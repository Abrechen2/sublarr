"""Per-item processing mixin for StandaloneScanner.

Extracted from standalone/scanner.py. Owns the three big "process"
methods — ``_process_series_group``, ``_process_movie``,
``process_single_file`` — plus the inline helpers used by
``process_single_file``'s episode fallback path. All depend on
``self._get_resolver()``, ``self._get_target_languages()``,
``self._check_existing_subtitle()`` and ``self._find_common_parent()``,
which stay on :class:`StandaloneScanner` itself.

Metadata priority inside each method is: NFO file → MetadataResolver
(online) → filename.
"""

import logging
import os

logger = logging.getLogger(__name__)


class _StandaloneProcessMixin:
    """Item-processing methods composed into StandaloneScanner."""

    def _process_series_group(self, title: str, files: list[dict], folder: dict) -> int:
        """Process a group of episode files belonging to one series.

        Resolves metadata once for the series, upserts standalone_series,
        then checks each episode for missing target language subtitles.

        Metadata priority: NFO file → MetadataResolver (online) → filename.

        Args:
            title: Normalized series title (lowercase).
            files: List of parsed file dicts (each with file_path key).
            folder: The watched folder dict.

        Returns:
            Number of wanted items added.
        """
        from db.standalone import upsert_standalone_series
        from db.wanted import upsert_wanted_item
        from standalone.nfo_parser import find_local_poster, parse_series_nfo

        # Use the first file's original title for display
        display_title = files[0].get("title", title)
        is_anime = any(f.get("is_anime", False) for f in files)
        year = None
        for f in files:
            if f.get("year"):
                year = f["year"]
                break

        # Determine series folder path (common parent)
        series_folder = self._find_common_parent([f["file_path"] for f in files])

        # --- NFO-first metadata resolution ---
        nfo = parse_series_nfo(series_folder)

        if nfo and (nfo.get("title") or nfo.get("tvdb_id") or nfo.get("tmdb_id")):
            nfo_title = nfo.get("title") or display_title
            nfo_year = nfo.get("year") or year
            nfo_is_anime = nfo.get("is_anime", is_anime)

            if nfo.get("tvdb_id") or nfo.get("tmdb_id"):
                # NFO has IDs — no online lookup needed
                poster_url = nfo.get("local_poster") or ""
                meta: dict = {}
            else:
                # NFO has title but no IDs — enrich via resolver
                resolver = self._get_resolver()
                meta = resolver.resolve_series(nfo_title, year=nfo_year, is_anime=nfo_is_anime)
                poster_url = nfo.get("local_poster") or meta.get("poster_url", "")

            series_id = upsert_standalone_series(
                title=nfo_title,
                folder_path=series_folder,
                year=nfo_year,
                tmdb_id=nfo.get("tmdb_id") or meta.get("tmdb_id"),
                tvdb_id=nfo.get("tvdb_id") or meta.get("tvdb_id"),
                anilist_id=nfo.get("anilist_id") or meta.get("anilist_id"),
                imdb_id=nfo.get("imdb_id") or meta.get("imdb_id", ""),
                poster_url=poster_url,
                is_anime=nfo_is_anime,
                episode_count=len(files),
                season_count=meta.get("season_count") or 0,
                metadata_source="nfo",
            )
            resolved_title = nfo_title
        else:
            # No usable NFO — fall back to MetadataResolver
            resolver = self._get_resolver()
            meta = resolver.resolve_series(display_title, year=year, is_anime=is_anime)
            local_poster = find_local_poster(series_folder)
            poster_url = local_poster or meta.get("poster_url", "")

            series_id = upsert_standalone_series(
                title=meta.get("title", display_title),
                folder_path=series_folder,
                year=meta.get("year"),
                tmdb_id=meta.get("tmdb_id"),
                tvdb_id=meta.get("tvdb_id"),
                anilist_id=meta.get("anilist_id"),
                imdb_id=meta.get("imdb_id", ""),
                poster_url=poster_url,
                is_anime=meta.get("is_anime", is_anime),
                episode_count=len(files),
                season_count=meta.get("season_count") or 0,
                metadata_source=meta.get("metadata_source", "filename"),
            )
            resolved_title = meta.get("title", display_title)

        # Check each episode for missing target subtitles
        wanted_added = 0
        target_languages = self._get_target_languages()

        for f in files:
            file_path = f["file_path"]
            season = f.get("season")
            episode = f.get("episode")

            season_episode = ""
            if season is not None and episode is not None:
                season_episode = f"S{season:02d}E{episode:02d}"
            elif episode is not None:
                season_episode = f"E{episode:02d}"

            for target_lang in target_languages:
                existing = self._check_existing_subtitle(file_path, target_lang)
                if existing == "ass":
                    continue  # Goal achieved

                ep_title = resolved_title
                if season_episode:
                    ep_title = f"{ep_title} -- {season_episode}"

                upsert_wanted_item(
                    item_type="episode",
                    file_path=file_path,
                    title=ep_title,
                    season_episode=season_episode,
                    existing_sub=existing or "",
                    missing_languages=[target_lang],
                    target_language=target_lang,
                    instance_name="standalone",
                    standalone_series_id=series_id,
                )
                wanted_added += 1

        return wanted_added

    def _process_movie(self, parsed: dict, file_path: str, folder: dict) -> int:
        """Process a single movie file.

        Resolves metadata, upserts standalone_movie, checks for missing
        target language subtitles.

        Metadata priority: NFO file → MetadataResolver (online) → filename.

        Args:
            parsed: Parsed file metadata dict.
            file_path: Absolute path to the movie file.
            folder: The watched folder dict.

        Returns:
            1 if a wanted item was added, 0 otherwise.
        """
        from db.standalone import upsert_standalone_movie
        from db.wanted import upsert_wanted_item
        from standalone.nfo_parser import find_local_poster, parse_movie_nfo

        title = parsed.get("title", "Unknown")
        year = parsed.get("year")
        movie_folder = os.path.dirname(file_path)

        # --- NFO-first metadata resolution ---
        nfo = parse_movie_nfo(movie_folder)

        if nfo and (nfo.get("title") or nfo.get("tmdb_id")):
            nfo_title = nfo.get("title") or title
            nfo_year = nfo.get("year") or year

            if nfo.get("tmdb_id"):
                # NFO has IDs — no online lookup needed
                poster_url = nfo.get("local_poster") or ""
                tmdb_id = nfo["tmdb_id"]
                imdb_id = nfo.get("imdb_id", "")
            else:
                # NFO has title but no IDs — enrich via resolver
                resolver = self._get_resolver()
                meta = resolver.resolve_movie(nfo_title, year=nfo_year)
                poster_url = nfo.get("local_poster") or meta.get("poster_url", "")
                tmdb_id = meta.get("tmdb_id")
                imdb_id = nfo.get("imdb_id") or meta.get("imdb_id", "")

            movie_id = upsert_standalone_movie(
                title=nfo_title,
                file_path=file_path,
                year=nfo_year,
                tmdb_id=tmdb_id,
                imdb_id=imdb_id,
                poster_url=poster_url,
                metadata_source="nfo",
            )
            resolved_title = nfo_title
        else:
            # No usable NFO — fall back to MetadataResolver
            resolver = self._get_resolver()
            meta = resolver.resolve_movie(title, year=year)
            local_poster = find_local_poster(movie_folder)
            poster_url = local_poster or meta.get("poster_url", "")

            movie_id = upsert_standalone_movie(
                title=meta.get("title", title),
                file_path=file_path,
                year=meta.get("year"),
                tmdb_id=meta.get("tmdb_id"),
                imdb_id=meta.get("imdb_id", ""),
                poster_url=poster_url,
                metadata_source=meta.get("metadata_source", "filename"),
            )
            resolved_title = meta.get("title", title)

        # Check for missing target subtitles
        wanted_added = 0
        target_languages = self._get_target_languages()

        for target_lang in target_languages:
            existing = self._check_existing_subtitle(file_path, target_lang)
            if existing == "ass":
                continue

            upsert_wanted_item(
                item_type="movie",
                file_path=file_path,
                title=resolved_title,
                existing_sub=existing or "",
                missing_languages=[target_lang],
                target_language=target_lang,
                instance_name="standalone",
                standalone_movie_id=movie_id,
            )
            wanted_added += 1

        return wanted_added

    def process_single_file(self, file_path: str) -> dict:
        """Process a single newly detected file.

        Parses the file, resolves metadata, creates/updates standalone
        entry, and creates wanted item if subtitles are missing.

        This is the callback target for the watcher's on_new_file.

        Args:
            file_path: Absolute path to the media file.

        Returns:
            Dict with type, title, wanted (bool).
        """
        from standalone.parser import parse_media_file

        try:
            parsed = parse_media_file(file_path)

            if parsed["type"] == "movie":
                wanted = self._process_movie(
                    parsed, file_path, {"path": os.path.dirname(file_path)}
                )
                return {
                    "type": "movie",
                    "title": parsed.get("title", "Unknown"),
                    "wanted": wanted > 0,
                }
            else:
                # For a single episode file detected by the watcher, mirror the
                # NFO-first flow used by the full-scan path (_process_series_group):
                # parse tvshow.nfo first, fall back to MetadataResolver only when
                # the NFO is missing or empty. Without this, a watcher-triggered
                # upsert was overwriting NFO-sourced TVDB/TMDB IDs with whatever
                # the resolver returned (often the filename-stub during transient
                # API failures), so the same series ended up flapping between
                # metadata_source="nfo" after a full scan and metadata_source=
                # "filename" after a single watcher event. See audit S1-2.
                from db.standalone import upsert_standalone_series
                from db.wanted import upsert_wanted_item
                from standalone.nfo_parser import find_local_poster, parse_series_nfo

                title = parsed.get("title", "Unknown")
                is_anime = parsed.get("is_anime", False)
                year = parsed.get("year")

                # Use the same season-folder normalization as the group path
                # (_process_series_group → _find_common_parent) so that single
                # episodes detected by the watcher don't create a duplicate
                # standalone_series entry rooted at the season subfolder.
                series_folder = self._find_common_parent([file_path])

                nfo = parse_series_nfo(series_folder)

                if nfo and (nfo.get("title") or nfo.get("tvdb_id") or nfo.get("tmdb_id")):
                    nfo_title = nfo.get("title") or title
                    nfo_year = nfo.get("year") or year
                    nfo_is_anime = nfo.get("is_anime", is_anime)

                    if nfo.get("tvdb_id") or nfo.get("tmdb_id"):
                        # NFO has IDs — no online lookup needed
                        poster_url = nfo.get("local_poster") or ""
                        meta: dict = {}
                    else:
                        # NFO has title but no IDs — enrich via resolver
                        resolver = self._get_resolver()
                        meta = resolver.resolve_series(
                            nfo_title, year=nfo_year, is_anime=nfo_is_anime
                        )
                        poster_url = nfo.get("local_poster") or meta.get("poster_url", "")

                    series_id = upsert_standalone_series(
                        title=nfo_title,
                        folder_path=series_folder,
                        year=nfo_year,
                        tmdb_id=nfo.get("tmdb_id") or meta.get("tmdb_id"),
                        tvdb_id=nfo.get("tvdb_id") or meta.get("tvdb_id"),
                        anilist_id=nfo.get("anilist_id") or meta.get("anilist_id"),
                        imdb_id=nfo.get("imdb_id") or meta.get("imdb_id", ""),
                        poster_url=poster_url,
                        is_anime=nfo_is_anime,
                        metadata_source="nfo",
                    )
                    resolved_title = nfo_title
                else:
                    resolver = self._get_resolver()
                    meta = resolver.resolve_series(title, year=year, is_anime=is_anime)
                    local_poster = find_local_poster(series_folder)
                    poster_url = local_poster or meta.get("poster_url", "")

                    series_id = upsert_standalone_series(
                        title=meta.get("title", title),
                        folder_path=series_folder,
                        year=meta.get("year"),
                        tmdb_id=meta.get("tmdb_id"),
                        tvdb_id=meta.get("tvdb_id"),
                        anilist_id=meta.get("anilist_id"),
                        imdb_id=meta.get("imdb_id", ""),
                        poster_url=poster_url,
                        is_anime=meta.get("is_anime", is_anime),
                        metadata_source=meta.get("metadata_source", "filename"),
                    )
                    resolved_title = meta.get("title", title)

                # Check for missing subtitles
                wanted = False
                target_languages = self._get_target_languages()
                season = parsed.get("season")
                episode = parsed.get("episode")

                season_episode = ""
                if season is not None and episode is not None:
                    season_episode = f"S{season:02d}E{episode:02d}"
                elif episode is not None:
                    season_episode = f"E{episode:02d}"

                for target_lang in target_languages:
                    existing = self._check_existing_subtitle(file_path, target_lang)
                    if existing == "ass":
                        continue

                    ep_title = resolved_title
                    if season_episode:
                        ep_title = f"{ep_title} -- {season_episode}"

                    upsert_wanted_item(
                        item_type="episode",
                        file_path=file_path,
                        title=ep_title,
                        season_episode=season_episode,
                        existing_sub=existing or "",
                        missing_languages=[target_lang],
                        target_language=target_lang,
                        instance_name="standalone",
                        standalone_series_id=series_id,
                    )
                    wanted = True

                return {
                    "type": "episode",
                    "title": resolved_title,
                    "wanted": wanted,
                }

        except Exception as e:
            logger.error("Error processing single file %s: %s", file_path, e)
            return {"type": "unknown", "title": "", "wanted": False, "error": str(e)}
