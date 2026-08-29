"""Regression cover for the six bugs in field report #196.

All six were reproduced on the beta instance on 2026-08-29 before any fix
existed. Each test below fails on the pre-fix code for the reason named in
its docstring — not incidentally.
"""

import os
import tempfile

import pytest

import providers._vendor  # noqa: F401 — trigger sys.path shim at collection time


class TestBug1CacheRegionConfigured:
    """addic7ed_subliminal and tvsubtitles_subliminal failed EVERY search.

    ``_vendor/subliminal/cache.py`` builds ``region = make_region(...)`` and
    only ever configures it in ``cli.py`` — subliminal's own command-line
    entry point, which Sublarr never runs. So the region stayed unconfigured
    and every ``@region.cache_on_arguments`` call raised an AttributeError
    from inside dogpile. Those two providers are the only ones in the
    vendored tree that use the decorator, which is exactly the pair the
    field report names.
    """

    def test_region_is_configured_after_importing_the_vendor_shim(self):
        from subliminal.cache import region

        assert region.is_configured, (
            "the vendored subliminal cache region is unconfigured — every "
            "@region.cache_on_arguments call will raise from inside dogpile"
        )

    def test_region_actually_serves_a_value(self):
        from subliminal.cache import region

        assert region.get_or_create("sublarr-probe", lambda: "v") == "v"

    def test_only_addic7ed_and_tvsubtitles_depend_on_the_region(self):
        """Guards the blast radius claim above — if a third provider starts
        using the cache, this test says so instead of letting it surprise us."""
        vendor = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "providers",
            "_vendor",
            "subliminal",
            "providers",
        )
        users = set()
        for entry in os.listdir(vendor):
            if not entry.endswith(".py"):
                continue
            with open(os.path.join(vendor, entry), encoding="utf-8") as fh:
                if "region.cache_on_arguments" in fh.read():
                    users.add(entry)
        assert users == {"addic7ed.py", "tvsubtitles.py"}


class _FakeLanguage:
    alpha2 = "en"
    alpha3 = "eng"


class _OpenSubtitlesLikeSubtitle:
    """Shaped like the vendored OpenSubtitlesSubtitle: no ``release_group``."""

    language = _FakeLanguage()
    id = "os-1"
    filename = "Show.S01E01.1080p.BluRay.x264-GRP.srt"
    movie_release_name = "Show.S01E01.1080p.BluRay.x264-GRP"
    page_link = "http://example.invalid/1"
    hearing_impaired = False
    foreign_only = False
    fps = None


class _GestdownLikeSubtitle:
    """Shaped like the vendored GestdownSubtitle: has ``release_group``."""

    language = _FakeLanguage()
    id = "gd-1"
    filename = ""
    release_group = "GRP"
    page_link = "http://example.invalid/2"
    hearing_impaired = False
    foreign_only = False
    fps = None


class TestBug3ReleaseInfoFallback:
    """opensubtitles_subliminal downloads were stored score=0 / breakdown NULL.

    ``_to_sublarr_result`` read ``release_group`` only. gestdown's subtitle
    class sets it, opensubtitles' does not (it carries ``movie_release_name``
    and ``filename`` instead) — so ``release_info`` came out empty, no scoring
    rule could match, and the row was written with score 0. Same wrapper
    class, different attribute surface.
    """

    def test_release_group_still_wins_when_present(self):
        from providers.subliminal_adapter import _to_sublarr_result

        r = _to_sublarr_result(_GestdownLikeSubtitle(), "gestdown_subliminal")
        assert r.release_info == "GRP"

    def test_falls_back_to_movie_release_name(self):
        from providers.subliminal_adapter import _to_sublarr_result

        r = _to_sublarr_result(_OpenSubtitlesLikeSubtitle(), "opensubtitles_subliminal")
        assert r.release_info == "Show.S01E01.1080p.BluRay.x264-GRP", (
            "without a release_info the scorer has nothing to match on and "
            "writes score=0 / breakdown NULL"
        )

    def test_never_returns_none(self):
        from providers.subliminal_adapter import _to_sublarr_result

        class Bare:
            language = _FakeLanguage()
            id = "x"

        assert _to_sublarr_result(Bare(), "whatever").release_info == ""


class TestBug2NapiprojektHash:
    """napiprojekt_subliminal failed every search with a bare ``'napiprojekt'``.

    The vendored provider does ``video.hashes['napiprojekt']`` unguarded in
    ``list_subtitles``. Sublarr's adapter never populated ``video.hashes`` at
    all, so the lookup raised KeyError on every single search — 499 times in
    24h on the reporting install. ``str(KeyError('napiprojekt'))`` is exactly
    the message that reached the log.
    """

    def test_wrapper_declares_the_hash_it_needs(self):
        from providers.subliminal_napiprojekt import NapiProjektSubliminalProvider

        assert "napiprojekt" in NapiProjektSubliminalProvider.required_hashes

    def test_hash_is_computed_when_the_file_is_readable(self):
        from providers.base import VideoQuery
        from providers.subliminal_adapter import _to_subliminal_video

        with tempfile.NamedTemporaryFile(suffix=".mkv", delete=False) as fh:
            fh.write(b"x" * 2048)
            path = fh.name
        try:
            q = VideoQuery(
                file_path=path,
                series_title="My Show",
                season=1,
                episode=5,
                languages=["pl"],
            )
            video = _to_subliminal_video(q, required_hashes={"napiprojekt"})
            assert "napiprojekt" in video.hashes
            assert len(video.hashes["napiprojekt"]) == 32
        finally:
            os.unlink(path)

    def test_missing_file_does_not_raise_and_leaves_hashes_empty(self):
        """The install that filed the report has media the container can read.
        One that does not must degrade to "no result", never to an exception
        on every search."""
        from providers.base import VideoQuery
        from providers.subliminal_adapter import _to_subliminal_video

        q = VideoQuery(
            file_path="/nonexistent/path/to/Show.S01E01.mkv",
            series_title="My Show",
            season=1,
            episode=5,
            languages=["pl"],
        )
        video = _to_subliminal_video(q, required_hashes={"napiprojekt"})
        assert video.hashes == {}

    def test_default_is_no_hashing(self):
        """Hashing reads 10 MB off disk. Only the provider that needs it pays."""
        from providers.base import VideoQuery
        from providers.subliminal_adapter import _to_subliminal_video

        with tempfile.NamedTemporaryFile(suffix=".mkv", delete=False) as fh:
            fh.write(b"x" * 2048)
            path = fh.name
        try:
            q = VideoQuery(
                file_path=path,
                series_title="My Show",
                season=1,
                episode=5,
                languages=["pl"],
            )
            assert _to_subliminal_video(q).hashes == {}
        finally:
            os.unlink(path)


class TestBug6JimakuAuthHeader:
    """jimaku.cc rejects ``Authorization: Bearer <key>``.

    Its published OpenAPI security scheme declares an api_key-in-header
    scheme, explicitly not http/bearer. The reporter proved with the same
    credential Sublarr holds that the raw key returns HTTP 200 while the
    Bearer form 401s — so every jimaku request failed regardless of whether
    the key was valid, and the provider auto-disabled itself.
    """

    def test_sends_the_raw_key_without_a_bearer_prefix(self):
        from providers.jimaku import JimakuProvider

        p = JimakuProvider(api_key="TESTKEY123")
        p.initialize()
        try:
            assert p.session.headers["Authorization"] == "TESTKEY123"
        finally:
            p.terminate()


class TestBugs45PackagedDependencies:
    """OCR and spell-check ship as code, their Python bindings did not.

    The Dockerfile already installs tesseract-ocr (+deu/+eng), hunspell and
    both dictionaries — the comment above that apt block literally says
    "for OCR functionality" / "for spell checking". requirements.txt carried
    neither pytesseract, Pillow nor pyenchant, so the image shipped the
    binaries and the dictionaries and could not reach them.
    """

    @pytest.mark.parametrize("pkg", ["pytesseract", "Pillow", "pyenchant"])
    def test_declared_in_requirements(self, pkg):
        req = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "requirements.txt",
        )
        with open(req, encoding="utf-8") as fh:
            body = fh.read().lower()
        assert pkg.lower() in body
