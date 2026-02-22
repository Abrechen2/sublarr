# Phase 19: Context-Window Batching - Context

**Gathered:** 2026-02-22
**Status:** Ready for planning

<domain>
## Phase Boundary

Extend the LLM translation pipeline so each translation call includes N surrounding
subtitle lines as read-only context alongside the target lines. The LLM sees the
conversational flow and produces more coherent output (correct pronouns, scene-aware
references). Context lines are never translated — only provided for awareness.

Creating/managing subtitle batches, caching translations, or quality scoring are
separate phases.

</domain>

<decisions>
## Implementation Decisions

### Context size
- Default: **3 lines before + 3 lines after** the target batch
- Configurable: 0 (disabled) to 10 lines per direction
- Single setting covers both directions (symmetric window)
- When context_window_size = 0 → feature disabled, pipeline unchanged

### Prompt structure
- Prompt uses clearly labeled sections so the LLM never confuses context with targets:
  - `[CONTEXT - DO NOT TRANSLATE]` block for preceding lines
  - `[TRANSLATE THESE LINES]` block for target lines
  - `[CONTEXT - DO NOT TRANSLATE]` block for following lines
- Each context line shown with its timing + text (same format as target lines)
- System prompt reinforces: translate ONLY the lines in the TRANSLATE block

### Edge & boundary behavior
- **Start of file:** use however many lines exist before (0 to N-1), no padding
- **End of file:** same — use available lines, no wrapping
- **Scene break detection:** if the time gap between context line and target block
  exceeds **5 seconds**, stop including further context in that direction
  (prevents unrelated dialogue from polluting context)
- **Very short files (< 3 lines total):** use all available lines as context

### Settings UX
- Located in: Settings → Translation tab, alongside existing translation config
- Single number input `Context window (lines)` with range 0–10
- Stored as global `config_entry`: key = `translation.context_window_size`, default = 3
- No per-profile override in this phase (global setting sufficient for v1)

### Claude's Discretion
- Exact prompt wording / system message copy
- Whether timing info per context line is ms or HH:MM:SS format
- Internal batch assembly algorithm (how batches are sliced from the subtitle list)
- Performance: whether context lines add to token count tracking

</decisions>

<specifics>
## Specific Ideas

- Scene break threshold (5s) mirrors common subtitle editing conventions for scene changes
- The prompt structure (labeled blocks) follows OpenAI best-practice for instruction-following tasks

</specifics>

<deferred>
## Deferred Ideas

- Per-language-profile context window override — global is fine for now, can add in a later polish phase
- Asymmetric windows (more preceding context than following) — not needed yet

</deferred>

---

*Phase: 19-context-window-batching*
*Context gathered: 2026-02-22*
