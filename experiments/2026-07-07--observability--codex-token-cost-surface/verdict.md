# Verdict

**Go for `codex_exec_json`; no-go for token/cost parity from Codex TUI alone.**

This was a declared mapping probe, so there is no hypothesis scorecard. The
result is clear enough to drive design: implement a dedicated `codex_exec_json`
observer first, and keep `codex_tui` as a coarse driver/pane observer until a
better live TUI source is proven.

## Mapping Result

| Source | Contains lifecycle? | Contains tool events? | Contains token/cost? | Parser viable? |
|---|---|---|---|---|
| `itmux run` Codex TUI JSONL | driver lifecycle only | driver tool phases only | no | yes, coarse only |
| Codex TUI session log | pane transcript | not structured | no | fragile fallback |
| `codex exec --json` | yes | yes via event items | yes via `turn.completed.usage` | yes |
| Codex sqlite/thread metadata | persisted metadata | no live stream | aggregate fields only | reconciliation only |

## Recommendation

Build `.6` observer interfaces around collection surfaces, not vendors:

- `codex_exec_json` should parse `codex exec --json` directly into
  `AgentRunEvent`, including `TokenUsage`.
- `codex_tui` should initially emit only coarse driver/session events and
  captured transcript links.
- Do not claim Codex TUI token/cost parity until another experiment proves an
  in-container live usage source.
