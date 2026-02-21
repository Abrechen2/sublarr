# Backend — Flask API

Flask-App auf Port 5765. Blueprint-Architektur, alle Routes unter `/api/v1/`.

## Schlüsseldateien

| Datei | Rolle |
|-------|-------|
| `app.py` | Flask-App-Factory (`create_app()`), Blueprint-Registrierung |
| `config.py` | Pydantic Settings (`SUBLARR_`-Prefix), `get_settings()` Singleton |
| `database.py` | SQLite WAL-Mode, `_db_lock` (threading.Lock), 17+ Tabellen |
| `translator.py` | Drei-Stufen-Pipeline → @backend/translation/CLAUDE.md |
| `wanted_scanner.py` | Fehlende Subs erkennen, Scheduler (6h-Zyklus) |
| `wanted_search.py` | Provider-Suche + Download fuer Wanted-Items |
| `auth.py` | Optionale API-Key-Auth (`X-Api-Key` Header) |
| `error_handler.py` | SublarrError-Hierarchie + Flask-Error-Handler + Request-IDs |
| `circuit_breaker.py` | CLOSED/OPEN/HALF_OPEN per Provider |

## Routes (`backend/routes/`)

```
providers.py   GET /providers, POST /providers/test/<name>, /providers/search
translate.py   POST /translate, /translate/sync, GET /status/<id>, /jobs
library.py     GET /library, /stats
wanted.py      POST /wanted/<id>/search, /wanted/<id>/process, /wanted/batch-search
config.py      GET|PUT /config
profiles.py    GET|POST /language-profiles, PUT|DELETE /language-profiles/<id>
webhooks.py    POST /webhook/sonarr, /webhook/radarr
system.py      GET /health, /logs  +  WS /socket.io/
```

## Wichtige Muster

**DB-Zugriff immer mit Lock:**
```python
with _db_lock:
    conn = get_db()
    # ... query
```

**Optional-Settings lesen** (fehlertolerantes Pattern):
```python
getattr(self.settings, "field_name", default_value)
```

**Fehlerbehandlung:** SublarrError-Subklassen werfen, GlobalErrorHandler fängt ab und gibt strukturiertes JSON zurück.

**Media-Server:** `backend/mediaserver/` — Jellyfin, Emby, Plex, Kodi (Manager-Pattern)

**Language Profiles:** Pro Serie/Film, mehrere Zielsprachen, Default `en→de` aus globaler Config.
