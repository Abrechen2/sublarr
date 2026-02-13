# CCAnimeTranslator - Anime Subtitle Translation Service

> **Teil des DIYHaus Hub** — Gesamtarchitektur und Netzwerk-Topologie siehe `../CLAUDE.md`

## Zweck

Automatische Uebersetzung von Anime-Untertiteln (Englisch → Deutsch) mittels Ollama LLM.
Unterstuetzt ASS und SRT Formate. Arbeitet mit Bazarr zusammen: Bazarr ist primaere Quelle
fuer professionelle Untertitel, AnimeTranslator uebernimmt als AI-Fallback wenn keine
deutschen ASS-Untertitel verfuegbar sind.

**Primaerziel:** Deutsche ASS-Untertitel fuer jede Anime-Episode.

## Abhaengigkeiten zu anderen Subsystemen

- **CCCardinal:** Container laeuft auf Cardinal (Docker), Medien-Bibliothek liegt auf Cardinal Array
- **Mac mini (Ollama):** LLM-Backend fuer die Uebersetzung (qwen2.5:14b-instruct als `anime-translator`)
- **Bazarr (Cardinal):** Primaere Untertitel-Quelle, Profil 3 "Anime" (de+en), Provider: animetosho, jimaku
- **Sonarr (Cardinal):** Serien-Management, 61 Anime-Serien
- **n8n (Cardinal):** Orchestrierung via Cron-Workflow (alle 4 Stunden)

---

## Drei-Stufen Prioritaetskette

```
MKV-Datei eingehend
  │
  ├─ Fall A: Deutscher ASS vorhanden → SKIP (Ziel erreicht)
  │
  ├─ Fall B: Deutscher SRT vorhanden → UPGRADE-Versuch
  │   ├─ B1: Bazarr sucht deutschen ASS bei Providern → gefunden? DONE
  │   ├─ B2: Englischer ASS embedded → uebersetze zu .de.ass → DONE
  │   └─ B3: Kein Upgrade moeglich → SRT behalten (akzeptabel)
  │
  └─ Fall C: Kein deutscher Untertitel → Volle Pipeline
      ├─ C1: Englischer ASS embedded → uebersetze zu .de.ass → DONE
      ├─ C2: Englischer SRT embedded → uebersetze zu .de.srt → DONE
      ├─ C3: Bazarr holt englischen Sub → uebersetze zu .de.srt → DONE
      └─ C4: Nichts verfuegbar → FAIL (Log + Skip)
```

---

## Architektur

```
                    ┌─────────────┐
                    │  n8n Cron   │ (alle 4h)
                    │  Workflow   │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐         ┌──────────────┐
                    │  Health     │────────►│  Pushover    │ (bei Fehler)
                    │  Check      │         │  Alert       │
                    └──────┬──────┘         └──────────────┘
                           │ OK
                    ┌──────▼──────┐
                    │  Bazarr     │ Wanted-List (anime-tagged)
                    │  API        │
                    └──────┬──────┘
                           │
               ┌───────────▼───────────┐
               │  AnimeTranslator      │
               │  /translate/sync      │
               │                       │
               │  detect_existing_     │
               │  german() → A/B/C    │
               └───────┬───────────────┘
                       │
          ┌────────────┼────────────┐
          │            │            │
    ┌─────▼─────┐ ┌───▼────┐ ┌───▼────────┐
    │ Bazarr    │ │ ffmpeg │ │ Ollama     │
    │ search/   │ │ extract│ │ translate  │
    │ fetch     │ │ stream │ │ (Mac mini) │
    └─────┬─────┘ └───┬────┘ └───┬────────┘
          │           │           │
          └────────┬──┘───────────┘
                   │
            ┌──────▼──────┐
            │ .de.ass /   │ + Bazarr scan-disk
            │ .de.srt     │
            └─────────────┘
```

---

## Container-Details

| Parameter | Wert |
|---|---|
| **Container-Name** | `anime-sub-translator` |
| **Image** | Custom Build (Python 3.11-slim + ffmpeg) |
| **Port** | 5765 |
| **Volume** | `/mnt/user/Emby-Media:/media:rw` |
| **Restart** | unless-stopped |
| **WSGI** | gunicorn, 2 Workers, 4 Threads, 300s Timeout |
| **Host** | Cardinal (192.168.178.36) |

### Umgebungsvariablen

| Variable | Default | Beschreibung |
|---|---|---|
| `OLLAMA_URL` | `http://192.168.178.155:11434` | Mac mini Ollama API |
| `OLLAMA_MODEL` | `anime-translator` | Ollama-Modell (qwen2.5:14b-instruct) |
| `BATCH_SIZE` | `15` | Zeilen pro Uebersetzungs-Batch |
| `LOG_LEVEL` | `INFO` | Python Logging Level |
| `BAZARR_URL` | (leer) | Bazarr API URL (`http://192.168.178.36:6767`) |
| `BAZARR_API_KEY` | (leer) | Bazarr API Key |
| `SONARR_URL` | (leer) | Sonarr API URL (`http://192.168.178.36:8989`) |
| `SONARR_API_KEY` | (leer) | Sonarr API Key |

---

## API-Endpoints

| Methode | Pfad | Beschreibung |
|---|---|---|
| GET | `/health` | Health Check (Ollama + Bazarr Konnektivitaet) |
| POST | `/translate` | Async Uebersetzung (gibt job_id zurueck) |
| POST | `/translate/sync` | Synchrone Uebersetzung (wartet auf Ergebnis) |
| POST | `/translate/wanted` | Bazarr Wanted-List verarbeiten (anime only) |
| GET | `/status/<job_id>` | Job-Status abfragen |
| GET | `/status/bazarr` | Bazarr-Integration Status |
| POST | `/batch` | Batch-Verarbeitung (mit `dry_run`, Pagination, Callback) |
| GET | `/batch/status` | Batch-Fortschritt |
| GET | `/stats` | Gesamtstatistiken (inkl. Upgrades, Quality Warnings) |

### Translate mit Bazarr-Kontext
```bash
curl -X POST http://localhost:5765/translate/sync \
  -H 'Content-Type: application/json' \
  -d '{"file_path": "/media/_Anime/_Serien/Show/S01E01.mkv", "sonarr_series_id": 123, "sonarr_episode_id": 456}'
```

### Batch Dry-Run mit Pagination
```bash
curl -X POST http://localhost:5765/batch \
  -H 'Content-Type: application/json' \
  -d '{"directory": "/media/_Anime/_Serien", "dry_run": true, "page": 1, "per_page": 50}'
```

---

## Dateistruktur

```
CCAnimeTranslator/
├── CLAUDE.md              # Diese Datei
├── Dockerfile             # Python 3.11-slim + ffmpeg
├── docker-compose.yml     # Service-Definition (inkl. Bazarr/Sonarr Env)
├── Modelfile              # Ollama-Modell Definition (qwen2.5:14b-instruct)
├── .gitignore
├── .dockerignore
├── PLAN.md                # Implementierungsplan (v2)
├── app/
│   ├── requirements.txt   # flask, gunicorn, pysubs2, requests
│   ├── server.py          # Flask REST API (Endpoints, Job-Tracking, Stats)
│   ├── translator.py      # Orchestrierung (Fall A/B/C Pipeline)
│   ├── ass_utils.py       # ASS/SRT-Parsing, Stream-Selektion, Tags
│   ├── ollama_client.py   # Ollama API Client, Batching, Retries, Validation
│   └── bazarr_client.py   # Bazarr REST API Client (Search, Fetch, Scan-Disk)
└── scripts/
    └── sonarr-trigger.sh  # DEPRECATED — n8n Workflow uebernimmt Orchestrierung
```

---

## Kernkonzepte

### Drei-Stufen Prioritaetskette (translator.py)
- **Fall A:** Deutscher ASS extern vorhanden → Skip
- **Fall B:** Deutscher SRT vorhanden → Upgrade-Versuch (Bazarr ASS-Suche → eng ASS uebersetzen → SRT behalten)
- **Fall C:** Kein deutscher Sub → Volle Pipeline (eng ASS → eng SRT → Bazarr fetch → Fail)
- Bazarr-Integration ist optional (graceful degradation bei fehlender Konfiguration)

### Style-Klassifizierung (ass_utils.py)
- **Dialog-Styles:** Enthalten "default", "main", "dialogue", "italic", etc. → werden uebersetzt
- **Signs/Songs-Styles:** Enthalten "sign", "op", "ed", "song", "karaoke", etc. → bleiben original
- **Heuristik:** Styles mit >80% `\pos()`/`\move()` Tags → Signs (nicht uebersetzen)
- **Fallback:** Unbekannte Styles werden als Dialog behandelt

### ASS Override Tags
- `{...}` Bloecke (Farben, Positionen, Formatierung) werden vor der Uebersetzung extrahiert
- Nach Uebersetzung **proportional** wiederhergestellt (Wort-Boundary-Snapping)
- `\N` (Hard Line Breaks) werden durch den gesamten Pipeline-Prozess preserviert

### SRT-Uebersetzung
- HTML-Tags (`<i>`, `<b>`, etc.) werden vor Uebersetzung entfernt
- Output als `.de.srt` — keine Style-Klassifizierung noetig
- Gleiche Batch/Retry-Logik wie ASS-Uebersetzung

### Stream-Selektion (ass_utils.py — Prioritaet)
1. Stream mit "Full" im Titel (nicht Signs/Songs)
2. Erster englischer Stream im gewuenschten Format ohne "sign"/"song"
3. Erster englischer Stream im gewuenschten Format
4. Erster Stream im gewuenschten Format ohne "sign"/"song"
5. Erster Stream im gewuenschten Format ueberhaupt
- Unterstuetzt `format_filter` Parameter ("ass" oder "srt")

### Bazarr-Integration (bazarr_client.py)
- Singleton-Pattern via `get_bazarr_client()` — None wenn nicht konfiguriert
- Retry-Logik: 3 Versuche mit exponentiellem Backoff
- `search_german_ass()` — durchsucht Provider nach deutschen ASS-Untertiteln
- `fetch_english_srt()` — laesst Bazarr englischen SRT herunterladen
- `notify_scan_disk()` — informiert Bazarr ueber neue Dateien

### Ollama Batching (ollama_client.py)
- 15 Zeilen pro Batch (konfigurierbar)
- Nummerierter Prompt → erwarte gleiche Zeilenanzahl zurueck
- 3 Retries mit exponentiellem Backoff (5s, 10s, 20s)
- Fallback: Einzelzeilen-Modus bei persistentem Batch-Fehler
- Timeout: 90s pro API-Request
- Response-Validation: JSON-Check, Error-Key, fehlende Response

### Qualitaetspruefung (translator.py)
- Identische Zeilen-Erkennung (>30% identisch = Warning)
- Laengenverhaeltnis-Analyse (Deutsch sollte ~1.1-1.5x laenger sein)
- Englische Wort-Frequenz im Output (<15% englische Woerter erwartet)

---

## n8n Workflow

**Datei:** `CCCardinal/n8n-workflows/anime-sub-translation.json`

- Cron-Trigger alle 4 Stunden
- Health Check → Bazarr Wanted List → Filter Anime → Translate (max 5/Run) → Pushover
- Unhealthy-Pfad sendet Pushover-Alert
- 600s Timeout pro Uebersetzungs-Request

---

## Deployment

### Build & Deploy auf Cardinal
```bash
# Dateien auf Cardinal synchronisieren
scp -r CCAnimeTranslator/ root@192.168.178.36:/mnt/user/appdata/anime-sub-translator/

# Auf Cardinal bauen und starten
ssh root@192.168.178.36 "cd /mnt/user/appdata/anime-sub-translator && docker compose up -d --build"
```

### Verifikation nach Deploy
```bash
# Health Check (sollte Ollama + Bazarr zeigen)
curl http://192.168.178.36:5765/health

# Bazarr-Integration pruefen
curl http://192.168.178.36:5765/status/bazarr

# Stats pruefen
curl http://192.168.178.36:5765/stats
```

---

## Bekannte Eigenschaften & Limitationen

- **8.426 Episoden** in der Anime-Bibliothek (~380 Serien)
- **1.504 Episoden** in Bazarr Wanted-List (Stand Feb 2026)
- **~4 Minuten pro Episode** (398 Dialog-Zeilen, 27 Batches bei E01 Dress-Up Darling)
- **Gesamtdauer geschaetzt:** ~562 Stunden fuer komplette Bibliothek
- ASS und SRT Untertitel werden unterstuetzt
- Nur MKV-Container werden gescannt
- Output: `.de.ass` (bevorzugt) oder `.de.srt` (Fallback) neben den MKV-Dateien

## Bekannte Probleme

- Batch Dry-Run mit Pagination loest das alte Timeout-Problem (1.7 MB JSON)
- Callback-URL fuer Batch-Fortschritt verfuegbar aber noch nicht in n8n integriert
- `sonarr-trigger.sh` ist deprecated — n8n Workflow uebernimmt Orchestrierung

---

## Sicherheitsregeln

1. **KEINE Medien-Dateien loeschen oder ueberschreiben** — nur `.de.ass`/`.de.srt` Dateien erstellen
2. **Container-Rebuild** erfordert Bestaetigung (laeuft auf Produktions-Server)
3. **Batch-Verarbeitung** belastet Mac mini GPU/CPU stark — nicht waehrend anderer
   Ollama-Aufgaben (Self-Healing AI) starten ohne Absprache
4. Container hat RW-Zugriff auf gesamte Emby-Media — vorsichtig mit Pfaden
5. Bazarr-Integration faellt lautlos zurueck wenn nicht konfiguriert — kein Fehler
