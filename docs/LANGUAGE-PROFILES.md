# Language Profiles

Language profiles control which subtitle languages Sublarr searches for and translates to, on a per-series basis.

---

## Overview

A language profile is a named configuration that specifies:

- **Target languages** — what languages to search for or translate to
- **Format preference** — ASS preferred, SRT fallback, or any
- **Translation settings** — which backend to use, prompt preset
- **Upgrade rules** — when to replace an existing subtitle

Each series or movie can be assigned one language profile. If no profile is assigned, the global defaults from Settings apply.

---

## Creating a Language Profile

1. Go to **Settings → Translation → Language Profiles**
2. Click **Add Profile**
3. Configure:
   - **Name** — e.g., "Anime DE", "Movies EN", "Documentary FR"
   - **Target Language** — the language to translate to (or download in)
   - **Source Language** — the original subtitle language (usually `en`)
   - **Format Preference** — ASS preferred, SRT only, or any
   - **Translation Backend** — Ollama, DeepL, LibreTranslate, etc.
   - **Prompt Preset** — which translation style to apply
4. Save

---

## Assigning Profiles to Series

### Manual Assignment

1. Go to **Library → Series**
2. Click on a series
3. In Series Detail, select the language profile from the dropdown
4. Click Save

### Tag-Based Automatic Assignment

If you use Sonarr/Radarr tags, Sublarr can automatically assign profiles based on tags:

1. Go to **Settings → Integrations → Tag Profile Mapping**
2. Add mappings like:
   - Tag `anime-de` → Profile "Anime DE"
   - Tag `documentary` → Profile "Documentary FR"
3. Save

Sublarr reads tags from Sonarr/Radarr when processing webhooks and assigns the matching profile automatically.

---

## Multi-Language Profiles

One profile can target multiple languages simultaneously. For example, a profile that downloads both German and French subtitles:

1. In the profile editor, add multiple target languages
2. Sublarr will search for and translate to each language independently
3. Per-language settings (backend, prompt) can be overridden per entry

---

## Default Profile

The **Global Default** profile applies when no series-specific profile is assigned. Set the defaults at **Settings → Translation**:

```
SUBLARR_SOURCE_LANGUAGE=en
SUBLARR_TARGET_LANGUAGE=de
```

---

## Profile Lookup Order

When processing a subtitle request, Sublarr checks profiles in this order:

1. Series-specific profile (set in Library)
2. Tag-assigned profile (from Sonarr/Radarr tags)
3. Global default settings

---

## Format Scoring with Profiles

Profiles interact with the scoring system:

- **ASS Preferred** — ASS candidates get +50 bonus in scoring
- **SRT Only** — ASS candidates scored at 0 (effectively filtered out)
- **Upgrade Prefer ASS** — SRT → ASS upgrade triggered regardless of score delta

For anime, always use **ASS Preferred** with **Upgrade Prefer ASS** enabled. This ensures you always get styled fansub subtitles when available.

---

## Translation Pipeline per Profile

The translation pipeline for each profile:

1. **Search** — query all enabled providers for the target language
2. **Score** — rank results by format, file size, hash match, uploader trust
3. **Download** — fetch the best match
4. **HI Removal** (if enabled) — strip hearing-impaired markers
5. **Translate** — call the configured backend with the configured prompt
6. **Quality Score** (if enabled) — LLM scores each translated line; low scores trigger retry
7. **Save** — write `.{lang}.ass` or `.{lang}.srt` next to the video file
8. **Media Server Refresh** — trigger library scan on configured servers

---

## Troubleshooting

**Profile not applied to series:**
- Check Settings → Integrations → Tag Profile Mapping for conflicts
- Verify the series is in the Library (Sublarr must have scanned it first)

**Wrong language downloaded:**
- Verify the target language code is correct (ISO 639-1: `en`, `de`, `ja`, `fr`, etc.)
- Check if the provider supports the target language

**Translation not running:**
- Ensure `SUBLARR_WEBHOOK_AUTO_TRANSLATE=true`
- Check the Queue page for failed translation jobs
