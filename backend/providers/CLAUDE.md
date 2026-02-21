# Providers — Subtitle Provider System

## Provider-Übersicht

| Provider | Auth | Format | Besonderheit |
|----------|------|--------|-------------|
| animetosho | kein Key | ASS (XZ) | Feed-API, Fansub-Releases |
| jimaku | API-Key | ZIP/RAR | Anime, AniList-ID |
| opensubtitles | API-Key + Login | SRT/ASS | 5 req/s Limit, REST v2 |
| subdl | API-Key | ZIP | 2000 DL/Tag |
| gestdown | kein Key | SRT | Gestdown.eu |
| podnapisi | kein Key | SRT | Osteuropa |
| kitsunekko | kein Key | ASS | Japanische Originalsprache |
| napisy24 | kein Key | SRT | Polnisch |
| titrari | kein Key | SRT | Rumaenisch |
| legendasdivx | kein Key | SRT | Portugiesisch |

## Scoring-Formel

```
hash_match     +359
series_match   +180
year_match     +90
season_match   +30
episode_match  +30
release_group  +14
ASS-Format     +50   ← wichtig: ASS vor SRT bevorzugen
```

## Schlüsseldateien

- `__init__.py` — `ProviderManager` (Singleton), parallele Suche via `ThreadPoolExecutor`, Circuit Breaker
- `base.py` — `SubtitleProvider` ABC, `VideoQuery`, `SubtitleResult`
- `http_session.py` — `RetryingSession` mit automatischem Rate-Limit-Handling (Retry-After-Header)

## Circuit Breaker

States: `CLOSED` (normal) → `OPEN` (nach N Fehlern) → `HALF_OPEN` (Test-Request) → zurück zu CLOSED.
Implementierung in `backend/circuit_breaker.py`.

## health_check() Pattern

Jeder Provider implementiert `health_check() -> tuple[bool, str]`.
Gibt `(True, "OK")` oder `(False, "Fehlermeldung")` zurueck.
API-Endpunkt: `POST /api/v1/providers/test/<name>` → Antwort in `result["health_check"]["healthy"]`.

## Download-Flow

1. `ProviderManager.search()` → parallele Suche, Ergebnisse gerankt
2. Bestes Ergebnis auswaehlen (hoechster Score)
3. `provider.download(subtitle_id)` → Bytes
4. Entpacken (ZIP/RAR/XZ) via `backend/utils`
5. In Media-Verzeichnis schreiben als `{name}.{lang}.ass`
