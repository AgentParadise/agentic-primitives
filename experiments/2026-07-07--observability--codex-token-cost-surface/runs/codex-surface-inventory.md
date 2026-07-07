# Codex Surface Inventory

| Source | Contains lifecycle? | Contains tool events? | Contains token/cost? | Parser viable? | Evidence |
|---|---|---|---|---|---|
| `itmux run` Codex TUI stdout/exporter JSONL | driver phase lifecycle only (`tool_start`, `tool_end`, `session_end`) | driver tools only, no Codex internal tool calls | no | yes for coarse run phases only | `codex-stdout.jsonl`, `codex-events.jsonl` |
| `itmux run` Codex TUI session log | pane/UI transcript | visible final answer, no structured tools in this probe | no | fragile fallback only | `codex-result.json.session_log` |
| `codex exec --json` with default model | yes (`thread.started`, `turn.started`, `turn.completed`) | yes when `item.completed` items represent messages/tool items; this probe has `agent_message` | yes: `turn.completed.usage` | yes; best first Codex observer for one-shot runs | `codex-exec-default-json.jsonl` |
| `codex exec --json --model gpt-5` | failure lifecycle (`thread.started`, `turn.started`, `turn.failed`) | no | no successful usage because model rejected | viable for failures, but model config must be account-compatible | `codex-exec-json.jsonl` |
| host `~/.codex/session_index.jsonl` | session index metadata | no | no | useful for discovery, not event stream | redacted key sample below |
| host `~/.codex/history.jsonl` | prompt history metadata | no | no | not suitable as observer source | redacted key sample below |
| host `~/.codex/state_5.sqlite.threads` | persisted thread metadata, includes `tokens_used` column | no row-level stream | aggregate token count column, not live turn usage | useful for offline reconciliation, not primary live observer | sqlite schema inspection |
| host `~/.codex/logs_2.sqlite.logs` | diagnostic logs with `thread_id` | maybe diagnostic lifecycle only | no obvious token/cost schema | secondary diagnostics only | sqlite schema inspection |

Recommendation: implement `codex_exec_json` first for one-shot runs because it gives structured lifecycle and `turn.completed.usage`. Keep `codex_tui` as a coarse pane/driver observer until an in-container session/log source is proven; do not promise token/cost parity for Codex TUI from current evidence.
