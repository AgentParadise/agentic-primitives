# Results

| Probe | Evidence | Result |
|---|---|---|
| Codex run artifact capture | `runs/codex-stdout.jsonl`, `runs/codex-events.jsonl`, `runs/codex-result.json`, `runs/summary.json` | `itmux run` Codex TUI succeeded and file fanout exported 11 driver-level events, but no token usage event. |
| Codex surface inventory | `runs/codex-files.txt`, `runs/codex-surface-inventory.md`, `runs/codex-exec-default-json.jsonl` | `codex exec --json` is the viable structured usage source; TUI remains coarse pane/driver observability only. |

## Mapping Table

See `runs/codex-surface-inventory.md` for the full table.

| Source | Contains lifecycle? | Contains tool events? | Contains token/cost? | Parser viable? |
|---|---|---|---|---|
| `itmux run` Codex TUI stdout/exporter JSONL | driver phases only | driver tools only | no | yes, coarse only |
| `itmux run` Codex TUI session log | visible pane transcript | not structured in this probe | no | fragile fallback |
| `codex exec --json` default model | yes | yes through `item.completed` stream shape | yes: `turn.completed.usage` | yes, first implementation target |
| host `~/.codex/state_5.sqlite.threads` | persisted metadata | no live stream | aggregate `tokens_used` column | offline reconciliation only |

## Key Data

- Codex TUI run: exit 0, 11 stdout events, 11 exported events, result success
  true, zero `token_usage` events.
- Codex exec default run: exit 0, event sequence `thread.started`,
  `turn.started`, `item.completed`, `turn.completed`.
- Codex exec default usage: `input_tokens=15919`,
  `cached_input_tokens=9600`, `output_tokens=11`,
  `reasoning_output_tokens=0`.
- `codex exec --json --model gpt-5` failed for this account with a 400 model
  support error, but still emitted failure lifecycle events.
