# Phase 19: Context-Window Batching - Research

**Researched:** 2026-02-22
**Domain:** LLM translation pipeline extension -- subtitle context injection
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Context size:** Default 3 lines before + 3 lines after. Configurable 0-10. Single symmetric setting. When 0 -> feature disabled, pipeline unchanged.
- **Prompt structure:** [CONTEXT - DO NOT TRANSLATE] block for preceding lines, [TRANSLATE THESE LINES] block for target lines, [CONTEXT - DO NOT TRANSLATE] block for following lines. Each context line shows timing + text. System prompt reinforces translate ONLY lines in TRANSLATE block.
- **Edge behavior:** Start/end of file uses however many lines exist (no padding). Scene break at >5 seconds gap stops context inclusion. Very short files (<3 lines total) use all available lines as context.
- **Settings UX:** Settings -> Translation tab. Single number input Context window (lines), range 0-10. Stored as Pydantic Settings field context_window_size, default 3. No per-profile override this phase.

### Claude Discretion
- Exact prompt wording / system message copy
- Whether timing info per context line is ms or HH:MM:SS format
- Internal batch assembly algorithm
- Performance: whether context lines add to token count tracking

### Deferred Ideas (OUT OF SCOPE)
- Per-language-profile context window override
- Asymmetric windows
</user_constraints>

---

