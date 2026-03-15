# V9 Sublarr Integration Plan

> **Kontext:** anime-translator-en-de-v9 basiert auf TranslateGemma-12B (SFT + DPO).
> Das Modell wurde mit einem fixen Chat-Format trainiert — Sublarr muss dieses Format
> exakt replizieren, sonst degradiert die Qualität trotz besserem Modell.

---

## 1. Optimales Prompt-Format für V9

### Warum `/api/chat` statt `/api/generate`

V9 ist ein Chat-Fine-Tune (Gemma-3 Chat Template). Sublarr verwendet aktuell
`/api/generate` mit einem rohen Prompt-String. Das funktioniert, weil Ollama die
Chat-Template-Wrapping intern erledigt — aber dabei geht die System-Prompt-Trennung
verloren und Serienkontexte können nicht sauber injiziert werden.

**V9 muss `/api/chat` verwenden** mit expliziter System/User-Trennung.

---

### Prompt-Format: Single-Line (1 Zeile)

**System-Turn (immer identisch, optional + Serienkontext):**
```
Du bist ein spezialisierter Anime-Untertitel-Übersetzer. Übersetze englische
Anime-Untertitel präzise und natürlich ins Deutsche. Verwende informelle Sprache
(du-Form). Behalte Charakternamen und Eigennamen unverändert. Keine Erklärungen
oder Kommentare — nur die Übersetzung.
```
Mit Serienkontext (wenn verfügbar):
```
[System-Prompt]. Serie: Attack on Titan. Genre: Action, Drama.
```

**User-Turn (ohne Glossar):**
```
Translate to German: It's not over yet.
```

**User-Turn (mit Glossar):**
```
Glossary: Survey Corps → Aufklärungstrupp, Titan → Titan, ODM → ODM-Gerät

Translate to German: The Survey Corps never gives up.
```

**Erwartete Modell-Antwort:**
```
Die Aufklärungstrupp gibt niemals auf.
```

---

### Prompt-Format: Multi-Line Batch (2–25 Zeilen)

**System-Turn:** identisch zu Single-Line (mit optionalem Serienkontext)

**User-Turn (ohne Glossar):**
```
Translate these anime subtitle lines from English to German.
Return ONLY the translated lines, one per line, same count.
Preserve \N exactly as \N (hard line break).
Do NOT add numbering or prefixes to the output lines.

1: It's not over yet.
2: We have to keep fighting.
3: For everyone we've lost.
```

**User-Turn (mit Glossar):**
```
Glossary: Survey Corps → Aufklärungstrupp, ODM → ODM-Gerät

Translate these anime subtitle lines from English to German.
Return ONLY the translated lines, one per line, same count.
Preserve \N exactly as \N (hard line break).
Do NOT add numbering or prefixes to the output lines.

1: The Survey Corps charges forward.
2: Use your ODM gear!
3: Don't give up now.
```

**Erwartete Modell-Antwort:**
```
Die Aufklärungstrupp stürmt vor.
Benutze dein ODM-Gerät!
Gib jetzt nicht auf.
```

---

### Glossar-Regeln (unverändert gegenüber V8)

- Format: `Glossary: term1 → trans1, term2 → trans2`
- Nur `approved != 0` Einträge injizieren
- Max 15 Einträge pro Request
- Leerzeile nach dem Glossar-Block (vor dem Prompt-Text)
- Globale Einträge (series_id IS NULL) + serienspezifische Einträge mergen (serienspezifisch überschreibt global)

---

## 2. Sublarr Code-Änderungen

### 2.1 `translation/ollama.py` — Chat API + Serienkontext

**Neue Config-Felder hinzufügen:**

```python
{
    "key": "use_chat_api",
    "label": "Chat API verwenden (V9+)",
    "type": "checkbox",
    "required": False,
    "default": "false",
    "help": "Für V9-Modelle: /api/chat statt /api/generate verwenden",
},
{
    "key": "system_prompt",
    "label": "System Prompt",
    "type": "textarea",
    "required": False,
    "default": "Du bist ein spezialisierter Anime-Untertitel-Übersetzer. Übersetze englische Anime-Untertitel präzise und natürlich ins Deutsche. Verwende informelle Sprache (du-Form). Behalte Charakternamen und Eigennamen unverändert. Keine Erklärungen oder Kommentare — nur die Übersetzung.",
    "help": "System-Prompt für Chat-API-Modus. {series_context} wird durch 'Serie: Name. Genre: ...' ersetzt.",
},
```

**`translate_batch()` Signatur erweitern:**
```python
def translate_batch(
    self,
    lines: list[str],
    source_lang: str,
    target_lang: str,
    glossary_entries: list[dict] | None = None,
    series_context: str | None = None,   # NEU
) -> TranslationResult:
```

**Neue `_call_ollama_chat()` Methode:**
```python
def _call_ollama_chat(self, system_prompt: str, user_prompt: str) -> str:
    payload = {
        "model": self._model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        "stream": False,
        "options": {
            "temperature": self._temperature,
            "num_predict": 4096,
            "num_ctx": 4096,
        },
    }
    resp = requests.post(
        f"{self._url}/api/chat",
        json=payload,
        timeout=self._request_timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["message"]["content"].strip()
```

**Dispatch-Logik in `translate_batch()`:**
```python
if self._use_chat_api:
    system = self._build_system_prompt(series_context)
    user = build_translation_prompt(lines, source_lang, target_lang, glossary_entries)
    response = self._call_ollama_chat(system, user)
else:
    # legacy: /api/generate (V6/V7/V8 Kompatibilität)
    prompt = build_translation_prompt(lines, source_lang, target_lang, glossary_entries)
    response = self._call_ollama(prompt)
```

---

### 2.2 `translation/base.py` — Serienkontext im Interface

```python
@abstractmethod
def translate_batch(
    self,
    lines: list[str],
    source_lang: str,
    target_lang: str,
    glossary_entries: list[dict] | None = None,
    series_context: str | None = None,   # NEU — optional, backward-kompatibel
) -> TranslationResult:
```

Alle anderen Backends (DeepL, Google, etc.) ignorieren `series_context` einfach.

---

### 2.3 `translator.py` — Serienkontext weitergeben

Bei jedem `translate_with_fallback()`-Aufruf den Serienkontext aus dem Job-Kontext
extrahieren und weitergeben:

```python
# Serienkontext aus bazarr_context_json oder Sonarr-Metadaten bauen
series_context = None
if series_title:
    series_context = f"Serie: {series_title}."
    if series_genre:
        series_context += f" Genre: {', '.join(series_genre[:2])}."

result = backend.translate_batch(
    lines=lines,
    source_lang=source_lang,
    target_lang=target_lang,
    glossary_entries=glossary_entries,
    series_context=series_context,   # NEU
)
```

---

### 2.4 `translation/llm_utils.py` — Quality Evaluator Fix

Der aktuelle Evaluator gibt fast immer DEFAULT_QUALITY_SCORE (50) zurück, weil der
LLM keinen reinen Integer ausgibt.

**Neues Evaluierungs-Prompt (zuverlässigere Extraktion):**

```python
def build_evaluation_prompt(...) -> str:
    return (
        f"Bewerte diese Untertitel-Übersetzung. "
        f"Antworte NUR mit einer einzigen Zahl von 0 bis 100.\n\n"
        f"Original (EN): {source_text}\n"
        f"Übersetzung (DE): {translated_text}\n\n"
        f"Kriterien: Bedeutung korrekt (40%), natürliches Deutsch (40%), "
        f"Länge passend (20%). Zahl:"
    )
```

**Robusteres Score-Parsing:**
```python
def parse_quality_score(response_text: str) -> int:
    # Zuerst: erste Zahl am Anfang der Antwort suchen (Modell soll nur Zahl ausgeben)
    text = response_text.strip()
    first_token = text.split()[0] if text else ""
    try:
        score = int(first_token)
        return max(0, min(100, score))
    except ValueError:
        pass
    # Fallback: alle Zahlen suchen, letzte nehmen
    matches = re.findall(r'\b(100|[1-9]?\d)\b', text)
    if matches:
        return max(0, min(100, int(matches[-1])))
    return DEFAULT_QUALITY_SCORE
```

---

## 3. Ollama Modelfile für V9

Beim Deployment auf dem Mac mini (`05_export_gguf.py`) folgendes Modelfile verwenden:

```
FROM /Users/denniswittke/models/anime-translator-en-de-v9-Q5_K_M.gguf

PARAMETER temperature 0.3
PARAMETER top_p 0.9
PARAMETER top_k 40
PARAMETER num_ctx 4096
PARAMETER num_predict 1024

# System-Prompt wird per Request von Sublarr injiziert (Chat API)
# Kein SYSTEM-Block hier — Sublarr kontrolliert den Kontext vollständig
```

**Wichtig:** Kein `SYSTEM`-Block im Modelfile — Sublarr injiziert den System-Prompt
dynamisch (inkl. Serienkontext) über `/api/chat`.

---

## 4. Sublarr Settings — V9 Konfiguration

Nach dem Deployment folgende Werte in den Sublarr-Einstellungen setzen:

| Setting | Wert |
|---------|------|
| Ollama URL | `http://192.168.178.155:11434` |
| Model | `anime-translator-en-de-v9` |
| Chat API | ✅ aktiviert |
| Temperature | `0.3` |
| Timeout | `120` |
| Max Retries | `3` |
| Batch Size | `25` |
| System Prompt | *(Standard aus config_field default)* |

---

## 5. Reihenfolge der Änderungen

```
1. [ ] translation/base.py       — series_context Parameter hinzufügen
2. [ ] translation/ollama.py     — use_chat_api, system_prompt, _call_ollama_chat()
3. [ ] translation/llm_utils.py  — Quality Evaluator Prompt + Parser Fix
4. [ ] translator.py             — series_context aus Job-Kontext extrahieren + weitergeben
5. [ ] Tests anpassen            — test_ollama_backend.py, test_llm_utils.py
6. [ ] V9 deployen               — nach 05_export_gguf.py
7. [ ] Sublarr config setzen     — use_chat_api=True, model=v9
```

---

## 6. Backward-Kompatibilität

Alle Änderungen sind rückwärtskompatibel:
- `use_chat_api=False` (default) → bestehende V6-Deployments laufen unverändert
- `series_context=None` → alle anderen Backends ignorieren den Parameter
- Neues Evaluator-Prompt ist modellunabhängig

Beim V9-Rollout: nur `use_chat_api=True` und `model=anime-translator-en-de-v9` setzen.

---

*Erstellt: 2026-03-15 | Für: Sublarr v0.29+ | Modell: anime-translator-en-de-v9*
