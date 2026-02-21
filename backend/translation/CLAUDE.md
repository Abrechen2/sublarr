# Translation — LLM-Übersetzungs-System

## Drei-Stufen-Pipeline (`translator.py`)

```
Case A: Ziel-ASS vorhanden          → Skip (nichts tun)
Case B: Ziel-SRT vorhanden
  B1: Provider hat besseres ASS     → ASS herunterladen + ersetzen
  B2: kein besseres ASS verfuegbar  → SRT uebersetzen via LLM
Case C: Kein Ziel-Sub
  C1: Embedded Subs extrahierbar    → extrahieren + uebersetzen
  C2: Provider-Treffer              → downloaden + uebersetzen
  C3: kein Ergebnis                 → in Wanted-Liste eintragen
```

## ASS Style-Klassifizierung (`ass_utils.py`)

- **Dialog-Styles** → werden uebersetzt
- **Signs/Songs** → bleiben original (Erkennungsmerkmal: >80% `\pos()` oder `\move()` Tags)
- Funktion: `classify_style(style_name, events) -> "dialog" | "signs_songs"`

## Translation-Backends (`backend/translation/`)

| Backend | Datei | Anforderung |
|---------|-------|-------------|
| Ollama | `ollama.py` | Lokale Instanz (Default: Mac mini :11434) |
| DeepL | `deepl_backend.py` | API-Key |
| LibreTranslate | `libretranslate.py` | Self-hosted URL |
| OpenAI-kompatibel | `openai_compat.py` | API-Key + URL (z.B. LM Studio) |
| Google Translate | `google_translate.py` | Cloud-Credentials |

Backend-Auswahl: `config_entries` DB oder `SUBLARR_TRANSLATION_BACKEND` Env-Var.

## Ollama-Client (`ollama_client.py`)

- Prompt aus Config (`SUBLARR_TRANSLATION_PROMPT`)
- Chunked Translation: Lange Dialoge in Batches aufteilen
- Modell-Default: `qwen2.5:14b-instruct`
- Timeout: 300s (lange Dialoge brauchen Zeit)

## Wichtige Konventionen

- **Nie Original ueberschreiben** — immer neue Datei `.{lang}.ass` anlegen
- **Hearing-Impaired Tags** (`hi_remover.py`) vor Uebersetzung entfernen wenn konfiguriert
- **Batch-Operationen** immer mit Bestaetigung — belasten GPU stark
