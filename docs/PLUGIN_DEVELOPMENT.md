# Plugin Development Guide

This guide explains how to develop plugins for Sublarr, including provider plugins, translation backends, and utility tools.

## Table of Contents

1. [Plugin Architecture](#plugin-architecture)
2. [Creating a Provider Plugin](#creating-a-provider-plugin)
3. [Creating a Translation Backend](#creating-a-translation-backend)
4. [Plugin Structure](#plugin-structure)
5. [API Reference](#api-reference)
6. [Best Practices](#best-practices)
7. [Testing](#testing)
8. [Publishing](#publishing)

## Plugin Architecture

Sublarr uses a plugin system that allows developers to extend functionality without modifying the core codebase. Plugins are Python modules that implement specific interfaces.

### Plugin Types

- **Provider Plugins**: Add new subtitle sources (e.g., custom websites, APIs)
- **Translation Backends**: Add new translation services (e.g., custom LLM APIs)
- **Tool Plugins**: Add utility functions (e.g., custom scoring, post-processing)

### Plugin Discovery

Plugins are discovered automatically from:
- Built-in plugins: `backend/providers/plugins/`
- User plugins: `/config/plugins/` (configurable)

## Creating a Provider Plugin

### Basic Structure

```python
from providers.base import SubtitleProvider, SubtitleResult

class MyProvider(SubtitleProvider):
    """My custom subtitle provider."""
    
    name = "MyProvider"
    priority = 100
    enabled = True
    
    def search(self, query):
        """Search for subtitles.
        
        Args:
            query: SearchQuery object with file_path, series_title, etc.
            
        Returns:
            List of SubtitleResult objects
        """
        results = []
        # Your search logic here
        return results
    
    def download(self, subtitle_id, file_path):
        """Download subtitle file.
        
        Args:
            subtitle_id: Provider-specific subtitle identifier
            file_path: Target file path
            
        Returns:
            Path to downloaded file
        """
        # Your download logic here
        return file_path
```

### Required Methods

- `search(query)`: Search for subtitles matching the query
- `download(subtitle_id, file_path)`: Download a specific subtitle

### Optional Methods

- `test()`: Test provider connectivity/credentials
- `get_config()`: Return provider configuration schema
- `validate_config(config)`: Validate configuration

### Example: Simple Provider

```python
import requests
from providers.base import SubtitleProvider, SubtitleResult

class ExampleProvider(SubtitleProvider):
    name = "ExampleProvider"
    priority = 50
    
    def __init__(self):
        super().__init__()
        self.api_key = self.get_setting("api_key", "")
    
    def search(self, query):
        if not self.api_key:
            return []
        
        # Make API request
        response = requests.get(
            "https://api.example.com/search",
            params={
                "title": query.series_title,
                "season": query.season,
                "episode": query.episode,
            },
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        
        results = []
        for item in response.json().get("results", []):
            results.append(SubtitleResult(
                provider=self.name,
                subtitle_id=item["id"],
                language=item["language"],
                format=item["format"],
                score=self._calculate_score(item, query),
                download_url=item["download_url"],
            ))
        
        return results
    
    def download(self, subtitle_id, file_path):
        response = requests.get(
            f"https://api.example.com/download/{subtitle_id}",
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        
        with open(file_path, "wb") as f:
            f.write(response.content)
        
        return file_path
    
    def _calculate_score(self, item, query):
        score = 100
        # Custom scoring logic
        if item.get("hash") == query.file_hash:
            score += 200
        return score
```

## Creating a Translation Backend

Translation backends implement the `TranslationBackend` interface:

```python
from translation.base import TranslationBackend

class MyTranslationBackend(TranslationBackend):
    """My custom translation backend."""
    
    name = "MyTranslation"
    supports_streaming = False
    
    def translate(self, text, source_lang, target_lang, context=None):
        """Translate text.
        
        Args:
            text: Source text to translate
            source_lang: Source language code (e.g., "en")
            target_lang: Target language code (e.g., "de")
            context: Optional context (e.g., glossary entries)
            
        Returns:
            Translated text
        """
        # Your translation logic here
        return translated_text
    
    def test(self):
        """Test backend connectivity."""
        try:
            result = self.translate("test", "en", "de")
            return True, "Backend is working"
        except Exception as e:
            return False, str(e)
```

## Plugin Structure

### Directory Layout

```
my-plugin/
├── __init__.py          # Plugin entry point
├── provider.py          # Provider implementation (if provider plugin)
├── translation.py       # Translation backend (if translation plugin)
├── README.md            # Plugin documentation
├── config.json          # Plugin metadata
└── requirements.txt     # Python dependencies (optional)
```

### `__init__.py` Example

```python
"""My Plugin - A custom subtitle provider."""

from .provider import MyProvider

# Export the provider class
__all__ = ["MyProvider"]
```

### `config.json` Example

```json
{
  "name": "my-plugin",
  "version": "1.0.0",
  "description": "My custom subtitle provider",
  "author": "Your Name",
  "type": "provider",
  "category": "provider",
  "url": "https://github.com/username/my-plugin",
  "license": "MIT"
}
```

## API Reference

### SubtitleProvider Base Class

```python
class SubtitleProvider:
    name: str                    # Provider name (required)
    priority: int = 100          # Search priority (lower = higher priority)
    enabled: bool = True         # Whether provider is enabled
    
    def search(self, query: SearchQuery) -> List[SubtitleResult]:
        """Search for subtitles."""
        pass
    
    def download(self, subtitle_id: str, file_path: str) -> str:
        """Download subtitle file."""
        pass
    
    def test(self) -> Tuple[bool, str]:
        """Test provider connectivity."""
        return True, "OK"
    
    def get_setting(self, key: str, default=None):
        """Get provider setting."""
        pass
```

### SearchQuery Object

```python
class SearchQuery:
    file_path: str               # Path to video file
    file_hash: str               # Video file hash
    series_title: str            # Series title
    season: int                  # Season number
    episode: int                 # Episode number
    year: int                    # Release year
    release_group: str           # Release group name
    source_lang: str             # Source language code
    target_lang: str             # Target language code
```

### SubtitleResult Object

```python
class SubtitleResult:
    provider: str                 # Provider name
    subtitle_id: str             # Provider-specific ID
    language: str                 # Language code
    format: str                   # Format (ass, srt, etc.)
    score: int                   # Quality score (0-1000+)
    download_url: str             # Direct download URL (optional)
    metadata: dict                # Additional metadata
```

## Best Practices

### 1. Error Handling

Always handle errors gracefully:

```python
def search(self, query):
    try:
        # Your search logic
        return results
    except requests.RequestException as e:
        logger.error(f"{self.name} search failed: {e}")
        return []
    except Exception as e:
        logger.exception(f"{self.name} unexpected error")
        return []
```

### 2. Rate Limiting

Respect rate limits and use the built-in session:

```python
def search(self, query):
    # Use self.session which has rate limiting built-in
    response = self.session.get(url, timeout=10)
    return results
```

### 3. Caching

Use the provider cache for expensive operations:

```python
def search(self, query):
    cache_key = f"{self.name}:{query.file_hash}"
    cached = self.get_cache(cache_key)
    if cached:
        return cached
    
    results = self._do_search(query)
    self.set_cache(cache_key, results, ttl=3600)
    return results
```

### 4. Configuration

Make your plugin configurable:

```python
def __init__(self):
    super().__init__()
    self.api_key = self.get_setting("api_key", "")
    self.timeout = self.get_setting("timeout", 10)
    self.max_results = self.get_setting("max_results", 50)
```

### 5. Logging

Use the logger for debugging:

```python
import logging

logger = logging.getLogger(__name__)

def search(self, query):
    logger.debug(f"Searching {self.name} for {query.series_title}")
    # Your logic
    logger.info(f"Found {len(results)} results")
    return results
```

## Testing

### Unit Tests

Create tests for your plugin:

```python
import pytest
from my_plugin import MyProvider

def test_provider_search():
    provider = MyProvider()
    query = SearchQuery(
        file_path="/test/video.mkv",
        series_title="Test Series",
        season=1,
        episode=1,
    )
    results = provider.search(query)
    assert len(results) > 0
    assert results[0].provider == "MyProvider"
```

### Integration Tests

Test with real API calls (use test credentials):

```python
def test_provider_download():
    provider = MyProvider()
    provider.api_key = "test_key"
    
    result = provider.download("test_id", "/tmp/test.srt")
    assert os.path.exists(result)
```

## Publishing

### 1. Create GitHub Repository

- Repository name: `sublarr-{plugin-name}`
- Include README with installation instructions
- Add license file

### 2. Submit to Marketplace

Create a pull request to the [Sublarr Community Plugins](https://github.com/sublarr-community/plugins) repository:

1. Fork the repository
2. Add your plugin to `registry.json`
3. Create pull request

### 3. Registry Entry

```json
{
  "name": "my-plugin",
  "version": "1.0.0",
  "description": "My custom subtitle provider",
  "author": "Your Name",
  "category": "provider",
  "url": "https://github.com/username/my-plugin",
  "install_url": "https://github.com/username/my-plugin.git",
  "license": "MIT"
}
```

## Examples

See the built-in plugins in `backend/providers/plugins/` for reference implementations:

- `template/` - Template plugin with all features
- `opensubtitles/` - OpenSubtitles.com provider
- `jimaku/` - Jimaku anime provider

## Support

- GitHub Issues: [Sublarr Issues](https://github.com/Abrechen2/sublarr/issues)
- Discord: [Sublarr Discord](https://discord.gg/sublarr)
- Documentation: [Sublarr Docs](https://docs.sublarr.app)
