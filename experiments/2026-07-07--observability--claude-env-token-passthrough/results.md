# Results

| Probe | Evidence | Result |
|---|---|---|
| Command-plan safety | `cargo test --test cred_transfer` before run; see implementation commit `7764245` | Passed: Docker argv includes `-e CLAUDE_CODE_OAUTH_TOKEN`, never `NAME=value`, and Codex does not receive Claude env auth. |
| Claude recipe run | `runs/itmux-run-stdout.jsonl`, `runs/itmux-run-events.jsonl`, `runs/itmux-run-result.json`, `runs/summary.json` | Passed: exit 0, result success true, session contained `CLAUDE_ENV_TOKEN_OK`, and no `API Error: 401`. |
| File exporter | `runs/itmux-run-stdout.jsonl`, `runs/itmux-run-events.jsonl`, `runs/itmux-run-result.json` | Passed: stdout had 11 events, exporter file had 11 events, exporter status `ok`, `events_exported = 11`. |

## Key Data

| Field | Value |
|---|---|
| Host `CLAUDE_CODE_OAUTH_TOKEN` env | set |
| `itmux run` exit | 0 |
| Result success | true |
| Session contains `CLAUDE_ENV_TOKEN_OK` | true |
| Session contains `API Error: 401` | false |
| Stdout event lines | 11 |
| Exporter event lines | 11 |
| Exporter status | ok |

## Classification

Passing `CLAUDE_CODE_OAUTH_TOKEN` into the Docker workspace by environment
variable name fixes the previously reproduced recipe-driven Claude 401 for this
host. The file fanout remains consistent after the fix.

This validates the credential-delivery path needed before rerunning Claude hook
observability. The remaining Claude work is hook/plugin event ingestion, not
basic prompt execution auth.
