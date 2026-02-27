"""Example Sublarr provider plugin.

Copy this file to your plugins directory (default: /config/plugins/),
rename it, and modify the class to implement your provider.

Requirements:
- The file must contain exactly one class that extends SubtitleProvider
- The class must have a unique 'name' attribute (lowercase, no spaces)
- The class must implement search() and download() methods
- config_fields declares what settings the user can configure in the UI

Quick Start:
    1. Copy this file to /config/plugins/my_provider.py
    2. Change the class name, 'name' attribute, and config_fields
    3. Implement search() and download() with your provider's API
    4. Restart Sublarr or call POST /api/v1/plugins/reload
    5. Configure your plugin via Settings > Providers in the UI
"""

from providers.base import (
    SubtitleProvider,
    SubtitleResult,
    VideoQuery,
)
from providers.http_session import create_session


class MyProvider(SubtitleProvider):
    """Your custom subtitle provider.

    Attributes:
        name: Unique provider identifier (lowercase, no spaces, no underscores
              at start). This appears in the Settings UI and API responses.
              Must NOT conflict with built-in providers (animetosho, jimaku,
              opensubtitles, subdl).

        languages: Set of ISO 639-1 language codes this provider supports.
              Common codes: en, de, fr, es, it, pt, ja, zh, ko, ar, nl, pl,
              sv, da, no, fi, cs, hu, tr, th, vi, id, ms, hi, ru.

        config_fields: List of configuration fields rendered in the Settings UI.
              Each field is a dict with these keys:
                - key (str): Internal config key, passed to __init__ as kwarg
                - label (str): Human-readable label shown in the UI
                - type (str): "text", "password", or "number"
                - required (bool): If True, provider won't initialize without it
                - default (str): Default value (optional)

        rate_limit: Tuple of (max_requests, window_seconds).
              Controls how many requests the ProviderManager allows within
              the time window. (0, 0) means no rate limiting.

        timeout: HTTP request timeout in seconds. Used by ProviderManager
              for the search timeout and by create_session for HTTP calls.

        max_retries: Number of retry attempts on transient failures (network
              errors, 5xx responses). The ProviderManager retries search()
              calls this many additional times.
    """

    name = "my_provider"  # CHANGE THIS -- must be unique across all providers
    languages = {"en", "de", "fr"}  # ISO 639-1 codes your provider supports

    config_fields = [
        {
            "key": "api_key",
            "label": "API Key",
            "type": "password",
            "required": True,
        },
        {
            "key": "base_url",
            "label": "Base URL",
            "type": "text",
            "required": False,
            "default": "https://api.example.com",
        },
    ]

    rate_limit = (30, 60)  # 30 requests per 60 seconds
    timeout = 15  # seconds
    max_retries = 2

    def __init__(self, **config):
        """Initialize the provider with config values.

        Config values come from config_fields: each field's 'key' is passed
        as a keyword argument. For example, with the config_fields above,
        you receive api_key="..." and base_url="..." here.

        Always call super().__init__(**config) first.
        """
        super().__init__(**config)
        self.session = None
        self.api_key = config.get("api_key", "")
        self.base_url = config.get("base_url", "https://api.example.com")

    def initialize(self):
        """Called once when the provider is loaded. Set up HTTP sessions here.

        This is called by ProviderManager during startup or after reload.
        Do NOT do expensive work in __init__ -- use initialize() instead.
        If the provider requires an API key and none is configured, set
        self.session = None to signal that the provider is disabled.
        """
        if not self.api_key:
            # Provider won't work without an API key
            return

        self.session = create_session(
            max_retries=self.max_retries,
            timeout=self.timeout,
            user_agent="Sublarr-Plugin/1.0",
        )
        # You can set auth headers on the session:
        # self.session.headers["Authorization"] = f"Bearer {self.api_key}"
        # self.session.headers["X-Api-Key"] = self.api_key

    def terminate(self):
        """Called when the provider is unloaded. Clean up resources.

        Release HTTP sessions, close connections, etc. This is called
        when the app shuts down or when plugins are reloaded.
        """
        if self.session:
            self.session.close()
            self.session = None

    def search(self, query: VideoQuery) -> list[SubtitleResult]:
        """Search for subtitles matching the query.

        Args:
            query: Contains all available metadata about the video:
                - file_path (str): Full path to the video file
                - file_hash (str): OpenSubtitles-compatible hash
                - title (str): Movie title or episode title
                - year (int|None): Release year
                - imdb_id (str): IMDB ID (e.g. "tt1234567")
                - tmdb_id (int|None): TMDB ID
                - series_title (str): TV series name
                - season (int|None): Season number
                - episode (int|None): Episode number
                - anidb_id (int|None): AniDB anime ID
                - anilist_id (int|None): AniList anime ID
                - tvdb_id (int|None): TVDB ID
                - release_group (str): Release group name
                - source (str): "BluRay", "WEB-DL", etc.
                - resolution (str): "1080p", "720p", etc.
                - languages (list[str]): Requested language codes
                - is_episode (bool): True if TV episode
                - is_movie (bool): True if movie
                - display_name (str): Human-readable name for logging

        Returns:
            List of SubtitleResult objects. Do NOT sort -- the ProviderManager
            handles scoring and sorting automatically.

        Scoring:
            Set result.matches to indicate what metadata matched. The
            ProviderManager computes a score from these matches:

            Episode scores: hash(359), series(180), year(90), season(30),
                episode(30), release_group(14), source(7), resolution(2)
            Movie scores: hash(119), title(60), year(30), release_group(13),
                source(7), resolution(2)
            Format bonus: ASS format gets +50 points automatically.

            Example: If your search matched by series name, season, and
            episode, set matches={"series", "season", "episode"} for a
            score of 180+30+30 = 240.
        """
        if not self.session:
            return []

        results = []

        # --- Replace this section with your actual API call ---

        # Example: search by series title and episode
        # params = {
        #     "q": query.series_title or query.title,
        #     "season": query.season,
        #     "episode": query.episode,
        #     "lang": ",".join(query.languages) if query.languages else "en",
        # }
        # resp = self.session.get(f"{self.base_url}/search", params=params)
        # resp.raise_for_status()
        #
        # for item in resp.json().get("results", []):
        #     # Determine subtitle format from filename
        #     filename = item.get("filename", "")
        #     if filename.endswith(".ass") or filename.endswith(".ssa"):
        #         fmt = SubtitleFormat.ASS
        #     elif filename.endswith(".srt"):
        #         fmt = SubtitleFormat.SRT
        #     else:
        #         fmt = SubtitleFormat.UNKNOWN
        #
        #     # Build the matches set based on what was matched
        #     matches = set()
        #     if item.get("series_match"):
        #         matches.add("series")
        #     if item.get("season_match"):
        #         matches.add("season")
        #     if item.get("episode_match"):
        #         matches.add("episode")
        #
        #     results.append(SubtitleResult(
        #         provider_name=self.name,
        #         subtitle_id=str(item["id"]),
        #         language=item.get("language", "en"),
        #         format=fmt,
        #         filename=filename,
        #         download_url=item["download_url"],
        #         release_info=item.get("release_info", ""),
        #         hearing_impaired=item.get("hearing_impaired", False),
        #         matches=matches,
        #     ))

        return results

    def download(self, result: SubtitleResult) -> bytes:
        """Download a subtitle file.

        Args:
            result: A SubtitleResult from search() with download_url populated.

        Returns:
            Raw subtitle file content as bytes (UTF-8 encoded).

        Tips:
            - Handle ZIP/RAR archives: extract the subtitle file
            - The ProviderManager expects UTF-8 bytes
            - Set result.content and result.format if the download reveals
              the actual format (e.g., ZIP contains an ASS file)
        """
        if not self.session:
            raise RuntimeError(f"{self.name} not initialized")

        resp = self.session.get(result.download_url)
        resp.raise_for_status()
        content = resp.content

        # --- Handle archives if your provider returns ZIPs ---

        # import zipfile
        # import io
        # if content[:4] == b'PK\x03\x04':
        #     with zipfile.ZipFile(io.BytesIO(content)) as zf:
        #         for name in zf.namelist():
        #             if name.endswith(('.srt', '.ass', '.ssa')):
        #                 content = zf.read(name)
        #                 # Update format based on actual file
        #                 if name.endswith('.ass') or name.endswith('.ssa'):
        #                     result.format = SubtitleFormat.ASS
        #                 elif name.endswith('.srt'):
        #                     result.format = SubtitleFormat.SRT
        #                 break

        result.content = content
        return content

    def health_check(self) -> tuple[bool, str]:
        """Check if the provider is reachable (optional override).

        Returns:
            (is_healthy, message) tuple.
            Default implementation returns (True, "OK").
        """
        if not self.session:
            return False, "Not initialized (missing API key?)"
        try:
            resp = self.session.get(f"{self.base_url}/health", timeout=5)
            return resp.status_code == 200, f"HTTP {resp.status_code}"
        except Exception as e:
            return False, str(e)
