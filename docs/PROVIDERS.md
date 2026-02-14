# Subtitle Provider System

This document describes how Sublarr's subtitle provider system works and how to add new providers.

## Table of Contents

- [Overview](#overview)
- [Existing Providers](#existing-providers)
- [Provider Architecture](#provider-architecture)
- [Scoring System](#scoring-system)
- [Adding a New Provider](#adding-a-new-provider)
- [Provider Best Practices](#provider-best-practices)
- [Testing Providers](#testing-providers)

## Overview

Sublarr uses a modular provider system to search and download subtitles from multiple sources. Each provider is an independent module that implements a standard interface, allowing the system to treat all providers uniformly while supporting their unique APIs and features.

**Key Features**
- Multiple providers searched in parallel
- Priority-based ordering (configurable)
- Automatic fallback on failure
- Result scoring and ranking
- Provider health monitoring
- HTTP session management with retry logic
- Cache system for search results

## Existing Providers

Sublarr includes four built-in providers, each with different strengths:

### 1. AnimeTosho

**Best for**: Fansub ASS subtitles from release groups

**Characteristics**
- No authentication required
- Specializes in anime subtitles
- High-quality ASS format from fansubs
- Extracts subtitles from full release torrents
- XZ-compressed subtitle archives
- Feed API (JSON format)
- Uses AniDB episode IDs for matching

**API Details**
- Endpoint: `https://feed.animetosho.org/json`
- Rate limit: None (public feed)
- Archive formats: XZ, ZIP, RAR
- Returns: Torrent metadata with subtitle info

**Configuration**
```env
# No API key needed
SUBLARR_PROVIDER_PRIORITIES=animetosho,jimaku,opensubtitles,subdl
```

**Strengths**
- Excellent ASS quality from fansub groups
- No rate limits or authentication
- Good coverage for popular anime

**Limitations**
- Anime-focused only (no live action)
- Requires parsing release names
- May have delays for new episodes

### 2. Jimaku

**Best for**: Anime subtitles with AniList integration

**Characteristics**
- Requires API key
- Anime-specialized
- Integrates with AniList for metadata
- ZIP/RAR archives common
- Good Japanese subtitle coverage
- Supports multiple languages

**API Details**
- Endpoint: `https://jimaku.cc/api/`
- Rate limit: Moderate (unspecified)
- Authentication: API key in header
- Archive formats: ZIP, RAR
- Uses: AniList IDs for series matching

**Configuration**
```env
SUBLARR_JIMAKU_API_KEY=your_api_key_here
```

**Obtaining API Key**
1. Register at https://jimaku.cc
2. Go to Account Settings
3. Generate API token

**Strengths**
- Excellent anime coverage
- AniList integration improves matching
- Active community contributions

**Limitations**
- Anime only
- API key required
- Moderate rate limits

### 3. OpenSubtitles

**Best for**: Broad coverage of all media types

**Characteristics**
- Requires API key (v2 REST API)
- Largest subtitle database
- Supports movies, TV shows, anime
- Both ASS and SRT formats
- Quality varies (user-submitted)
- Login increases download limits

**API Details**
- Endpoint: `https://api.opensubtitles.com/api/v1/`
- Rate limit: 5 requests/second
- Authentication: API key + optional login
- Download limit: 200/day (logged out), 1000/day (logged in)
- Uses: File hash, IMDB ID, episode matching

**Configuration**
```env
SUBLARR_OPENSUBTITLES_API_KEY=your_api_key_here
SUBLARR_OPENSUBTITLES_USERNAME=your_username
SUBLARR_OPENSUBTITLES_PASSWORD=your_password
```

**Obtaining API Key**
1. Register at https://www.opensubtitles.com
2. Apply for API key at https://www.opensubtitles.com/en/consumers
3. Wait for approval (usually 1-2 days)

**Strengths**
- Massive database (millions of subtitles)
- Excellent file hash matching
- Supports all media types
- Multiple languages

**Limitations**
- API key approval required
- Rate limits and download quotas
- Quality inconsistent (user-submitted)
- Login recommended for higher limits

### 4. SubDL

**Best for**: Subscene successor with broad coverage

**Characteristics**
- Requires API key
- Subscene spiritual successor (launched May 2024)
- Movies, TV shows, anime
- ZIP archive downloads
- Good quality curation
- 2000 downloads/day limit

**API Details**
- Endpoint: `https://api.subdl.com/api/v1/`
- Rate limit: Moderate (unspecified)
- Authentication: API key in header
- Archive format: ZIP
- Uses: IMDB ID, TMDB ID, title matching

**Configuration**
```env
SUBLARR_SUBDL_API_KEY=your_api_key_here
```

**Obtaining API Key**
1. Register at https://subdl.com
2. Go to API section in settings
3. Generate API key

**Strengths**
- Curated quality subtitles
- Good coverage for movies and TV
- Subscene community migration
- High daily limit

**Limitations**
- Relatively new service
- API key required
- Download quota enforced

## Provider Architecture

### Core Classes

**SubtitleProvider (Abstract Base Class)**

Located in `backend/providers/base.py`, this defines the interface all providers must implement.

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

@dataclass
class VideoQuery:
    """Query parameters for subtitle search"""
    series: Optional[str] = None
    season: Optional[int] = None
    episode: Optional[int] = None
    year: Optional[int] = None
    movie_title: Optional[str] = None
    language: str = "en"
    file_path: Optional[Path] = None
    file_hash: Optional[str] = None
    imdb_id: Optional[str] = None
    tvdb_id: Optional[str] = None
    anilist_id: Optional[str] = None

@dataclass
class SubtitleResult:
    """Subtitle search result from a provider"""
    provider: str
    language: str
    format: str  # "ass" or "srt"
    download_url: str
    score: int = 0
    release_info: Optional[str] = None
    hearing_impaired: bool = False
    file_hash: Optional[str] = None

class SubtitleProvider(ABC):
    """Base class for all subtitle providers"""

    def __init__(self, config):
        self.config = config
        self.session = RetryingSession()

    @abstractmethod
    def search(self, query: VideoQuery) -> List[SubtitleResult]:
        """Search for subtitles matching the query"""
        pass

    @abstractmethod
    def download(self, result: SubtitleResult, dest: Path) -> Path:
        """Download subtitle file to destination"""
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """Check if provider is accessible and working"""
        pass

    def score_result(self, result: SubtitleResult, query: VideoQuery) -> int:
        """Calculate match score for a result"""
        # Implemented in base class with standard algorithm
        pass
```

**ProviderManager (Singleton)**

Located in `backend/providers/__init__.py`, this orchestrates all providers.

```python
class ProviderManager:
    """Manages all subtitle providers"""

    def __init__(self, config):
        self.config = config
        self.providers = {}
        self._init_providers()

    def _init_providers(self):
        """Initialize enabled providers based on config"""
        priorities = self.config.provider_priorities
        enabled = self.config.providers_enabled

        for name in priorities:
            if not enabled or name in enabled:
                provider_class = PROVIDER_REGISTRY.get(name)
                if provider_class:
                    self.providers[name] = provider_class(self.config)

    def search(self, query: VideoQuery) -> List[SubtitleResult]:
        """Search all providers and return scored results"""
        all_results = []

        for name, provider in self.providers.items():
            try:
                results = provider.search(query)
                for result in results:
                    result.score = provider.score_result(result, query)
                all_results.extend(results)
            except Exception as e:
                logger.error(f"Provider {name} search failed: {e}")

        # Sort by score (highest first)
        all_results.sort(key=lambda r: r.score, reverse=True)
        return all_results

    def download_best(self, query: VideoQuery, dest: Path) -> Optional[Path]:
        """Search, find best result, and download it"""
        results = self.search(query)
        if not results:
            return None

        best = results[0]
        provider = self.providers[best.provider]
        return provider.download(best, dest)
```

**RetryingSession**

Located in `backend/providers/http_session.py`, this handles HTTP requests with retry logic and rate-limit awareness.

```python
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class RetryingSession(requests.Session):
    """HTTP session with automatic retry and rate-limit handling"""

    def __init__(self):
        super().__init__()

        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            method_whitelist=["HEAD", "GET", "OPTIONS", "POST"]
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.mount("http://", adapter)
        self.mount("https://", adapter)

    def request(self, method, url, **kwargs):
        """Override request to add rate-limit handling"""
        response = super().request(method, url, **kwargs)

        # If rate limited, wait and retry
        if response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 60))
            logger.warning(f"Rate limited, waiting {retry_after}s")
            time.sleep(retry_after)
            response = super().request(method, url, **kwargs)

        return response
```

## Scoring System

The scoring system ranks subtitle results to select the best match. Scores are cumulative, with higher scores indicating better matches.

### Score Weights

Based on Bazarr/subliminal scoring system:

| Match Type | Weight | Description |
|------------|--------|-------------|
| **File Hash** | 359 | Exact file hash match (OpenSubtitles) |
| **Series/Movie** | 180 | Series or movie title match |
| **Year** | 90 | Release year match |
| **Season** | 30 | Season number match (TV shows) |
| **Episode** | 30 | Episode number match (TV shows) |
| **Release Group** | 14 | Release group name match |
| **Source** | 7 | Video source (BluRay, WEB, etc.) |
| **Resolution** | 2 | Video resolution (1080p, 720p, etc.) |
| **Format Bonus** | 50 | ASS format bonus (Sublarr-specific) |

### Scoring Algorithm

```python
def score_result(self, result: SubtitleResult, query: VideoQuery) -> int:
    """Calculate match score for a result"""
    score = 0

    # File hash match (highest priority)
    if result.file_hash and query.file_hash:
        if result.file_hash == query.file_hash:
            score += 359

    # Series/movie title match
    if query.series and result.release_info:
        if query.series.lower() in result.release_info.lower():
            score += 180
    elif query.movie_title and result.release_info:
        if query.movie_title.lower() in result.release_info.lower():
            score += 180

    # Year match
    if query.year and result.release_info:
        if str(query.year) in result.release_info:
            score += 90

    # Season/episode match
    if query.season is not None and result.release_info:
        if f"S{query.season:02d}" in result.release_info.upper():
            score += 30
    if query.episode is not None and result.release_info:
        if f"E{query.episode:02d}" in result.release_info.upper():
            score += 30

    # Release group, source, resolution parsing
    # (extract from release_info and compare)

    # ASS format bonus (Sublarr-specific)
    if result.format.lower() == "ass":
        score += 50

    return score
```

### Why ASS Gets +50 Bonus

For anime, ASS format is superior because:
- Preserves styling and positioning
- Supports complex typesetting
- Handles signs and songs
- Maintains fansub quality

Sublarr prioritizes ASS to deliver the best possible anime subtitle experience, unlike Bazarr which treats ASS as just another format.

## Adding a New Provider

Follow these steps to add a new subtitle provider to Sublarr.

### Step 1: Create Provider Module

Create a new file in `backend/providers/` named after your provider (e.g., `backend/providers/newprovider.py`).

```python
from typing import List, Optional
from pathlib import Path
import logging

from .base import SubtitleProvider, VideoQuery, SubtitleResult
from .http_session import RetryingSession

logger = logging.getLogger(__name__)

class NewProviderProvider(SubtitleProvider):
    """Subtitle provider for NewProvider.com"""

    def __init__(self, config):
        super().__init__(config)
        self.api_key = config.newprovider_api_key
        self.base_url = "https://api.newprovider.com/v1"
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}"
        })

    def search(self, query: VideoQuery) -> List[SubtitleResult]:
        """Search NewProvider for subtitles"""
        if not self.api_key:
            logger.warning("NewProvider API key not configured")
            return []

        try:
            # Build API request
            params = {
                "query": query.series or query.movie_title,
                "language": query.language,
            }
            if query.season:
                params["season"] = query.season
            if query.episode:
                params["episode"] = query.episode

            # Make API call
            response = self.session.get(
                f"{self.base_url}/search",
                params=params,
                timeout=10
            )
            response.raise_for_status()
            data = response.json()

            # Parse results
            results = []
            for item in data.get("results", []):
                result = SubtitleResult(
                    provider="newprovider",
                    language=item["language"],
                    format=item["format"],  # "ass" or "srt"
                    download_url=item["download_url"],
                    release_info=item.get("release_name"),
                    hearing_impaired=item.get("hearing_impaired", False)
                )
                results.append(result)

            logger.info(f"NewProvider found {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"NewProvider search error: {e}")
            return []

    def download(self, result: SubtitleResult, dest: Path) -> Path:
        """Download subtitle from NewProvider"""
        try:
            response = self.session.get(
                result.download_url,
                timeout=30,
                stream=True
            )
            response.raise_for_status()

            # Handle different content types
            content_type = response.headers.get("content-type", "")

            if "zip" in content_type:
                # Extract from ZIP
                return self._extract_from_zip(response.content, dest)
            else:
                # Direct subtitle file
                dest.write_bytes(response.content)
                return dest

        except Exception as e:
            logger.error(f"NewProvider download error: {e}")
            raise

    def health_check(self) -> bool:
        """Check if NewProvider API is accessible"""
        try:
            response = self.session.get(
                f"{self.base_url}/health",
                timeout=5
            )
            return response.status_code == 200
        except Exception:
            return False

    def _extract_from_zip(self, content: bytes, dest: Path) -> Path:
        """Extract subtitle from ZIP archive"""
        import zipfile
        import io

        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            # Find subtitle file in archive
            for name in zf.namelist():
                if name.endswith((".ass", ".srt")):
                    subtitle_data = zf.read(name)
                    dest.write_bytes(subtitle_data)
                    return dest

        raise ValueError("No subtitle found in ZIP archive")
```

### Step 2: Add Configuration Settings

Edit `backend/config.py` to add settings for your provider:

```python
class Settings(BaseSettings):
    # ... existing settings ...

    # NewProvider settings
    newprovider_api_key: Optional[str] = None
    newprovider_enabled: bool = True

    class Config:
        env_prefix = "SUBLARR_"
        env_file = ".env"
```

### Step 3: Register Provider

Edit `backend/providers/__init__.py` to register your provider:

```python
from .opensubtitles import OpenSubtitlesProvider
from .jimaku import JimakuProvider
from .animetosho import AnimeToshoProvider
from .subdl import SubDLProvider
from .newprovider import NewProviderProvider  # Add import

PROVIDER_REGISTRY = {
    "animetosho": AnimeToshoProvider,
    "jimaku": JimakuProvider,
    "opensubtitles": OpenSubtitlesProvider,
    "subdl": SubDLProvider,
    "newprovider": NewProviderProvider,  # Add to registry
}
```

### Step 4: Update Environment Example

Add your provider settings to `.env.example`:

```env
# NewProvider configuration
SUBLARR_NEWPROVIDER_API_KEY=
SUBLARR_NEWPROVIDER_ENABLED=true

# Provider priorities (order matters)
SUBLARR_PROVIDER_PRIORITIES=animetosho,jimaku,newprovider,opensubtitles,subdl
```

### Step 5: Add Documentation

Update this file (PROVIDERS.md) with your provider's details:
- Add to [Existing Providers](#existing-providers) section
- Document API details, rate limits, authentication
- Provide instructions for obtaining API keys
- List strengths and limitations

## Provider Best Practices

### API Keys and Authentication

**DO:**
- Store API keys in config, never hardcode
- Support optional authentication where possible
- Check for API key presence before making requests
- Return empty results if auth is missing (don't crash)

**DON'T:**
- Log API keys or tokens
- Commit API keys to git
- Hardcode API endpoints (use config)

### Error Handling

**DO:**
- Catch and log all exceptions
- Return empty list on search failure (not raise)
- Use descriptive error messages
- Implement graceful degradation

**DON'T:**
- Let exceptions propagate (breaks provider manager)
- Hide errors silently (always log)
- Retry forever (respect timeouts)

### Rate Limiting

**DO:**
- Use RetryingSession for automatic retry
- Respect Retry-After headers
- Implement exponential backoff
- Log rate limit events

**DON'T:**
- Ignore rate limits (will get banned)
- Retry immediately after 429 error
- Make parallel requests to same provider

### Archive Handling

**DO:**
- Support ZIP, RAR, XZ formats
- Extract subtitle files automatically
- Prefer ASS over SRT if both present
- Clean up temporary files

**DON'T:**
- Assume single file in archive
- Extract all files blindly (security risk)
- Leave temp files on disk

### Performance

**DO:**
- Use connection pooling (RetryingSession)
- Set reasonable timeouts (5-30 seconds)
- Stream large downloads
- Cache search results

**DON'T:**
- Make synchronous requests in loops
- Download entire archive to memory
- Retry indefinitely on timeout

### Code Quality

**DO:**
- Follow Python PEP 8 style
- Use type hints
- Write docstrings
- Add unit tests

**DON'T:**
- Mix concerns (keep search/download separate)
- Use global variables
- Write overly complex logic

## Testing Providers

### Unit Tests

Create tests in `backend/tests/test_providers.py`:

```python
import pytest
from providers.newprovider import NewProviderProvider
from providers.base import VideoQuery

@pytest.fixture
def provider(mocker):
    """Mock provider with API key"""
    config = mocker.Mock()
    config.newprovider_api_key = "test_key"
    return NewProviderProvider(config)

def test_search_series(provider, mocker):
    """Test searching for a TV series"""
    # Mock HTTP response
    mock_response = {
        "results": [
            {
                "language": "en",
                "format": "ass",
                "download_url": "https://example.com/sub.ass",
                "release_name": "Series.S01E01.1080p"
            }
        ]
    }
    mocker.patch.object(
        provider.session,
        'get',
        return_value=mocker.Mock(
            status_code=200,
            json=lambda: mock_response
        )
    )

    # Perform search
    query = VideoQuery(
        series="Test Series",
        season=1,
        episode=1,
        language="en"
    )
    results = provider.search(query)

    # Verify results
    assert len(results) == 1
    assert results[0].provider == "newprovider"
    assert results[0].format == "ass"

def test_search_no_api_key():
    """Test that search fails gracefully without API key"""
    config = mocker.Mock()
    config.newprovider_api_key = None
    provider = NewProviderProvider(config)

    query = VideoQuery(series="Test", language="en")
    results = provider.search(query)

    assert results == []

def test_health_check(provider, mocker):
    """Test provider health check"""
    mocker.patch.object(
        provider.session,
        'get',
        return_value=mocker.Mock(status_code=200)
    )

    assert provider.health_check() is True
```

### Integration Tests

**Manual Testing**

Test against the real API (use test API key):

```python
# test_integration.py (not in automated suite)
from providers.newprovider import NewProviderProvider
from config import get_config

def test_real_search():
    """Manual test against real API"""
    config = get_config()
    provider = NewProviderProvider(config)

    query = VideoQuery(
        series="Attack on Titan",
        season=1,
        episode=1,
        language="en"
    )

    results = provider.search(query)
    print(f"Found {len(results)} results")
    for r in results:
        print(f"  - {r.format} from {r.provider}: {r.release_info}")

if __name__ == "__main__":
    test_real_search()
```

**API Endpoint Testing**

Use the built-in test endpoint:

```bash
curl -X POST http://localhost:5765/api/v1/providers/test/newprovider \
  -H "X-Api-Key: your-api-key"
```

### Debugging

**Enable Debug Logging**

```env
SUBLARR_LOG_LEVEL=DEBUG
```

**Check Provider Status**

```bash
curl http://localhost:5765/api/v1/providers \
  -H "X-Api-Key: your-api-key"
```

**View Provider Stats**

```bash
curl http://localhost:5765/api/v1/providers/stats \
  -H "X-Api-Key: your-api-key"
```

## Provider Roadmap

Potential future providers to consider:

- **Addic7ed**: TV show subtitles (requires scraping, no official API)
- **Podnapisi**: Large database (free API available)
- **Subscene**: Popular but no official API (scraping required)
- **Napisy24**: Polish subtitles (scraping required)
- **Argenteam**: Spanish/Latin American subtitles (API available)
- **Shooter**: Chinese subtitles (API available)

If you implement any of these, please contribute back to the project!

## Questions?

- Open a GitHub Issue for provider-related questions
- Check the API documentation for the target provider
- Review existing provider implementations as examples
- Test thoroughly before submitting a pull request

Thank you for contributing to Sublarr!
