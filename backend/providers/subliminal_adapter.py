"""Thin adapter that wraps a Subliminal Provider class as a Sublarr SubtitleProvider.

Usage:

    from subliminal.providers.opensubtitles import OpenSubtitlesProvider
    from providers.subliminal_adapter import SubliminalProviderAdapter

    adapter = SubliminalProviderAdapter(
        subliminal_provider_cls=OpenSubtitlesProvider,
        provider_name="opensubtitles_subliminal",
        username="...",
        password="...",
    )
    results = adapter.search(query)
    content = adapter.download(results[0])

The adapter translates between Sublarr's `VideoQuery` / `SubtitleResult` dataclasses
and Subliminal's `Video` / `Subtitle` types.
"""

from __future__ import annotations

import logging

import providers._vendor  # noqa: F401 — side-effect import adds vendor to sys.path

from providers.base import SubtitleFormat, SubtitleProvider, SubtitleResult, VideoQuery

from subliminal.video import Episode, Movie, Video

logger = logging.getLogger(__name__)


def _to_sublarr_result(subliminal_subtitle, registered_name: str) -> SubtitleResult:
    """Convert a Subliminal Subtitle into a Sublarr SubtitleResult.

    `registered_name` is the name under which the adapter is registered with
    Sublarr's provider registry (e.g. "opensubtitles_subliminal") — not the
    Subliminal-internal provider_name attribute. We use our own name so that
    circuit-breaker + scoring + rate-limit state stays scoped to the adapter.
    """
    s = subliminal_subtitle
    language_code = getattr(s.language, "alpha2", "") or str(getattr(s.language, "alpha3", ""))
    return SubtitleResult(
        provider_name=registered_name,
        subtitle_id=str(getattr(s, "id", "")),
        language=language_code,
        format=SubtitleFormat.UNKNOWN,  # Subliminal determines format on download
        filename=getattr(s, "filename", "") or "",
        download_url=getattr(s, "page_link", "") or "",
        hearing_impaired=bool(getattr(s, "hearing_impaired", False)),
        forced=bool(getattr(s, "foreign_only", False)),
        fps=getattr(s, "fps", None),
        release_info=str(getattr(s, "release_group", "") or ""),
        provider_data={"subliminal_subtitle": s},  # keep reference for download()
    )


def _to_subliminal_video(query: VideoQuery) -> Video:
    """Convert a Sublarr VideoQuery into a subliminal Video/Episode/Movie.

    Only fields that Subliminal scoring/matching actually reads are forwarded.
    Missing fields are left as Subliminal's defaults (usually None/empty).
    """
    if query.is_episode:
        default_name = (
            f"{query.series_title}.S{query.season:02d}E{query.episode:02d}.mkv"
        )
        return Episode(
            name=query.file_path or default_name,
            series=query.series_title,
            season=query.season,
            # Subliminal 2.2.0 uses the plural "episodes" kwarg (int | Sequence[int]);
            # it still exposes an `episode` property for the first element.
            episodes=query.episode,
            title=query.episode_title or None,
            year=query.year,
            release_group=query.release_group or None,
            source=query.source or None,
            resolution=query.resolution or None,
            video_codec=query.video_codec or None,
            imdb_id=query.imdb_id or None,
        )
    return Movie(
        name=query.file_path or f"{query.title}.{query.year}.mkv",
        title=query.title,
        year=query.year,
        release_group=query.release_group or None,
        source=query.source or None,
        resolution=query.resolution or None,
        video_codec=query.video_codec or None,
        imdb_id=query.imdb_id or None,
    )


class SubliminalProviderAdapter(SubtitleProvider):
    """Wraps a Subliminal Provider class and exposes Sublarr's provider interface."""

    # Instance-level overrides so each adapter instance can present a distinct name
    name: str = "subliminal_adapter"

    def __init__(
        self,
        subliminal_provider_cls: type,
        provider_name: str,
        **config,
    ):
        super().__init__(**config)
        self._subliminal_provider_cls = subliminal_provider_cls
        self.name = provider_name
        self._impl = None  # Instantiated in initialize()

    def initialize(self):
        """Instantiate the wrapped Subliminal provider and enter its context."""
        self._impl = self._subliminal_provider_cls(**self._subliminal_kwargs())
        self._impl.initialize()

    def terminate(self):
        """Cleanly tear down the wrapped Subliminal provider."""
        if self._impl is not None:
            try:
                self._impl.terminate()
            finally:
                self._impl = None

    def _subliminal_kwargs(self) -> dict:
        """Subclasses of Subliminal providers accept different kwargs.

        The adapter forwards ALL non-empty values from self.config as kwargs.
        Subliminal providers that don't need certain kwargs ignore them.
        """
        return {k: v for k, v in self.config.items() if v not in (None, "")}

    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        """Search the wrapped Subliminal provider for subtitles matching query."""
        from babelfish import Language

        if not query.languages:
            return []

        # Convert ISO 639-1 codes in query.languages into babelfish Language objects.
        try:
            lang_set = {Language.fromalpha2(code) for code in query.languages}
        except ValueError as e:
            logger.warning("Invalid language code in query for %s: %s", self.name, e)
            return []

        video = _to_subliminal_video(query)

        try:
            subliminal_subtitles = self._impl.list_subtitles(video, lang_set)
        except Exception as e:
            logger.warning("Subliminal provider %s failed search: %s", self.name, e)
            return []

        return [_to_sublarr_result(s, self.name) for s in subliminal_subtitles]

    def download(self, result: SubtitleResult) -> bytes:
        """Not yet implemented — filled in by Task 9."""
        raise NotImplementedError("download() wired up in Task 9")
