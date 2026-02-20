# SRT-Reference-Enhanced ASS Translation — Implementation Plan

## Context

Lokale LLMs (Ollama) liefern bei ASS-Untertitelübersetzung oft steife, inkonsistente Ergebnisse.
Wenn bereits eine deutsche SRT existiert (extern, embedded, oder per Provider), enthält sie eine
menschliche/professionelle Übersetzung die als **Referenzkontext** im LLM-Prompt genutzt werden kann.

**Getestet mit qwen2.5:14b und qwen3:30b:**
- Qualität: Natürlichere Formulierungen, konsistente Terminologie, besserer Ton
- Speed: 3-6x schneller (LLM adaptiert statt generiert)
- Robustheit: Line-Count-Matching funktioniert auch bei unterschiedlichen Zeilenaufteilungen

**Scope:** Eigenständige Special Beta — alle ASS-Übersetzungen prüfen ob eine Target-SRT existiert.
Nur für Ollama-Backend (und OpenAI-Compatible) — nicht für API-Backends wegen Token-Kosten.

---

## Testergebnisse (Proof of Concept)

### Test A/B: Standard vs. SRT-Referenz

| Aspekt | Ohne Referenz | Mit SRT-Referenz |
|--------|--------------|-----------------|
| "I'm not that dense" | "Ich bin nicht so dumm" | **"So begriffsstutzig bin ich nicht"** |
| "For three hundred years" | "Drei Hundert Jahre lang" (Fehler!) | **"Dreihundert Jahre lang"** |
| "And let us end this together" | "lass uns damit gemeinsam enden" (holprig) | **"lass uns das gemeinsam beenden"** |

### Performance

| Modell | Ohne Ref | Mit Ref | Speedup |
|--------|----------|---------|---------|
| qwen2.5:14b (10 Zeilen) | 3.0s | 0.8s | **3.7x** |
| qwen3:30b (10 Zeilen) | 23.5s | 3.9s | **6x** |
| qwen3:30b (8 vs 5 Zeilen Mismatch) | 23.5s | 3.9s | **6x** |

### Edge Cases

| Szenario | Ergebnis |
|----------|----------|
| Mismatched line counts (ASS=8, SRT=5) | v2-Prompt: 8/8 korrekt |
| SRT hat Fehler (Platoon→"Bataillon") | LLM übernimmt teilweise → Prompt sagt "improve if awkward" |
| SRT ist fast identisch | LLM kopiert ~90% (schnell, gutes Ergebnis) |

---

## Architektur-Übersicht

```
translate_ass() / _translate_external_ass()
  │
  ├─ [NEU] _find_srt_reference(mkv_path, target_lang)
  │    ├─ Extern: {base}.{lang}.srt vorhanden?
  │    ├─ Embedded: ffprobe Target-SRT Stream?
  │    └─ Return: List[str] | None (SRT-Textzeilen)
  │
  ├─ _translate_with_manager(dialog_texts, ..., srt_reference=srt_lines)
  │    └─ TranslationManager.translate_with_fallback(..., srt_reference=srt_lines)
  │         └─ backend.translate_batch(..., srt_reference=srt_lines)
  │              └─ [Ollama/OpenAI] build_translation_prompt(..., srt_reference=srt_lines)
  │              └─ [DeepL/Libre/Google] ignoriert srt_reference (kein Prompt-Engineering)
  │
  └─ Ergebnis: .{lang}.ass mit SRT-Referenz-verbesserter Übersetzung
```

---

## Dateien und Änderungen

### 1. `backend/config.py` — Config-Setting

**Neues Setting:**
```python
srt_reference_enabled: bool = True  # env: SUBLARR_SRT_REFERENCE_ENABLED
```

Runtime-Override via `config_entries` DB-Tabelle möglich.

---

### 2. `backend/translator.py` — SRT-Referenz-Erkennung + Durchreichung

**Neue Funktion: `_find_srt_reference()`** (ca. Zeile 310, nach den detect-Funktionen)

```python
def _find_srt_reference(mkv_path: str, target_language: str,
                        probe_data=None) -> list[str] | None:
    """Find existing target-language SRT to use as translation reference.

    Checks (in priority order):
    1. External .{lang}.srt file
    2. Embedded SRT stream in target language (via ffprobe + extraction)

    Returns:
        List of SRT text lines (dialog only, cleaned), or None if not found.
    """
```

Logik:
- `config.srt_reference_enabled` prüfen → False = sofort None zurück
- External SRT: Pfadkonstruktion wie `detect_existing_target_for_lang`, dann `pysubs2.load()`
- Embedded SRT: `select_best_subtitle_stream(probe_data, format_filter="srt", language=target_lang)`, extrahieren, laden
- Dialog-Texte extrahieren (gleiche Logik wie `_translate_srt`): HTML-Tags strippen, leere Zeilen skippen
- Return: `List[str]` mit den reinen Textzeilen

**Änderung `translate_ass()`** (Zeile 404-521):
- Nach `classify_styles()` und Dialog-Extraktion: `srt_reference = _find_srt_reference(mkv_path, tgt_lang, probe_data)`
- An `_translate_with_manager()` durchreichen: neuer Parameter `srt_reference=srt_reference`

**Änderung `_translate_external_ass()`** (gleiche Änderung wie translate_ass):
- Auch hier `_find_srt_reference()` aufrufen und durchreichen

**Änderung `_translate_with_manager()`** (Zeile 160-204):
- Neuer optionaler Parameter: `srt_reference: list[str] | None = None`
- An `manager.translate_with_fallback()` durchreichen

---

### 3. `backend/translation/__init__.py` — TranslationManager

**Änderung `translate_with_fallback()`** (Zeile 85-155):
- Neuer optionaler Parameter: `srt_reference: list[str] | None = None`
- An `backend.translate_batch()` durchreichen
- Nur durchreichen wenn `backend.supports_srt_reference` True ist

---

### 4. `backend/translation/base.py` — Backend ABC

**Änderung `translate_batch()` Signatur** (Zeile 52-71):
```python
@abstractmethod
def translate_batch(
    self,
    lines: list[str],
    source_lang: str,
    target_lang: str,
    glossary_entries: list[dict] | None = None,
    srt_reference: list[str] | None = None,  # NEU
) -> TranslationResult:
```

Neues Klassen-Attribut:
```python
supports_srt_reference: bool = False  # Nur LLM-Backends setzen True
```

---

### 5. `backend/translation/ollama.py` — Ollama Backend

**Änderung `translate_batch()`** (Zeile 146-207):
- Neuer Parameter `srt_reference`
- An `build_translation_prompt()` durchreichen

```python
supports_srt_reference = True

def translate_batch(self, lines, source_lang, target_lang,
                    glossary_entries=None, srt_reference=None):
    prompt = build_translation_prompt(
        lines, source_lang, target_lang, glossary_entries,
        srt_reference=srt_reference,  # NEU
    )
```

**Änderung `_translate_singles()`** (Zeile 209-262):
- Ebenfalls `srt_reference` durchreichen (für Single-Line-Fallback wird Referenz-Matching
  auf die relevanten Referenzzeilen eingegrenzt)

---

### 6. `backend/translation/openai_compat.py` — OpenAI-Compatible Backend

- Gleiche Änderung wie Ollama: `supports_srt_reference = True`
- `srt_reference` an Prompt-Building durchreichen

---

### 7. `backend/translation/llm_utils.py` — Prompt Construction (Kernstück)

**Änderung `build_translation_prompt()`** (Zeile 120-147):
```python
def build_translation_prompt(
    lines: list[str],
    source_lang: str,
    target_lang: str,
    glossary_entries: list[dict] | None = None,
    prompt_template: str | None = None,
    srt_reference: list[str] | None = None,  # NEU
) -> str:
```

**Änderung `build_prompt_with_glossary()`** (Zeile 90-118):

Neue Referenz-Sektion einfügen. Wenn `srt_reference` vorhanden, wird ein
modifizierter Prompt mit Referenzblock gebaut:

```
[Glossary: ...]

Translate exactly {N} anime subtitle lines from {source} to {target}.
You MUST return exactly {N} lines. No more, no less.
Return ONLY the translated lines, one per line.
Do NOT add numbering, prefixes, or empty lines.

A German SRT subtitle exists for this video as context.
It may have different line breaks or fewer lines than the ASS source.
Use the SRT only as vocabulary/tone reference.
Translate each ASS line independently.
If the SRT phrasing seems awkward, improve it.

German SRT context (for reference only, different line splits):
---
{srt_reference_text}
---

Translate these lines:
1: first ASS line
2: second ASS line
...
```

**Wichtig:** SRT-Referenz NICHT nummeriert (vermeidet Verwechslung bei Line-Count Mismatch).

**Batch-Windowing der Referenz:**
- Bei Batch-Translation (z.B. 15 ASS-Zeilen pro Batch) nur die zeitlich relevanten
  SRT-Zeilen als Referenz mitgeben, nicht die gesamte SRT
- Naive Heuristik: Proportionales Mapping (Batch-Position / Total-Lines) auf SRT-Zeilen
- Mit Puffer: ±20% der SRT-Zeilen um den geschätzten Bereich

---

### 8. `backend/translation/deepl_backend.py`, `libretranslate.py`, `google_translate.py`

- `srt_reference` Parameter zur Signatur hinzufügen (für Interface-Kompatibilität)
- **Komplett ignorieren** — kein Prompt-Engineering möglich bei diesen APIs
- `supports_srt_reference = False` (default aus base.py)

---

### 9. Neue Datei: `backend/srt_reference.py` — SRT-Referenz-Logik (Optional)

Falls die Logik zu komplex wird für inline in translator.py, eigenes Modul:

```python
def find_srt_reference(mkv_path, target_language, probe_data=None) -> list[str] | None
def extract_srt_texts(srt_path) -> list[str]
def window_reference_for_batch(srt_lines, batch_start, batch_size, total_dialog) -> list[str]
```

Entscheidung: Inline in translator.py starten, bei >80 Zeilen auslagern.

---

## Pipeline-Flow nach Implementierung

```
Case B2: .de.srt existiert + .en.ass embedded
  ├─ _find_srt_reference() → lädt .de.srt Texte ✓ (immer vorhanden)
  ├─ translate_ass() mit srt_reference
  ├─ LLM-Prompt enthält SRT-Kontext
  ├─ Ergebnis: .de.ass (SRT-referenziert, bessere Qualität)
  └─ .de.srt bleibt erhalten (nichts wird gelöscht)

Case C1: Kein Target + .en.ass embedded
  ├─ _find_srt_reference() → prüft embedded Target-SRT oder externe .de.srt
  ├─ Wenn gefunden: translate_ass() mit srt_reference
  ├─ Wenn nicht: translate_ass() ohne Referenz (Standard-Verhalten)
  └─ Ergebnis: .de.ass

Case C3: Provider-Quelle ASS
  ├─ _find_srt_reference() → gleiche Logik
  └─ _translate_external_ass() mit srt_reference
```

---

## Config & UI

### Backend: `config.py`
```python
srt_reference_enabled: bool = True
```

### Frontend: Settings → Translation Tab
- Toggle: "Use SRT as reference for ASS translation"
- Hilfetext: "When a target-language SRT exists, use it as context to improve
  ASS translation quality. Only applies to LLM backends (Ollama, OpenAI-compatible)."
- In der bestehenden Translation-Settings-Sektion, kein neuer Tab nötig

### Stats-Erweiterung
- `result["stats"]["srt_reference_used"]`: bool — ob Referenz genutzt wurde
- Sichtbar in Activity/History für Debugging

---

## Implementierungsreihenfolge

### Task 1: Config + SRT-Erkennung
1. `config.py`: Setting `srt_reference_enabled` hinzufügen
2. `translator.py`: `_find_srt_reference()` implementieren
3. Test: Funktion findet existierende SRT-Dateien korrekt

### Task 2: Interface-Erweiterung (Durchreichung)
1. `translation/base.py`: `srt_reference` Parameter + `supports_srt_reference` Attribut
2. `translation/__init__.py`: Parameter durch TranslationManager schleusen
3. `translator.py`: `_translate_with_manager()` erweitern
4. Alle Backends: Signatur anpassen (ignorieren bei non-LLM)

### Task 3: Prompt-Engineering (Kern)
1. `translation/llm_utils.py`: `build_translation_prompt()` erweitern
2. Referenz-Block mit v2-Prompt-Format (getestet und validiert)
3. Batch-Windowing-Logik für Referenz

### Task 4: Ollama + OpenAI Integration
1. `translation/ollama.py`: `srt_reference` nutzen in `translate_batch()` + `_translate_singles()`
2. `translation/openai_compat.py`: Gleiche Änderung
3. Integration-Test: Echter Ollama-Call mit und ohne Referenz

### Task 5: Pipeline-Integration
1. `translator.py`: `translate_ass()` + `_translate_external_ass()` — `_find_srt_reference()` aufrufen
2. Stats-Feld `srt_reference_used` hinzufügen
3. Logging: Info-Level wenn Referenz gefunden/genutzt

### Task 6: Frontend + Tests
1. Settings UI: Toggle für `srt_reference_enabled`
2. Activity/History: Badge wenn SRT-Referenz genutzt
3. Backend-Tests: Unit-Tests für Prompt-Building mit Referenz
4. Integration-Test: End-to-End mit echtem Ollama

---

## Verifikation

### Automatische Tests
```bash
cd backend && python -m pytest tests/ -v
```
- `test_llm_utils.py`: Prompt-Aufbau mit/ohne SRT-Referenz
- `test_translator.py`: `_find_srt_reference()` mit Mock-Dateien
- `test_config.py`: Neues Setting wird erkannt

### Manueller E2E-Test
1. MKV mit eingebettetem .en.ass + existierender .de.srt vorbereiten
2. `POST /api/v1/translate` aufrufen
3. Prüfen: Logs zeigen "SRT reference found" Info
4. Prüfen: Ergebnis-ASS enthält natürlichere Übersetzung
5. Prüfen: .de.srt bleibt unverändert
6. Setting abschalten → translate nochmal → keine Referenz genutzt

### Qualitätsvergleich
- Gleiche Episode mit/ohne Referenz übersetzen
- Ergebnisse vergleichen (Formulierung, Konsistenz, Speed)
