"""HTML result-parsing mixin for LegendasDivxProvider.

Extracted from providers/legendasdivx.py. Owns the BeautifulSoup pass
that turns a search-results HTML page into :class:`SubtitleResult`
objects — the biggest method on the provider class and one that
depends only on ``self.name`` from the instance.

- ``_parse_search_results(html, query)`` — iterate rows, dispatch to
  ``_parse_result_row`` per row, swallow parse failures with a warning
- ``_parse_result_row(row, query)`` — pull download/detail URLs from
  anchor tags, detect format from filename extension, build the
  match-set for scoring, and emit a single SubtitleResult (or None
  when the row is a header/navigation element)
"""

import logging
import re
from urllib.parse import urljoin

from providers.base import SubtitleFormat, SubtitleResult, VideoQuery
from providers.legendasdivx_parsers import (
    _FORMAT_MAP,
    BASE_URL,
    _can_use_lxml,
    _parse_episode_info,
)

logger = logging.getLogger(__name__)


class _LegendasDivxParseMixin:
    """HTML → SubtitleResult translation for LegendasDivxProvider."""

    def _parse_search_results(self, html: str, query: VideoQuery) -> list[SubtitleResult]:
        """Parse HTML search results page into SubtitleResult objects."""
        # Imported lazily so the module can be loaded even when bs4 is missing;
        # the provider class blocks login/search in that case before we get here.
        from bs4 import BeautifulSoup

        results = []
        parser = "lxml" if _can_use_lxml() else "html.parser"
        soup = BeautifulSoup(html, parser)

        # LegendasDivx renders results in list/table format
        # Try multiple selectors for resilience
        rows = soup.find_all("tr")
        if not rows:
            rows = soup.find_all("div", class_=re.compile(r"result|subtitle|entry|download", re.I))

        if not rows:
            logger.debug("LegendasDivx: no result rows found in HTML")
            return []

        for row in rows:
            try:
                result = self._parse_result_row(row, query)
                if result:
                    results.append(result)
            except Exception as e:
                logger.warning("LegendasDivx: failed to parse result row: %s", e)
                continue

        logger.info("LegendasDivx: found %d results", len(results))
        return results

    def _parse_result_row(self, row, query: VideoQuery) -> SubtitleResult | None:
        """Parse a single result row into a SubtitleResult.

        Returns None if the row is not a valid subtitle result.
        """
        links = row.find_all("a", href=True)
        if not links:
            return None

        download_url = ""
        detail_url = ""
        release_name = ""

        for link in links:
            href = link.get("href", "")
            text = link.get_text(strip=True)

            if "download" in href.lower() or any(
                href.lower().endswith(ext) for ext in [".zip", ".rar", ".srt"]
            ):
                download_url = urljoin(BASE_URL, href)
            elif href and text and len(text) > 3:
                detail_url = urljoin(BASE_URL, href)
                if not release_name:
                    release_name = text

        if not download_url and not detail_url:
            return None

        effective_url = download_url or detail_url

        row_text = row.get_text(" ", strip=True)
        if not release_name:
            release_name = row_text[:200]

        # Skip header/navigation rows
        if len(release_name) < 3 or release_name.lower() in (
            "titulo",
            "descricao",
            "download",
            "idioma",
        ):
            return None

        # Detect format
        fmt = SubtitleFormat.SRT
        for ext_str in [".ass", ".ssa", ".srt", ".sub"]:
            if ext_str in release_name.lower():
                fmt = _FORMAT_MAP.get(ext_str, SubtitleFormat.SRT)
                break

        # Build matches
        matches = set()
        parsed = _parse_episode_info(release_name)

        if query.is_episode:
            series_title = query.series_title or query.title
            if series_title and series_title.lower() in release_name.lower():
                matches.add("series")
            if parsed.get("season") == query.season:
                matches.add("season")
            if parsed.get("episode") == query.episode:
                matches.add("episode")
        elif query.is_movie:
            if query.title and query.title.lower() in release_name.lower():
                matches.add("title")
            if query.year and str(query.year) in release_name:
                matches.add("year")

        if query.release_group and query.release_group.lower() in release_name.lower():
            matches.add("release_group")
        if query.resolution and parsed.get("resolution") == query.resolution:
            matches.add("resolution")

        subtitle_id = effective_url.split("/")[-1] if "/" in effective_url else effective_url

        return SubtitleResult(
            provider_name=self.name,
            subtitle_id=f"legendasdivx:{subtitle_id}",
            language="pt",
            format=fmt,
            filename=release_name[:100],
            download_url=effective_url,
            release_info=release_name,
            matches=matches,
            provider_data={
                "is_detail_page": not download_url,
                "detail_url": detail_url,
            },
        )
