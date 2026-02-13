# CCAnimeTranslator v2 — Umfassender Verbesserungsplan

## Kontext & Ist-Zustand

### Aktueller Stand
Der Anime Subtitle Translator laeuft auf Cardinal als Docker-Container (`anime-sub-translator:5765`)
und uebersetzt englische ASS-Untertitel via Ollama (Mac mini, `anime-translator` Modell) nach Deutsch.

### Identifizierte Probleme
- **Keine deutsche Sub-Erkennung** — Dateien mit vorhandenen deutschen Subs werden unnoetig uebersetzt
- **Nur ASS als Quellformat** — SRT wird ignoriert, obwohl viele Episoden nur SRT haben
- **Keine Bazarr-Integration** — Arbeitet komplett isoliert, Bazarr weiss nichts von AI-Uebersetzungen
- **Critical Bugs** — Race Conditions (stats ohne Lock), fehlende Validierung, stille Datenverluste
- **Fehlende Infrastruktur** — Kein .gitignore, kein Modelfile, __pycache__ in Git

### Bazarr Ist-Zustand (verifiziert)
- Container laeuft auf Cardinal (`bazarr:6767`)
- API-Key: `8503b420e7678ecfc1d8c68ea0deaee6`
- **Profil 3 "Anime"** existiert: Deutsch (primaer) + Englisch (sekundaer), `originalFormat=1`
- Anime-Serien nutzen bereits Profil 3 (verifiziert)
- Provider: opensubtitlescom, **animetosho**, addic7ed, podnapisi, **jimaku**, embeddedsubtitles
- **1504 Anime-Episoden** in der Wanted-Liste (fehlen deutsche Subs)
- Post-Processing aktiv (sed fuer `\N`-Fix)
- SubSync aktiviert (GSS, max 60s Offset)
- Bazarr hat **kein** "nicht gefunden"-Webhook — nur Wanted-Liste als Tracking

### Sonarr Ist-Zustand
- 61 Anime-Serien (alle monitored), Tag "anime"
- Sonarr-Webhook an Bazarr bereits konfiguriert
- Sonarr-Trigger-Script fuer AnimeTranslator existiert (`scripts/sonarr-trigger.sh`), aber **nicht deployed**

---

## Ziel-Architektur

### Design-Prinzip: Deutsche ASS ist IMMER das Ziel

German ASS (.de.ass) ist das primaere Zielformat — es erhaelt Styles, Override-Tags,
Positionierung und Timing. German SRT ist nur akzeptabel wenn es keine ASS-Quelle gibt.
Selbst wenn eine deutsche SRT existiert, versucht der Translator ein Upgrade auf ASS.

```
┌─────────────────────────────────────────────────────────────┐
│                    Neue Episode (Sonarr)                     │
└──────┬─────────────────────────────────────────────┬────────┘
       │                                             │
       ▼                                             ▼
┌──────────────┐                          ┌──────────────────┐
│   Bazarr     │  Webhook (existiert)     │   n8n Workflow   │
│  Profil 3    │◄─────────────────────────│  (Sonarr Hook)   │
│ de+en        │                          │                  │
└──────┬───────┘                          └────────┬─────────┘
       │                                           │
       │  Sucht deutsche Subs                      │  Wartet 30 Min
       │  bei 6 Providern                          │  (Bazarr Zeit geben)
       │                                           │
       ▼                                           ▼
  ┌──────────────┐                         ┌──────────────────┐
  │ DE ASS       │──► Done (Ziel!)         │  AnimeTranslator │
  │ gefunden     │                         │  Prueft Status   │
  └──────────────┘                         └────────┬─────────┘
  ┌──────────────┐                                  │
  │ DE SRT       │──► Upgrade versuchen ──────────► │
  │ gefunden     │   (ASS waere besser)             │
  └──────────────┘                                  │
  ┌──────────────┐                                  │
  │ Nichts       │──────────────────────────────────│
  │ gefunden     │                                  │
  └──────────────┘                                  │
                                                    ▼
                                      ┌────────────────────────────┐
                                      │  Prioritaetskette:         │
                                      │                            │
                                      │  FALL A: DE ASS vorhanden  │
                                      │  → Skip (Ziel erreicht)    │
                                      │                            │
                                      │  FALL B: DE SRT vorhanden  │
                                      │  → Upgrade-Versuch:        │
                                      │    B1. Bazarr: DE ASS?     │
                                      │    B2. EN ASS → .de.ass    │
                                      │    B3. Keins → SRT behalten│
                                      │                            │
                                      │  FALL C: Kein dt. Sub      │
                                      │    C1. EN ASS → .de.ass    │
                                      │    C2. EN SRT → .de.srt    │
                                      │    C3. Bazarr EN → .de.srt │
                                      │    C4. Nichts → Fail       │
                                      └─────────────┬──────────────┘
                                                    │
                                                    ▼
                                      ┌────────────────────────────┐
                                      │  Bazarr benachrichtigen    │
                                      │  (scan-disk)               │
                                      │  → Episode aus Wanted      │
                                      └────────────────────────────┘
```

### Prioritaetskette (Detail)

**FALL A — Deutsche ASS vorhanden (embedded oder extern .de.ass)**

| Prio | Aktion | Ergebnis |
|------|--------|----------|
| A    | Skip   | Ziel bereits erreicht, nichts zu tun |

**FALL B — Deutsche SRT vorhanden, aber KEINE deutsche ASS → Upgrade-Versuch**

| Prio | Quelle / Aktion                  | Output    | Begruendung                                    |
|------|-----------------------------------|-----------|-------------------------------------------------|
| B1   | Bazarr: Deutsche ASS suchen       | `.de.ass` | Provider koennte professionelle ASS haben       |
| B2   | Englische ASS embedded → Uebersetzen | `.de.ass` | AI-Uebersetzung mit Styles besser als plain SRT |
| B3   | Kein Upgrade moeglich → SRT behalten | —        | Deutsche SRT ist akzeptabler Fallback           |

**FALL C — Kein deutscher Untertitel vorhanden**

| Prio | Quelle                  | Aktion                           | Output    | Begruendung                              |
|------|-------------------------|----------------------------------|-----------|------------------------------------------|
| C1   | Englisch ASS (embedded) | Ollama-Uebersetzung              | `.de.ass` | Beste Qualitaet: Styles, Tags, Timing    |
| C2   | Englisch SRT (embedded/extern) | Ollama-Uebersetzung         | `.de.srt` | Format beibehalten, kein ASS verfuegbar  |
| C3   | Bazarr: EN SRT holen    | Bazarr-Download → Uebersetzung   | `.de.srt` | Letzter Versuch ueber Provider           |
| C4   | Keine Quelle            | Fail + Log                       | —         | Episode bleibt in Wanted                 |

---

## Umsetzungsreihenfolge

### Phase 1: Infrastruktur & Voraussetzungen

**Dateien:** Projekt-Root, `docker-compose.yml`

#### 1.1 Git-Cleanup
- **`.gitignore` erstellen:**
  ```
  __pycache__/
  *.pyc
  *.pyo
  .env
  .env.*
  *.egg-info/
  .vscode/
  .idea/
  ```
- **`.dockerignore` erstellen:**
  ```
  .git
  __pycache__
  CLAUDE.md
  PLAN.md
  scripts/
  *.md
  .gitignore
  ```
- **`__pycache__/` aus Git entfernen:** `git rm -r --cached app/__pycache__/`

#### 1.2 Modelfile dokumentieren
- **`Modelfile` erstellen** — Dokumentiert das `anime-translator` Ollama-Modell
  (qwen2.5:14b Basis, System-Prompt, temperature 0.3)
- Dient als Referenz falls das Modell auf dem Mac mini neu erstellt werden muss

#### 1.3 Docker-Compose erweitern
- Neue Environment-Variablen fuer Bazarr-Integration:
  ```yaml
  environment:
    - BAZARR_URL=http://192.168.178.36:6767
    - BAZARR_API_KEY=8503b420e7678ecfc1d8c68ea0deaee6
    - SONARR_URL=http://192.168.178.36:8989
    - SONARR_API_KEY=60563879e92648258976fa64023074b8
  ```
- Bazarr-Credentials sind Container-intern (kein Expose nach aussen)

#### 1.4 Requirements erweitern
- `pysubs2` kann bereits SRT lesen/schreiben — keine neue Dependency noetig
- Pruefen ob `pysubs2` Version SRT-Support hat (ja, ab v1.0)

---

### Phase 2: Deutsche Untertitel-Erkennung

**Dateien:** `app/ass_utils.py`, `app/translator.py`

Dies ist die Grundlage fuer alles Weitere. Bevor uebersetzt wird, muss zuverlaessig
erkannt werden ob bereits deutsche Subs existieren.

#### 2.1 Embedded German Detection (`ass_utils.py`)
- **Neue Funktion `has_german_stream(ffprobe_data)`:**
  ```python
  GERMAN_LANG_TAGS = {"ger", "deu", "de", "german"}

  def has_german_stream(ffprobe_data):
      """Prueft ob mindestens ein deutscher Untertitel-Stream eingebettet ist."""
      for stream in ffprobe_data.get("streams", []):
          if stream.get("codec_type") != "subtitle":
              continue
          lang = stream.get("tags", {}).get("language", "").lower()
          if lang in GERMAN_LANG_TAGS:
              return True
      return False
  ```
- Wird bei jeder Uebersetzung aufgerufen (nach `run_ffprobe()`, vor Stream-Selektion)
- Kein separater ffprobe-Call noetig — nutzt die bereits geholten Daten

#### 2.2 External German Detection (`translator.py`)
- **`has_existing_translation()` refactoren** zu `detect_existing_german()`:
  ```python
  GERMAN_ASS_PATTERNS = [".de.ass", ".deu.ass", ".ger.ass", ".german.ass"]
  GERMAN_SRT_PATTERNS = [".de.srt", ".deu.srt", ".ger.srt", ".german.srt"]
  ```
- Gibt differenzierten Status zurueck (nicht nur bool):
  - `"ass"` — Deutsche ASS vorhanden (Ziel erreicht, Skip)
  - `"srt"` — Deutsche SRT vorhanden (Upgrade-Versuch auf ASS)
  - `None` — Kein deutscher Sub (volle Pipeline)
- Kombiniert embedded + external: ASS-Treffer hat Vorrang ueber SRT

#### 2.3 Integration in Pipeline — Drei-Faelle-Logik
- **`translate_file()` erweitern:**
  - Nach `run_ffprobe()`: `detect_existing_german(mkv_path, probe_data)` aufrufen
  - **Fall A** (`"ass"`): Skip mit `reason: "German ASS already exists"`
  - **Fall B** (`"srt"`): Upgrade-Modus aktivieren (siehe Phase 3/4)
  - **Fall C** (`None`): Volle Translation-Pipeline
- **`scan_directory()` updaten:**
  - Gibt jetzt `german_status` pro Datei zurueck ("ass", "srt", None)
  - Dateien mit `"ass"` werden uebersprungen
  - Dateien mit `"srt"` werden als "upgrade candidates" markiert
  - Embedded-Check NICHT im Scan (zu langsam fuer 8426 Files)
  - Lazy Check nur zur Uebersetzungszeit

---

### Phase 3: SRT-Unterstuetzung

**Dateien:** `app/ass_utils.py`, `app/translator.py`

ASS bleibt das primaere Format. SRT ist der Fallback wenn kein englischer ASS-Stream
vorhanden ist. `pysubs2` kann SRT nativ lesen und schreiben.

#### 3.1 Stream-Selektion erweitern (`ass_utils.py`)
- **`select_best_stream()` refactoren** zu `select_best_subtitle_stream()`
  mit Rueckgabe von Format-Info:
  ```python
  def select_best_subtitle_stream(ffprobe_data):
      """Selektiert den besten Untertitel-Stream.

      Returns:
          dict: {"sub_index": int, "format": "ass"|"srt", "language": str, "title": str}
          oder None wenn nichts gefunden
      """
  ```
- **Neue Prioritaet:**
  1. Englischer ASS-Stream mit "Full" im Titel (nicht Signs/Songs)
  2. Erster englischer ASS-Stream ohne "sign"/"song"
  3. Erster englischer ASS-Stream
  4. ASS-Stream ohne Sprach-Tag, nicht "sign"/"song"
  5. **NEU: Erster englischer SRT-Stream** (Fallback)
  6. **NEU: Erster SRT-Stream ohne Sprach-Tag**
  7. None
- Wichtig: SRT-Streams haben `codec_name` = `"subrip"` oder `"srt"` in ffprobe

#### 3.2 SRT-Extraktion (`ass_utils.py`)
- **`extract_subtitle_stream()` erweitern** (vormals `extract_ass_stream()`):
  - ASS: Wie bisher (`-c:s copy` → `.ass`)
  - SRT: `-c:s copy` → `.srt` (ffmpeg kopiert SRT-Streams direkt)
  - Suffix automatisch basierend auf Format

#### 3.3 SRT-Translation Pipeline (`translator.py`)
- **`translate_srt_file()` als neue Funktion:**
  - `pysubs2.load()` kann SRT direkt laden (erkennt Format automatisch)
  - SRT hat keine Styles → alle Zeilen werden uebersetzt
  - SRT hat keine Override Tags → kein `extract_tags()`/`restore_tags()` noetig
  - `\N` in SRT sind echte Newlines (`\n`) → einfacher
  - **Uebersetzungsablauf:**
    1. SRT laden mit pysubs2
    2. Alle nicht-leeren Zeilen sammeln
    3. Tags-artige Marker `{...}` entfernen (selten in SRT, aber moeglich)
    4. Batch-Uebersetzung via `translate_all()` (gleicher Ollama-Client)
    5. Ergebnis zurueckschreiben
    6. Als `.de.srt` speichern: `subs.save(output_path, format_="srt")`
- **Qualitaets-Vorteil ASS:** In den Stats/Logs festhalten ob ASS oder SRT uebersetzt
  wurde, damit der Benutzer weiss welche Episoden "Premium" (ASS) und welche "Fallback" (SRT) sind

#### 3.4 Externe SRT-Dateien als Quelle
- **`find_external_english_srt()` in `translator.py`:**
  ```python
  ENGLISH_SRT_PATTERNS = [
      ".en.srt", ".eng.srt", ".english.srt",
      ".en.ass", ".eng.ass",  # Seltener, aber moeglich
  ]
  ```
  - Sucht neben der MKV nach englischen externen Untertiteln
  - Gibt den Pfad zurueck oder None
  - Wird in Prio 3 der Kette genutzt

#### 3.5 translate_file() Refactoring — Drei-Faelle-Pipeline
- **Neue Gesamt-Pipeline:**
  ```python
  def translate_file(mkv_path, force=False, bazarr_context=None):
      probe_data = run_ffprobe(mkv_path)

      if not force:
          german_status = detect_existing_german(mkv_path, probe_data)
      else:
          german_status = None

      # ═══ FALL A: Deutsche ASS vorhanden → Ziel erreicht ═══
      if german_status == "ass":
          return skip_result("German ASS already exists")

      # ═══ FALL B: Deutsche SRT vorhanden → Upgrade-Versuch auf ASS ═══
      if german_status == "srt":
          # B1: Bazarr nach deutscher ASS fragen
          if bazarr_context:
              de_ass = bazarr_search_german_ass(bazarr_context)
              if de_ass:
                  return skip_result("German ASS downloaded via Bazarr (upgraded from SRT)")

          # B2: Englische ASS embedded → uebersetzen zu .de.ass
          best_stream = select_best_subtitle_stream(probe_data, format_filter="ass")
          if best_stream:
              return translate_ass(mkv_path, best_stream, probe_data)

          # B3: Kein Upgrade moeglich → SRT behalten
          return skip_result("German SRT exists, no ASS upgrade available")

      # ═══ FALL C: Kein deutscher Sub → Volle Pipeline ═══

      # C1: Englische ASS embedded → .de.ass (bestes Ergebnis)
      best_stream = select_best_subtitle_stream(probe_data)
      if best_stream and best_stream["format"] == "ass":
          return translate_ass(mkv_path, best_stream, probe_data)

      # C2: Englische SRT (embedded oder extern) → .de.srt
      if best_stream and best_stream["format"] == "srt":
          return translate_srt_from_stream(mkv_path, best_stream)

      ext_srt = find_external_english_srt(mkv_path)
      if ext_srt:
          return translate_srt_from_file(mkv_path, ext_srt)

      # C3: Bazarr: Englische SRT beschaffen → .de.srt
      if bazarr_context:
          eng_srt = bazarr_fetch_english(bazarr_context)
          if eng_srt:
              return translate_srt_from_file(mkv_path, eng_srt)

      # C4: Nichts gefunden
      return fail_result("No English subtitle source found")
  ```

**Wichtig:** `select_best_subtitle_stream()` akzeptiert einen optionalen `format_filter`
Parameter. In Fall B2 wird nur nach ASS-Streams gesucht (SRT ignoriert, da SRT→SRT
kein Upgrade waere).

---

### Phase 4: Bazarr Integration

**Dateien:** Neue `app/bazarr_client.py`, `app/translator.py`, `app/server.py`

#### 4.1 Bazarr API Client (`bazarr_client.py`)

Neues Modul fuer alle Bazarr-Interaktionen:

```python
class BazarrClient:
    """Bazarr REST API Client."""

    def __init__(self, url, api_key):
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers["X-API-KEY"] = api_key
```

**Methoden:**

| Methode | API-Call | Zweck |
|---------|----------|-------|
| `get_wanted_anime(limit=50)` | `GET /api/episodes/wanted` + Tag-Filter | Anime-Episoden ohne dt. Subs |
| `get_episode_subs(episode_id)` | `GET /api/episodes?episodeid[]=X` | Vorhandene Subs einer Episode |
| `search_german_ass(series_id, episode_id)` | `GET /api/providers/episodes` + Filter | Gezielt nach deutscher ASS bei Providern suchen (fuer Upgrade B1) |
| `download_subtitle(series_id, episode_id, provider_result)` | `POST /api/providers/episodes` | Spezifisches Sub-Ergebnis downloaden |
| `search_english_srt(series_id, episode_id)` | `PATCH /api/episodes/subtitles` lang=en | Bazarr nach engl. SRT suchen lassen (fuer Fallback C3) |
| `notify_scan_disk(series_id)` | `PATCH /api/series` action=scan-disk | Bazarr ueber neue Dateien informieren |
| `get_series_by_tag(tag="anime")` | `GET /api/series` + Filter | Alle Anime-Serien listen |
| `health_check()` | `GET /api/system/status` | Bazarr erreichbar? |

**Upgrade-Logik (B1) — `search_german_ass()`:**
- Nutzt `GET /api/providers/episodes?episodeid=X` um alle verfuegbaren Subs zu listen
- Filtert Ergebnisse auf: `language == "de"` UND `release_info` enthaelt ".ass" oder Format-Hinweis
- Bazarr's Provider-Suche liefert `score`, `matches`, `release_info` — damit koennen ASS-Ergebnisse
  identifiziert werden (animetosho und jimaku liefern haeufig ASS)
- Wenn ASS-Ergebnis gefunden: `download_subtitle()` aufrufen
- Timeout: 30s (Provider-Suche kann dauern)

**Fehlerbehandlung:**
- Alle Calls mit Timeout (10s)
- Retries bei Connection-Errors (3x mit Backoff)
- Graceful Degradation: Wenn Bazarr nicht erreichbar → Warnung loggen, weiter ohne Bazarr
- Niemals blocken wenn Bazarr down ist

#### 4.2 Bazarr-Context im Translate-Request

Erweitere den `/translate` Endpoint um optionale Bazarr-Metadaten:
```json
{
  "file_path": "/media/_Anime/_Serien/.../S01E01.mkv",
  "force": false,
  "sonarr_series_id": 1452,
  "sonarr_episode_id": 59443
}
```
- Wenn `sonarr_series_id` + `sonarr_episode_id` mitgegeben werden:
  - Prio 4 (Bazarr English SRT holen) wird moeglich
  - Nach Erfolg: `notify_scan_disk()` automatisch aufgerufen
- Wenn nicht mitgegeben: Bazarr-Integration wird uebersprungen (Prio 1-3 + 5)

#### 4.3 Post-Translation Bazarr-Sync

Nach erfolgreicher Uebersetzung:
1. `bazarr.notify_scan_disk(series_id)` aufrufen
2. Bazarr erkennt die neue `.de.ass` / `.de.srt` Datei
3. Episode verschwindet aus der Wanted-Liste
4. Bazarr's SubSync kann die neue Datei ggf. time-shiften

#### 4.4 Neuer Endpoint: `/translate/wanted`

Dedizierter Endpoint fuer n8n-Integration:
```
POST /translate/wanted
{
  "max_episodes": 10,      // Pro Durchlauf
  "anime_only": true,
  "skip_if_bazarr_searching": true
}
```
- Holt Wanted-Liste von Bazarr (nur Anime-Tag)
- Filtert auf Episoden die Bazarr nicht mehr aktiv sucht (adaptive search expired)
- Startet Uebersetzungen sequentiell (Ollama ist single-threaded)
- Gibt Status zurueck mit Job-IDs

#### 4.5 Neuer Endpoint: `/status/bazarr`

Health & Status fuer die Bazarr-Integration:
```json
{
  "bazarr_reachable": true,
  "wanted_anime_count": 1504,
  "last_sync": "2026-02-13T14:30:00Z",
  "translations_synced": 42
}
```

---

### Phase 5: n8n Workflow

**Datei:** Neuer n8n-Workflow JSON in `CCCardinal/n8n-workflows/`

#### 5.1 Workflow-Design: "Anime Sub Translation Pipeline"

```
Trigger: Cron (alle 4 Stunden)
  │
  ▼
HTTP Request: GET AnimeTranslator /health
  │
  ├── Unhealthy → Stop + Pushover Alert
  │
  ▼
HTTP Request: GET Bazarr /api/episodes/wanted (anime only, limit 20)
  │
  ├── 0 Wanted → Stop (alles up to date)
  │
  ▼
Filter: Nur Episoden wo Bazarr nicht mehr aktiv sucht
  │
  ▼
Loop (max 5 Episoden pro Durchlauf):
  │
  ├── HTTP Request: POST AnimeTranslator /translate/sync
  │   Body: { file_path, sonarr_series_id, sonarr_episode_id }
  │
  ├── Erfolg → Naechste Episode
  │
  ├── Fehler → Loggen, weiter mit naechster
  │
  └── Alle 5 durch → Stop
  │
  ▼
HTTP Request: GET AnimeTranslator /stats
  │
  ▼
Pushover: "Anime Subs: X uebersetzt, Y fehlgeschlagen, Z noch offen"
```

**Warum Cron statt Sonarr-Webhook:**
- Bazarr braucht Zeit zum Suchen (30+ Minuten mit Adaptive Search)
- Ein Timer-basierter Ansatz vermeidet Race Conditions
- 4-Stunden-Intervall = 6x pro Tag = genug fuer neue Episoden
- Einfacher zu debuggen und monitoren

#### 5.2 Optionaler Sonarr-Trigger Workflow (Fast-Path)

Fuer neue Episoden die schneller uebersetzt werden sollen:
```
Trigger: Sonarr Webhook (Download/Upgrade)
  │
  ▼
Filter: Nur Anime (seriesType check)
  │
  ▼
Wait: 45 Minuten (Bazarr Zeit geben)
  │
  ▼
HTTP Request: Bazarr API — Episode noch wanted?
  │
  ├── Nein (Bazarr hat dt. Sub gefunden) → Stop
  │
  ▼
HTTP Request: POST AnimeTranslator /translate
  Body: { file_path, sonarr_series_id, sonarr_episode_id }
  │
  ▼
Pushover: "AI-Uebersetzung gestartet fuer {seriesTitle} S{xx}E{xx}"
```

#### 5.3 Sonarr-Trigger Script ersetzen
- Das existierende `scripts/sonarr-trigger.sh` wird NICHT deployed
- Stattdessen uebernimmt n8n die Orchestrierung (zentraler, besser monitorbar)
- Script bleibt als Dokumentation im Repo

---

### Phase 6: Bug-Fixes & Hardening

#### 6.1 Thread-Safety (`server.py`)
- **`stats_lock = threading.Lock()`** neben `batch_lock` hinzufuegen
- Alle `stats[...]`-Zugriffe schuetzen: `_run_job()`, `_run_batch()`, `/stats` Endpoint
- Fehlende `stats["total_skipped"]` Inkrementierung in `_run_batch()` ergaenzen

#### 6.2 Ollama Response-Validierung (`ollama_client.py`)
- `_call_ollama()`: `resp.json()` in try/except → `RuntimeError` bei invalid JSON
- Auf `"error"` Key im JSON pruefen → `RuntimeError` mit Ollama-Fehlermeldung
- Auf fehlenden `"response"` Key pruefen → `RuntimeError`

#### 6.3 Health-Check absichern (`ollama_client.py`)
- `resp.json()` in try/except → `return False, "invalid JSON"`
- `requests.Timeout` separat fangen

#### 6.4 Retries fuer Einzelzeilen (`ollama_client.py`)
- `_translate_singles()`: Gleiche Retry-Logik wie `translate_batch()`
  (3 Versuche, exponentieller Backoff)
- `except Exception` einschraenken auf `(requests.RequestException, RuntimeError)`

#### 6.5 Smarteres Line-Merging (`ollama_client.py`)
- `_parse_response()`: Wenn mehr Zeilen als erwartet:
  Versuche aufeinanderfolgende nicht-nummerierte Zeilen zu mergen
- Erst nach gescheitertem Merge truncaten

#### 6.6 Translator-Validierung (`translator.py`)
- Laengen-Check nach `translate_all()`:
  `if len(translated) != len(originals)` → `return success=False`

#### 6.7 Error-Handling (`ass_utils.py`, `ollama_client.py`)
- `run_ffprobe()`: `json.loads()` in try/except, `subprocess.TimeoutExpired` separat
- `REQUEST_TIMEOUT` auf 90s senken (120s ist zu lang, Ollama ist dann stuck)

#### 6.8 Tag-Restoration verbessern (`ass_utils.py`)
- `extract_tags()`: Zusaetzlich `original_clean_length` zurueckgeben
- `restore_tags()`: Proportionale Positionierung statt fester Zeichenposition
  - Position-0-Tags bleiben am Anfang
  - Andere: `ratio = original_pos / original_length` → `insert_pos = ratio * translated_length`
  - Snap auf naechste Wortgrenze innerhalb +/- 3 Zeichen

---

### Phase 7: Server-Erweiterungen

#### 7.1 Batch Dry-Run Paginierung (`server.py`)
- Parameter `page` (default 1) und `per_page` (default 100)
- Response: `total_pages`, `page`, `files_found`
- Verhindert 1.7 MB JSON-Responses bei 8426 Dateien

#### 7.2 Batch Callback-URL (`server.py`)
- Optionaler `callback_url` im `/batch` Endpoint
- POST mit Status-Update nach jeder Datei und am Ende
- Fire-and-forget mit 5s Timeout
- Nutzen: n8n kann benachrichtigt werden ohne zu pollen

#### 7.3 Uebersetzungs-Qualitaetspruefung (`translator.py`)
- Check nach Uebersetzung (gilt fuer ASS und SRT):
  - Uebersetzung identisch mit Original? → Warnung "not translated"
  - Laengenverhaeltnis >3x oder <0.3x? → Warnung "suspicious length"
  - Haeufige englische Woerter in "Uebersetzung"? → Warnung "possibly untranslated"
- Nur als Warnung loggen + in Stats aufnehmen, nicht blockieren
- Threshold konfigurierbar via Environment

#### 7.4 Stats erweitern (`server.py`)
- Neue Felder:
  ```json
  {
    "by_format": { "ass": 120, "srt": 34 },
    "by_source": {
      "embedded_ass": 100,
      "embedded_srt": 20,
      "external_srt": 10,
      "bazarr_english_srt": 4
    },
    "upgrades": {
      "srt_to_ass_translated": 15,
      "srt_to_ass_bazarr": 3,
      "srt_upgrade_skipped": 8
    },
    "skipped": {
      "german_ass_exists": 450,
      "german_srt_kept": 8
    },
    "bazarr_synced": 154,
    "quality_warnings": 3
  }
  ```

---

## Betroffene Dateien (Zusammenfassung)

| Datei | Phasen | Aenderungsumfang |
|---|---|---|
| `app/translator.py` | 2, 3, 6, 7 | Komplett-Refactoring: Priority Chain, SRT-Pipeline, German-Detection, Qualitaetscheck |
| `app/ass_utils.py` | 2, 3, 6 | German-Stream-Check, Stream-Selektion (ASS+SRT), Tag-Restoration, ffprobe-Errors |
| `app/server.py` | 4, 6, 7 | Stats-Lock, neue Endpoints (/translate/wanted, /status/bazarr), Paginierung, Callback |
| `app/ollama_client.py` | 6 | Response-Validation, Health-Check, Retries, Timeout, Line-Merging |
| **`app/bazarr_client.py`** | 4 | **Neu:** Bazarr API Client (Wanted, Search, Scan-Disk, Health) |
| `docker-compose.yml` | 1 | Bazarr/Sonarr Environment-Variablen |
| `app/requirements.txt` | 1 | Ggf. Version-Pinning |
| `.gitignore` | 1 | **Neu** |
| `.dockerignore` | 1 | **Neu** |
| `Modelfile` | 1 | **Neu** |
| `scripts/sonarr-trigger.sh` | 5 | Deprecated-Markierung (n8n uebernimmt) |
| n8n-Workflow JSON | 5 | **Neu:** Anime Sub Translation Pipeline |

---

## Verifizierung

### Nach jeder Phase

1. Container auf Cardinal neu bauen:
   ```bash
   ssh root@192.168.178.36 "cd /mnt/user/appdata/anime-sub-translator && docker compose up -d --build"
   ```
2. Health-Check: `curl http://192.168.178.36:5765/health`
3. Container-Logs: `docker logs anime-sub-translator --tail 50`

### Phase-spezifische Tests

| Phase | Testfall | Erwartung |
|-------|----------|-----------|
| 2 | Episode mit eingebetteter deutscher ASS | Fall A: Skip "German ASS already exists" |
| 2 | Episode mit externer `.de.ass` | Fall A: Skip |
| 2 | Episode mit `.de.srt` aber ohne `.de.ass` | Fall B: Upgrade-Versuch (nicht Skip!) |
| 2 | Episode ohne deutschen Sub | Fall C: Volle Pipeline |
| 3 | Episode mit nur englischem SRT (kein ASS) | Fall C2: Uebersetzt zu `.de.srt` |
| 3 | Episode mit englischem ASS + SRT | Fall C1: ASS bevorzugt → `.de.ass` |
| 3 | Episode mit dt. SRT + engl. ASS embedded | Fall B2: Upgrade → `.de.ass` erstellt |
| 4 | Fall B1: Bazarr findet deutsche ASS | Download via Bazarr, SRT-Upgrade erfolgreich |
| 4 | Fall C3: Bazarr holt englische SRT | Download + Uebersetzung → `.de.srt` |
| 4 | `/translate/wanted` | Holt Wanted von Bazarr, startet Uebersetzungen |
| 4 | `/status/bazarr` | Zeigt Bazarr-Verbindungsstatus |
| 5 | n8n Workflow manuell triggern | Episoden werden abgearbeitet |
| 6 | Parallele `/translate` Requests | Keine Stats-Corruption |
| 7 | Dry-Run mit Paginierung | Max 100 Eintraege pro Seite |

### End-to-End Test

1. Episode waehlen die in Bazarr Wanted ist (z.B. Irregular at Magic High School S3E13)
2. `POST /translate` mit Sonarr-IDs
3. Pruefen: `.de.ass` oder `.de.srt` wurde erstellt
4. Pruefen: Bazarr zeigt Episode nicht mehr als "wanted"
5. Pruefen: Emby/Jellyfin erkennt den neuen Untertitel

---

## Abhaengigkeiten zwischen Phasen

```
Phase 1 (Infra)
  │
  ▼
Phase 2 (German Detection) ─────┐
  │                              │
  ▼                              │
Phase 3 (SRT Support) ──────────┤
  │                              │
  ▼                              │
Phase 4 (Bazarr Client) ◄───────┘
  │
  ▼
Phase 5 (n8n Workflow) — braucht Phase 4
  │
  ▼
Phase 6 (Bug-Fixes) — unabhaengig, kann parallel zu 4/5
  │
  ▼
Phase 7 (Erweiterungen) — unabhaengig, kann parallel zu 5/6
```

Phase 6 und 7 koennen nach Phase 3 jederzeit eingeschoben werden.
Die kritische Abhaengigkeitskette ist: 1 → 2 → 3 → 4 → 5.

---

## Nicht im Scope

- **Parallele Uebersetzung** — Ollama auf Mac mini ist single-threaded
- **Persistente Job-History** — In-Memory reicht fuer den Use-Case
- **Unit Tests** — Sinnvoll aber separates Projekt
- **Radarr/Film-Support** — Fokus auf Anime-Serien (Sonarr)
- **Bazarr Provider Registration** — AnimeTranslator als Bazarr-Provider zu registrieren
  waere elegant aber extrem komplex (eigenes Bazarr-Plugin)
- **Automatisches Ollama-Modell-Management** — Modell muss manuell auf Mac mini existieren

---

## Risiken & Mitigationen

| Risiko | Wahrscheinlichkeit | Mitigation |
|--------|-------------------|------------|
| Bazarr API nicht stabil | Niedrig | Graceful Degradation: ohne Bazarr weiter uebersetzen |
| Ollama ueberfordert bei 1504 Episoden | Mittel | Max 5 Episoden pro n8n-Durchlauf, 4h Intervall |
| SRT-Timing ungenau nach Uebersetzung | Niedrig | Bazarr SubSync kann nachkorrigieren |
| pysubs2 SRT-Parsing-Fehler | Niedrig | Try/except, Episode ueberspringen + loggen |
| Mac mini nicht erreichbar | Mittel | Health-Check vor jedem Batch, Pushover-Alert |
