"""Catalog bundles cannot reach local files, loopback or the LAN (Forgejo #54).

The vendored bundles fetch with urllib and http.client on their own and are
pinned by hash, so the download-URL policy is enforced around them: every
request URL (each redirect hop included) and every socket a bundle opens is
checked while bundle code runs.
"""

import hashlib
import http.client
import http.server
import io
import ipaddress
import os
import socket
import threading
import urllib.request
from email.message import Message

import pytest

from providers.base import ProviderError, SubtitleResult
from providers.hub import BUNDLES_DIR, build_provider_class, discover_bundles
from providers.hub.net_guard import HubNetworkBlockedError, outbound_guard

SRT = b"1\n00:00:01,000 --> 00:00:02,000\nsecret\n"


@pytest.fixture
def loopback_server():
    """A plain HTTP server on 127.0.0.1 that serves an SRT body."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 — http.server's naming
            self.send_response(200)
            self.send_header("Content-Length", str(len(SRT)))
            self.end_headers()
            self.wfile.write(SRT)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def local_file(tmp_path):
    path = tmp_path / "local.srt"
    path.write_bytes(SRT)
    return path


# -- the guard itself ------------------------------------------------------------


def test_outside_the_guard_loopback_and_files_still_work(loopback_server, local_file):
    """Positive control: the guard is scoped, the rest of Sublarr is untouched."""
    with urllib.request.urlopen(f"http://127.0.0.1:{loopback_server}/") as resp:
        assert resp.read() == SRT
    with urllib.request.urlopen(local_file.as_uri()) as resp:
        assert resp.read() == SRT


def test_a_file_url_is_refused(local_file):
    with outbound_guard("fakehub"), pytest.raises(HubNetworkBlockedError, match="scheme"):
        urllib.request.urlopen(local_file.as_uri())


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "[::1]"])
def test_loopback_is_refused(loopback_server, host):
    with outbound_guard("fakehub"), pytest.raises(HubNetworkBlockedError):
        urllib.request.urlopen(f"http://{host}:{loopback_server}/", timeout=5)


@pytest.mark.parametrize(
    "url",
    [
        "http://192.168.178.10/x.srt",
        "http://10.0.0.1/x.srt",
        "http://100.64.0.1/x.srt",
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.google.internal/",
        "http://2130706433/",
    ],
)
def test_lan_and_metadata_urls_are_refused(url):
    with outbound_guard("fakehub"), pytest.raises(HubNetworkBlockedError):
        urllib.request.urlopen(url, timeout=5)


def test_raw_http_client_connections_are_checked_too(loopback_server):
    """Bundles that use http.client directly (greeksubtitles, subtitlecat)."""
    conn = http.client.HTTPConnection("127.0.0.1", loopback_server, timeout=5)
    with outbound_guard("fakehub"), pytest.raises(HubNetworkBlockedError):
        conn.request("GET", "/")
    conn.close()


class _RedirectToLoopback(urllib.request.HTTPHandler):
    """Answers the first hop with a 302 to a loopback address, without network."""

    def http_open(self, req):
        if req.host == "subs.example.com":
            headers = Message()
            headers["Location"] = "http://127.0.0.1:1/x.srt"
            resp = urllib.request.addinfourl(io.BytesIO(b""), headers, req.full_url, 302)
            resp.msg = "Found"
            return resp
        return super().http_open(req)


def test_every_redirect_hop_is_checked():
    opener = urllib.request.build_opener(_RedirectToLoopback())
    with outbound_guard("fakehub"), pytest.raises(HubNetworkBlockedError, match="127.0.0.1"):
        opener.open("http://subs.example.com/x.srt", timeout=5)


class _AnswerEverything(urllib.request.HTTPHandler):
    """Answers every request with 200 and no network, so only the guard decides."""

    def http_open(self, req):
        return urllib.request.addinfourl(io.BytesIO(SRT), Message(), req.full_url, 200)


def _open_offline(url):
    opener = urllib.request.OpenerDirector()
    opener.add_handler(_AnswerEverything())
    with opener.open(url, timeout=1) as resp:
        return resp.read()


@pytest.fixture
def no_proxy_env(monkeypatch):
    for name in ("http_proxy", "https_proxy", "all_proxy", "no_proxy"):
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.upper(), raising=False)


@pytest.fixture
def fake_dns(monkeypatch):
    """Resolve a few test names without a DNS server; others fail to resolve."""
    table = {
        "subsarr.lan": "192.168.178.20",
        "intranet.lan": "192.168.178.99",
        "proxy.lan": "192.168.178.2",
        "subs.example.com": "93.184.215.14",
    }

    def getaddrinfo(host, port, *args, **kwargs):
        try:
            ip = table.get(host) or str(ipaddress.ip_address(host))
        except ValueError:
            raise socket.gaierror(f"unknown host {host}") from None
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port or 0))]

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    return table


def test_an_operator_host_is_reachable_but_no_other_lan_host(no_proxy_env, fake_dns):
    """Only the host the operator configured may be private (Subsarr's base_url)."""
    with outbound_guard("subsarr", operator_urls=["http://192.168.178.20:8080"]):
        assert _open_offline("http://192.168.178.20:8080/api") == SRT
        with pytest.raises(HubNetworkBlockedError, match="192.168.178.21"):
            _open_offline("http://192.168.178.21/api")


def test_an_operator_host_name_allows_only_its_own_addresses(no_proxy_env, fake_dns):
    with outbound_guard("subsarr", operator_urls=["http://subsarr.lan:8080"]):
        assert _open_offline("http://subsarr.lan:8080/api") == SRT
        sock = socket.socket()
        sock.settimeout(0.01)
        try:
            with pytest.raises(HubNetworkBlockedError):
                sock.connect(("192.168.178.99", 80))
        finally:
            sock.close()


def test_loopback_stays_refused_even_when_configured(no_proxy_env, loopback_server):
    with (
        outbound_guard("subsarr", operator_urls=[f"http://127.0.0.1:{loopback_server}"]),
        pytest.raises(HubNetworkBlockedError),
    ):
        urllib.request.urlopen(f"http://127.0.0.1:{loopback_server}/", timeout=5)


def test_a_bundle_url_setting_outside_the_allowlist_opens_nothing(no_proxy_env, bundle_dir):
    """A setting named *_url in some other bundle is no operator server address."""
    provider = _fake_provider(bundle_dir, mirror_url="http://192.168.178.21/")
    with provider._network_guard(), pytest.raises(HubNetworkBlockedError):
        _open_offline("http://192.168.178.21/x.srt")


def test_subsarr_gets_exactly_its_configured_base_url(no_proxy_env, fake_dns):
    provider = _real_provider("subsarr", base_url="http://subsarr.lan:8080")
    with provider._network_guard():
        assert _open_offline("http://subsarr.lan:8080/api") == SRT
        with pytest.raises(HubNetworkBlockedError):
            _open_offline("http://192.168.178.21/api")


@pytest.fixture
def lan_proxy(monkeypatch):
    monkeypatch.setenv("http_proxy", "http://proxy.lan:3128")
    monkeypatch.delenv("no_proxy", raising=False)
    monkeypatch.delenv("NO_PROXY", raising=False)


@pytest.mark.parametrize("url", ["http://intranet.lan/x.srt", "http://subs.example.com/x.srt"])
def test_a_proxied_request_to_a_host_name_is_refused(lan_proxy, fake_dns, url):
    """The proxy resolves the name itself (DNS rebinding), so no check here can hold."""
    with outbound_guard("fakehub"), pytest.raises(HubNetworkBlockedError, match="proxied request"):
        _open_offline(url)


def test_a_proxied_request_to_a_public_ip_passes_the_url_check(lan_proxy, fake_dns):
    with outbound_guard("fakehub"):
        assert _open_offline("http://93.184.215.14/x.srt") == SRT


def test_the_proxy_host_is_not_an_allowed_target(lan_proxy, fake_dns):
    """Configuring a proxy grants its host nothing: no request to it, no socket."""
    with outbound_guard("fakehub"):
        with pytest.raises(HubNetworkBlockedError):
            _open_offline("http://192.168.178.2:3128/x.srt")
        sock = socket.socket()
        sock.settimeout(0.01)
        try:
            with pytest.raises(HubNetworkBlockedError):
                sock.connect(("192.168.178.2", 3128))
        finally:
            sock.close()


def test_a_proxy_tunnel_to_a_host_name_is_refused(no_proxy_env, fake_dns):
    conn = http.client.HTTPConnection("93.184.215.14", 3128, timeout=0.01)
    conn.set_tunnel("subs.example.com", 443)
    with outbound_guard("fakehub"), pytest.raises(HubNetworkBlockedError, match="tunnel"):
        conn.request("GET", "/")
    conn.close()


def test_a_proxy_tunnel_to_a_private_ip_is_refused(no_proxy_env, fake_dns):
    conn = http.client.HTTPConnection("93.184.215.14", 3128, timeout=0.01)
    conn.set_tunnel("192.168.178.99", 443)
    with outbound_guard("fakehub"), pytest.raises(HubNetworkBlockedError, match="192.168.178.99"):
        conn.request("GET", "/")
    conn.close()


def test_the_guard_is_per_thread(loopback_server):
    """A hub search on one thread does not block a Sonarr call on another."""
    results = []
    entered = threading.Event()
    release = threading.Event()

    def hub_thread():
        with outbound_guard("fakehub"):
            entered.set()
            release.wait(5)

    t = threading.Thread(target=hub_thread)
    t.start()
    entered.wait(5)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{loopback_server}/") as resp:
            results.append(resp.read())
    finally:
        release.set()
        t.join(5)
    assert results == [SRT]


# -- the real vendored bundles named in the issue ---------------------------------


def _real_provider(hub_id, **config):
    for bundle_id, bundle_dir, manifest in discover_bundles(BUNDLES_DIR):
        if bundle_id == hub_id:
            provider = build_provider_class(hub_id, bundle_dir, manifest)(**config)
            provider.initialize()
            return provider
    raise AssertionError(f"{hub_id} bundle missing")


_FAKE_BUNDLE = "class FakeProvider:\n    pass\n"


@pytest.fixture
def bundle_dir(tmp_path):
    path = tmp_path / "fakehub"
    path.mkdir()
    (path / "provider.py").write_text(_FAKE_BUNDLE)
    return path


def _fake_provider(bundle_dir, **config):
    manifest = {
        "provider_id": "fakehub",
        "entry_module": "provider",
        "entry_class": "FakeProvider",
        "config_schema": {"properties": {"mirror_url": {"type": "string"}}},
        "files": {"provider.py": hashlib.sha256(_FAKE_BUNDLE.encode()).hexdigest()},
    }
    provider = build_provider_class("fakehub", str(bundle_dir), manifest)(**config)
    provider.initialize()
    return provider


def _result(provider, payload):
    return SubtitleResult(
        provider_name=provider.name,
        subtitle_id="x",
        language="tr",
        filename="x.srt",
        provider_data={"payload": payload, "language": {"alpha3": "tur"}},
    )


def test_animekalesi_cannot_read_a_local_file(local_file):
    provider = _real_provider("animekalesi")
    result = _result(provider, {"download_url": local_file.as_uri()})
    with pytest.raises(ProviderError):
        provider.download(result)
    assert result.content is None


def test_shooter_cannot_fetch_from_loopback(loopback_server):
    provider = _real_provider("shooter")
    result = _result(
        provider,
        {"provider": "shooter", "download_url": f"http://127.0.0.1:{loopback_server}/x.srt"},
    )
    with pytest.raises(ProviderError):
        provider.download(result)
    assert result.content is None


def test_the_guard_does_not_outlive_a_bundle_call(loopback_server, local_file):
    provider = _real_provider("animekalesi")
    with pytest.raises(ProviderError):
        provider.download(_result(provider, {"download_url": local_file.as_uri()}))
    assert os.path.exists(local_file)
    with urllib.request.urlopen(f"http://127.0.0.1:{loopback_server}/") as resp:
        assert resp.read() == SRT
