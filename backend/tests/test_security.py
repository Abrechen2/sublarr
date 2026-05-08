"""Security tests — SSRF guard for service-URL config fields.

Added in response to the 2026-05-08 internal pentest, where every
non-canonical IP form (decimal/octal/hex), IPv4-mapped IPv6, and DNS
hostnames bypassed the link-local-only check in
``validate_service_url``.
"""

import os
import sys

# Ensure backend root is importable when pytest's conftest does not handle it.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestValidateServiceUrlBypassResistance:
    """SSRF allowlist bypasses surfaced by the 2026-05-08 internal pentest.

    Previous implementation only blocked link-local + cloud metadata + bad
    schemes, so a config-PUT with X-Api-Key could redirect Sonarr/Radarr/
    Ollama URL fields at internal services (Postgres :5432, Redis :6379)
    and at the AWS metadata endpoint via decimal-encoded IPs.
    """

    def test_loopback_v4_blocked(self):
        from security_utils import validate_service_url

        ok, reason = validate_service_url("http://127.0.0.1:5432/")
        assert ok is False
        assert "loopback" in (reason or "").lower()

    def test_loopback_v6_blocked(self):
        from security_utils import validate_service_url

        ok, reason = validate_service_url("http://[::1]:5765/")
        assert ok is False
        assert "loopback" in (reason or "").lower()

    def test_decimal_encoded_loopback_blocked(self):
        from security_utils import validate_service_url

        # 2130706433 == 127.0.0.1
        ok, _ = validate_service_url("http://2130706433/")
        assert ok is False

    def test_decimal_encoded_aws_metadata_blocked(self):
        from security_utils import validate_service_url

        # 2852039166 == 169.254.169.254 (AWS / Azure / GCP metadata)
        ok, _ = validate_service_url("http://2852039166/")
        assert ok is False

    def test_octal_encoded_loopback_blocked(self):
        from security_utils import validate_service_url

        ok, _ = validate_service_url("http://0177.0.0.1/")
        assert ok is False

    def test_hex_encoded_loopback_blocked(self):
        from security_utils import validate_service_url

        ok, _ = validate_service_url("http://0x7f.0.0.1/")
        assert ok is False

    def test_ipv4_mapped_ipv6_loopback_blocked(self):
        from security_utils import validate_service_url

        ok, _ = validate_service_url("http://[::ffff:127.0.0.1]/")
        assert ok is False

    def test_unspecified_v4_blocked(self):
        from security_utils import validate_service_url

        ok, _ = validate_service_url("http://0.0.0.0/")
        assert ok is False

    def test_short_zero_unspecified_blocked(self):
        from security_utils import validate_service_url

        # "0" is interpreted as 0.0.0.0 by inet_aton
        ok, _ = validate_service_url("http://0/")
        assert ok is False

    def test_localhost_hostname_blocked_via_dns_resolution(self):
        from security_utils import validate_service_url

        # localhost resolves to 127.0.0.1 / ::1 — must be rejected
        ok, _ = validate_service_url("http://localhost/")
        assert ok is False

    def test_link_local_literal_still_blocked(self):
        from security_utils import validate_service_url

        ok, _ = validate_service_url("http://169.254.169.254/")
        assert ok is False

    # Legitimate use cases that MUST keep working — homelab and public.

    def test_private_lan_homelab_allowed(self):
        from security_utils import validate_service_url

        # Sublarr is built for self-hosting and reaches Sonarr/Radarr on LAN.
        ok, _ = validate_service_url("http://192.168.178.36:5765/")
        assert ok is True

    def test_private_lan_10_8_allowed(self):
        from security_utils import validate_service_url

        ok, _ = validate_service_url("http://10.0.0.1/")
        assert ok is True

    def test_public_host_allowed(self):
        from security_utils import validate_service_url

        ok, _ = validate_service_url("https://api.opensubtitles.com/")
        assert ok is True

    def test_file_scheme_still_blocked(self):
        from security_utils import validate_service_url

        ok, _ = validate_service_url("file:///etc/passwd")
        assert ok is False

    def test_gopher_scheme_still_blocked(self):
        from security_utils import validate_service_url

        ok, _ = validate_service_url("gopher://127.0.0.1/")
        assert ok is False

    def test_metadata_hostname_still_blocked(self):
        from security_utils import validate_service_url

        ok, _ = validate_service_url("http://metadata.google.internal/")
        assert ok is False
