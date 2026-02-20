# SRT Overlap Merge — Beta Feature Plan

## Problem

SRT-Dateien (besonders bei Anime) enthalten oft Dialog UND On-Screen Text (Signs).
Wenn beide zeitlich überlappen, zeigen die meisten Player nur einen Eintrag — typischerweise
den Sign-Text, wodurch der Dialog verloren geht. ASS löst das mit Layern und Positionierung,
aber wenn nur eine SRT vorhanden ist, fehlt diese Möglichkeit.

## Lösung

Zeitlich überlappende SRT-Einträge erkennen und in einen einzigen mehrzeiligen Eintrag
zusammenführen. So zeigen alle Player beide Texte gleichzeitig an.

### Vorher (Player zeigt nur eins)
```srt
42
00:05:00,000 --> 00:05:03,000
Akademie für Helden

43
00:05:00,000 --> 00:05:03,000
Ich werde der Stärkste!
```

### Nachher (Player zeigt beides)
```srt
42
00:05:00,000 --> 00:05:03,000
Akademie für Helden
Ich werde der Stärkste!
```

---

## Feature-Spezifikation

### Kernverhalten

| Aspekt | Entscheidung |
|--------|-------------|
| **Trigger** | Einstellbar: automatisch bei Download, manuell über UI, oder beides |
| **Overlap-Erkennung** | Konfigurierbarer Prozent-Threshold (% der kürzeren Zeile) |
| **Default-Threshold** | 50% (kürzere Zeile muss zu ≥50% überlappt werden) |
| **Zeilenreihenfolge** | Original-Reihenfolge beibehalten (wie in der SRT-Datei) |
| **Output** | Neue Datei mit konfigurierbarem Suffix (Default: `.merged`) |
| **Original** | Bleibt unverändert erhalten |
| **Reporting** | Detaillierter Log mit Zeitstempeln und betroffenen Zeilen |
| **UI** | Eigener "Beta Features" Tab in Settings |

### Overlap-Berechnung

```
Overlap-Prozent = Überlappungsdauer / Dauer der kürzeren Zeile × 100

Beispiel:
  Eintrag A: 00:05:00 → 00:05:05 (5s)
  Eintrag B: 00:05:03 → 00:05:08 (5s)
  Überlappung: 00:05:03 → 00:05:05 (2s)
  Kürzere Zeile: 5s (beide gleich)
  Overlap: 2s / 5s = 40%
  Bei Threshold 50% → NICHT zusammenführen
  Bei Threshold 30% → Zusammenführen
```

### Merge-Timing-Strategie bei partiellen Overlaps

Wenn zusammengeführt wird, entsteht ein neuer Eintrag mit dem **längsten Zeitfenster**:
```
Eintrag A: 00:05:00 → 00:05:05
Eintrag B: 00:05:03 → 00:05:08
Merged:    00:05:00 → 00:05:08  (beide Texte, volles Fenster)
```

### Multi-Overlap-Handling

Wenn 3+ Einträge sich gegenseitig überlappen, werden alle in einen zusammengeführt:
```
A: 00:05:00 → 00:05:05  "Sign Text"
B: 00:05:02 → 00:05:06  "Dialog 1"
C: 00:05:04 → 00:05:07  "Dialog 2"
→ Merged: 00:05:00 → 00:05:07 mit 3 Textzeilen
```

---

## Konfiguration

### Neue Config-Einträge (DB config_entries)

| Key | Typ | Default | Beschreibung |
|-----|-----|---------|-------------|
| `beta_srt_overlap_merge_enabled` | bool | `false` | Feature an/aus |
| `beta_srt_overlap_merge_auto` | bool | `false` | Automatisch bei Provider-Download |
| `beta_srt_overlap_merge_threshold` | int | `50` | Overlap-Prozent ab dem gemergt wird (1-100) |
| `beta_srt_overlap_merge_suffix` | str | `merged` | Suffix für Output-Datei |
| `beta_srt_overlap_merge_max_lines` | int | `4` | Max Zeilen pro Merged-Eintrag (Sicherheitslimit) |

### Config-Kaskade

Alle Settings über DB `config_entries` (Runtime-Override), da Beta-Feature.
Kein Eintrag in `config.py` Pydantic Settings nötig — das Feature soll bewusst
nicht über Environment-Variablen aktivierbar sein (erst nach Stabilisierung).

---

## Backend-Implementierung

### Neue Datei: `backend/srt_overlap_merger.py`

```
Klasse: SRTOverlapMerger
  - __init__(threshold_percent=50, max_merge_lines=4, suffix="merged")
  - analyze(srt_path) → OverlapReport
  - merge(srt_path, output_path=None) → MergeResult
  - _find_overlaps(events) → List[OverlapGroup]
  - _merge_group(group) → SSAEvent
  - _calculate_overlap_percent(event_a, event_b) → float

Datenklassen:
  OverlapGroup:
    - events: List[SSAEvent]
    - overlap_start: int (ms)
    - overlap_end: int (ms)
    - overlap_percent: float

  OverlapReport:
    - total_entries: int
    - overlap_groups: List[OverlapGroup]
    - total_overlaps: int
    - affected_entries: int

  MergeResult:
    - input_path: str
    - output_path: str
    - overlaps_found: int
    - overlaps_merged: int
    - entries_before: int
    - entries_after: int
    - details: List[MergeDetail]

  MergeDetail:
    - timecode: str (z.B. "00:05:00 → 00:05:08")
    - original_texts: List[str]
    - merged_text: str
    - overlap_percent: float
```

### Algorithmus

```python
def _find_overlaps(events):
    """
    1. Events nach Startzeit sortieren
    2. Sliding Window: für jedes Event prüfen ob es mit
       nachfolgenden Events überlappt
    3. Überlappende Events in Gruppen zusammenfassen
    4. Overlap-Prozent berechnen und gegen Threshold prüfen
    5. Groups zurückgeben die den Threshold überschreiten
    """

def merge(srt_path):
    """
    1. SRT laden via pysubs2.load()
    2. Overlaps finden via _find_overlaps()
    3. Für jede Overlap-Group:
       a. Texte zusammenführen (Newline-separiert)
       b. Timing = min(starts) → max(ends)
       c. Originalreihenfolge der Texte beibehalten
       d. Max-Lines-Limit prüfen (Sicherheit)
    4. Neue Event-Liste aufbauen (non-overlapping + merged)
    5. Sequenznummern neu vergeben
    6. Output schreiben via pysubs2.save()
    7. MergeResult mit Details zurückgeben
    """
```

### Integration in bestehende Pipeline

**Automatischer Trigger (wenn aktiviert):**

In `translator.py` nach erfolgreichem Provider-Download, BEVOR die Übersetzung startet:

```python
# In translator.py, nach SRT-Download von Provider
if get_config_entry("beta_srt_overlap_merge_enabled") == "true" \
   and get_config_entry("beta_srt_overlap_merge_auto") == "true":
    merger = SRTOverlapMerger(
        threshold_percent=int(get_config_entry("beta_srt_overlap_merge_threshold") or 50),
        suffix=get_config_entry("beta_srt_overlap_merge_suffix") or "merged"
    )
    result = merger.merge(downloaded_srt_path)
    if result.overlaps_merged > 0:
        emit_event("srt_overlap_merge_complete", result.to_dict())
        logger.info(f"SRT Overlap Merge: {result.overlaps_merged} overlaps merged")
```

**Manueller Trigger:**

Neuer API-Endpoint für manuelle Ausführung pro Datei oder Batch.

### Neue API-Endpoints

```
POST /api/v1/beta/srt-overlap/analyze
  Body: { "file_path": "/media/.../episode.en.srt" }
  Response: OverlapReport (nur Analyse, keine Änderung)

POST /api/v1/beta/srt-overlap/merge
  Body: { "file_path": "/media/.../episode.en.srt" }
  Response: MergeResult

POST /api/v1/beta/srt-overlap/batch-merge
  Body: { "series_id": 123 }  oder  { "paths": [...] }
  Response: { "job_id": "...", "total": 24 }

GET /api/v1/beta/srt-overlap/status/<job_id>
  Response: Batch-Fortschritt
```

### Neues Event

```python
# In events/catalog.py
"srt_overlap_merge_complete": {
    "description": "SRT overlap merge completed",
    "payload": ["input_path", "output_path", "overlaps_found",
                "overlaps_merged", "entries_before", "entries_after"]
}
```

### Logging/History

Neuer Eintrag in `activity_log` (bestehende Tabelle) oder dedizierte Tabelle:

```sql
-- Option: Eigene Tabelle für detailliertes Reporting
CREATE TABLE IF NOT EXISTS srt_merge_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    input_path TEXT NOT NULL,
    output_path TEXT NOT NULL,
    overlaps_found INTEGER DEFAULT 0,
    overlaps_merged INTEGER DEFAULT 0,
    entries_before INTEGER DEFAULT 0,
    entries_after INTEGER DEFAULT 0,
    details_json TEXT,          -- JSON mit MergeDetail-Liste
    threshold_used INTEGER,
    merged_at TEXT DEFAULT (datetime('now'))
);
```

---

## Frontend-Implementierung

### Neuer Settings-Tab: "Beta Features"

**Datei:** `frontend/src/pages/Settings/BetaFeaturesTab.tsx`

Dieser Tab wird zum zentralen Ort für alle experimentellen Features.
Aktuell nur SRT Overlap Merge, aber erweiterbar.

```
┌─────────────────────────────────────────────────┐
│  ⚗️ Beta Features                    [BETA]     │
│                                                  │
│  ┌─ SRT Overlap Merge ─────────────────────────┐│
│  │                                              ││
│  │  Zusammenführung überlappender SRT-Einträge  ││
│  │  damit Dialog und On-Screen Text gleichzeitig││
│  │  angezeigt werden.                           ││
│  │                                              ││
│  │  [Toggle] Feature aktivieren                 ││
│  │  [Toggle] Automatisch bei Download           ││
│  │                                              ││
│  │  Overlap-Threshold:  [====50%====]  50%      ││
│  │  Output-Suffix:      [  merged   ]           ││
│  │  Max Zeilen/Eintrag: [    4      ]           ││
│  │                                              ││
│  └──────────────────────────────────────────────┘│
└─────────────────────────────────────────────────┘
```

### Library-Integration

In der SeriesDetail/MovieDetail-Page ein Button pro Subtitle-Datei:

```
┌─ episode.en.srt ────────────────────────┐
│  Provider: AnimeTosho  Score: 245       │
│  [Analyze Overlaps]  [Merge Overlaps]   │
│                                          │
│  Letzte Analyse: 12 Overlaps gefunden   │
│  Letzte Merge: 8 zusammengeführt        │
└──────────────────────────────────────────┘
```

### Analyse-Ergebnis Dialog

Nach Klick auf "Analyze Overlaps" ein Modal/Dialog:

```
┌─ Overlap-Analyse: episode.en.srt ──────────────┐
│                                                  │
│  Einträge gesamt:     342                        │
│  Überlappungen:       12                         │
│  Betroffene Einträge: 28                         │
│  Threshold:           50%                        │
│                                                  │
│  ┌─ Details ───────────────────────────────────┐ │
│  │ 00:05:00 → 00:05:03 (87% Overlap)          │ │
│  │   "Akademie für Helden"                     │ │
│  │   "Ich werde der Stärkste!"                 │ │
│  │                                              │ │
│  │ 00:12:44 → 00:12:48 (62% Overlap)          │ │
│  │   "GEFAHR - BETRETEN VERBOTEN"              │ │
│  │   "Wir müssen da rein!"                     │ │
│  └──────────────────────────────────────────────┘│
│                                                  │
│  [Abbrechen]              [Merge durchführen]    │
└──────────────────────────────────────────────────┘
```

---

## Dateien — Übersicht aller Änderungen

### Neue Dateien

| Datei | Zweck |
|-------|-------|
| `backend/srt_overlap_merger.py` | Kernlogik: Overlap-Erkennung + Merge |
| `backend/routes/beta.py` | API-Endpoints für Beta-Features |
| `backend/tests/test_srt_overlap_merger.py` | Unit Tests |
| `frontend/src/pages/Settings/BetaFeaturesTab.tsx` | UI: Beta-Tab in Settings |
| `frontend/src/components/shared/OverlapAnalysisModal.tsx` | UI: Analyse-Ergebnis Dialog |

### Zu ändernde Dateien

| Datei | Änderung |
|-------|----------|
| `backend/server.py` | Beta-Blueprint registrieren |
| `backend/translator.py` | Auto-Merge nach Download einhängen (~5 Zeilen) |
| `backend/database.py` | `srt_merge_history` Tabelle anlegen |
| `backend/events/catalog.py` | Neues Event `srt_overlap_merge_complete` |
| `frontend/src/pages/Settings/index.tsx` | "Beta Features" Tab hinzufügen |
| `frontend/src/pages/SeriesDetail.tsx` | Analyze/Merge Buttons (optional, Phase 2) |
| `frontend/src/lib/types.ts` | TypeScript Interfaces für Overlap-Daten |
| `frontend/src/api/client.ts` | API-Calls für Beta-Endpoints |

---

## Implementierungsreihenfolge

### Phase 1: Backend-Kern (srt_overlap_merger.py + Tests)
1. Datenklassen definieren (OverlapGroup, OverlapReport, MergeResult, MergeDetail)
2. `_calculate_overlap_percent()` implementieren
3. `_find_overlaps()` implementieren
4. `_merge_group()` implementieren
5. `analyze()` und `merge()` als public API
6. Unit Tests mit Edge Cases:
   - Keine Overlaps → keine Änderung
   - Exakte Zeitgleichheit → Merge
   - Partielle Überlappung unter Threshold → kein Merge
   - Partielle Überlappung über Threshold → Merge
   - 3+ gleichzeitige Overlaps → ein Merge
   - Leere SRT → graceful handling
   - Bereits mehrzeilige Einträge → korrekt behandeln
   - Max-Lines-Limit erreicht → keine weiteren Merges in die Gruppe

### Phase 2: API + DB + Events
1. `srt_merge_history` Tabelle in database.py
2. Event in catalog.py registrieren
3. `routes/beta.py` mit analyze/merge/batch-merge Endpoints
4. Blueprint in server.py registrieren

### Phase 3: Pipeline-Integration
1. Auto-Merge Hook in translator.py nach Provider-Download
2. Config-Entries auslesen und Feature-Gate

### Phase 4: Frontend
1. BetaFeaturesTab.tsx mit Settings-Controls
2. Tab in Settings/index.tsx registrieren
3. TypeScript Types + API-Client Calls
4. OverlapAnalysisModal.tsx (optional, kann auch Phase 5 sein)

### Phase 5: Library-Integration (Optional, kann nachgeliefert werden)
1. Analyze/Merge Buttons in SeriesDetail
2. Batch-Merge für ganze Serien

---

## Edge Cases & Sicherheit

| Edge Case | Handling |
|-----------|----------|
| SRT ohne Overlaps | Report mit 0 Overlaps, keine Output-Datei erstellt |
| Output-Datei existiert bereits | Überschreiben mit Warning im Log |
| Mehr als `max_merge_lines` Overlaps | Nur die ersten N zusammenführen, Rest als separate Einträge |
| Leerer Text in SRT-Eintrag | Überspringen, nicht in Merge einbeziehen |
| Nur Whitespace/Tags | Wie leerer Text behandeln |
| Datei nicht lesbar | Graceful Error, kein Crash |
| Kein pysubs2 installiert | Unmöglich (bereits Dependency), aber ImportError abfangen |
| Riesige SRT (10000+ Einträge) | Performance: O(n log n) Sort + O(n) Sweep |
| Bereits gemergte Datei nochmal mergen | Idempotent: keine neuen Overlaps → keine Änderung |

---

## Testplan

### Unit Tests (test_srt_overlap_merger.py)

```python
class TestOverlapCalculation:
    test_exact_overlap()           # 100%
    test_partial_overlap()         # z.B. 40%
    test_no_overlap()              # 0%
    test_adjacent_no_overlap()     # Ende A == Start B → 0%
    test_contained_overlap()       # B komplett in A → 100%

class TestFindOverlaps:
    test_no_overlaps()
    test_single_overlap_pair()
    test_multiple_separate_overlaps()
    test_chain_overlap_three()     # A↔B↔C
    test_threshold_boundary()      # Genau am Threshold
    test_below_threshold()         # Knapp unter Threshold

class TestMerge:
    test_simple_merge()
    test_timing_expansion()        # Merged Timing = longest span
    test_text_order_preserved()
    test_max_lines_limit()
    test_no_overlaps_no_output()
    test_idempotent()              # Merge of merged = same result
    test_multiline_entries()       # Bereits mehrzeilige SRT-Einträge
    test_empty_srt()
    test_single_entry_srt()

class TestFileHandling:
    test_output_suffix()
    test_custom_suffix()
    test_original_unchanged()      # Input-Datei unverändert
```

### Integrationstests

- SRT-Datei aus echtem Anime-Fansub mit bekannten Overlaps
- Pipeline-Test: Download → Auto-Merge → Translation
- API-Test: analyze → merge → history abrufen

---

## Metriken & Monitoring

Wenn Prometheus-Metrics aktiv:
```python
srt_overlaps_found_total      # Counter: gefundene Overlaps gesamt
srt_overlaps_merged_total     # Counter: durchgeführte Merges gesamt
srt_merge_duration_seconds    # Histogram: Dauer pro Merge-Operation
```

---

## Zukunftserweiterungen (nicht in dieser Implementierung)

1. **LLM-Klassifizierung:** Dialog vs Sign erkennen, Dialog priorisieren
2. **Whisper-Abgleich:** Voice Activity Detection zur Klassifizierung
3. **ASS-Konvertierung:** Merged SRT → einfache ASS mit Dialog unten + Signs \an8
4. **Vorschau:** Im UI anzeigen wie das Ergebnis im Player aussehen würde
5. **Undo:** Merged-Datei löschen und zurück zum Original
