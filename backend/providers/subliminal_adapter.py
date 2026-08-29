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

from subliminal.video import Episode, Movie, Video

import providers._vendor  # noqa: F401 — side-effect import adds vendor to sys.path
from providers.base import SubtitleFormat, SubtitleProvider, SubtitleResult, VideoQuery

logger = logging.getLogger(__name__)


def _release_info(s) -> str:
    """Best available release string for a Subliminal subtitle.

    Subliminal's provider classes do not share one attribute for this.
    Gestdown sets ``release_group``; OpenSubtitles has no such attribute at
    all and carries ``movie_release_name`` / ``filename`` instead. Reading
    only ``release_group`` left ``release_info`` empty for the latter, no
    scoring rule could match, and every opensubtitles_subliminal download was
    written with score 0 and a NULL breakdown while its sibling wrapper
    scored normally off the same code path.

    ``info`` is Subliminal's own "describe this subtitle" property and is the
    right last resort — OpenSubtitles implements it as
    "whichever of movie_release_name / filename is longer".
    """
    for attr in ("release_group", "movie_release_name", "filename", "info"):
        value = getattr(s, attr, None)
        if value:
            return str(value)
    return ""


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
        release_info=_release_info(s),
        provider_data={"subliminal_subtitle": s},  # keep reference for download()
    )


#: Hash name -> the vendored refiner function that computes it. Only the
#: providers that declare a hash in ``required_hashes`` pay for it, because
#: each of these reads a large chunk off disk.
_HASH_FUNCTIONS = {"napiprojekt": "hash_napiprojekt", "opensubtitles": "hash_opensubtitles"}


def _compute_hashes(file_path: str, wanted: set[str]) -> dict[str, str]:
    """Compute the requested video hashes, skipping anything unavailable.

    A provider that needs a hash it cannot get must degrade to "no results",
    never to an exception. napiprojekt's vendored ``list_subtitles`` does a
    bare ``video.hashes['napiprojekt']``, so an absent hash raised KeyError on
    every single search — 499 times in 24h on the install that reported it.
    """
    if not file_path or not wanted:
        return {}
    hashes: dict[str, str] = {}
    for name in wanted:
        func_name = _HASH_FUNCTIONS.get(name)
        if not func_name:
            continue
        try:
            from subliminal.refiners import hash as _hash_refiner

            value = getattr(_hash_refiner, func_name)(file_path)
        except (OSError, ValueError, AttributeError) as e:
            logger.debug("could not compute %s hash for %s: %s", name, file_path, e)
            continue
        if value:
            hashes[name] = value
    return hashes


def _to_subliminal_video(query: VideoQuery, required_hashes: set[str] | None = None) -> Video:
    """Convert a Sublarr VideoQuery into a subliminal Video/Episode/Movie.

    Only fields that Subliminal scoring/matching actually reads are forwarded.
    Missing fields are left as Subliminal's defaults (usually None/empty).

    ``required_hashes`` names the video hashes the wrapped provider needs.
    It defaults to none: hashing reads megabytes off disk, so only a provider
    that actually looks a hash up should trigger it.
    """
    video = _build_video(query)
    if required_hashes:
        video.hashes.update(_compute_hashes(query.file_path or "", set(required_hashes)))
    return video


def _build_video(query: VideoQuery) -> Video:
    if query.is_episode:
        default_name = f"{query.series_title}.S{query.season:02d}E{query.episode:02d}.mkv"
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

    #: Video hashes the wrapped provider looks up. Empty by default — computing
    #: one reads megabytes off disk, so a provider opts in rather than every
    #: search paying for it. See ``_compute_hashes``.
    required_hashes: set[str] = frozenset()

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

        video = _to_subliminal_video(query, required_hashes=self.required_hashes)

        # A hash-only provider called without its hash does not fail politely:
        # napiprojekt's vendored list_subtitles indexes video.hashes directly,
        # so a missing entry raises on every single search. Computing the hash
        # is not enough — when it could not be produced (unreadable path,
        # remote mount, file gone) the search must not be attempted at all.
        missing = set(self.required_hashes) - set(video.hashes)
        if missing:
            logger.debug(
                "%s: skipping search, required hash(es) unavailable for %s: %s",
                self.name,
                query.file_path or "<no path>",
                ", ".join(sorted(missing)),
            )
            return []

        try:
            subliminal_subtitles = self._impl.list_subtitles(video, lang_set)
        except Exception as e:
            logger.warning("Subliminal provider %s failed search: %s", self.name, e)
            return []

        return [_to_sublarr_result(s, self.name) for s in subliminal_subtitles]

    def download(self, result: SubtitleResult) -> bytes:
        """Download subtitle content via the wrapped Subliminal provider."""
        subliminal_sub = result.provider_data.get("subliminal_subtitle")
        if subliminal_sub is None:
            raise ValueError(
                "SubtitleResult from SubliminalProviderAdapter missing "
                "provider_data['subliminal_subtitle'] — results must come "
                "from the same adapter instance that produced them."
            )
        self._impl.download_subtitle(subliminal_sub)
        return subliminal_sub.content or b""
