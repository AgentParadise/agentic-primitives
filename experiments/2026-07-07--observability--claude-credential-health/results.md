# Results

| Probe | Evidence | Result |
|---|---|---|
| Host Claude auth | `runs/host-claude-stdout.txt`, `runs/host-claude-stderr.txt`, `runs/host-claude-exit.txt` | Host `claude -p` succeeded and printed `CLAUDE_HOST_AUTH_OK`. |
| Container credential shape | `runs/start-report.json`, `runs/container-credential-shape.json`, `runs/summary.json` | Claude-only workspace started. Container had `.credentials.json` and `.claude.json`; `.credentials.json` had access token length 108 but refresh token length 0. |
| Recipe-driven Claude run | `runs/itmux-run-stdout.jsonl`, `runs/itmux-run-events.jsonl`, `runs/itmux-run-result.json`, `runs/summary.json` | Reproduced 401: run exited 3, result success false, session log contained `API Error: 401`. File exporter still wrote 11 events. |

## Key Data

| Field | Value |
|---|---|
| Host `CLAUDE_CODE_OAUTH_TOKEN` env | set |
| Host Claude command exit | 0 |
| Container `.credentials.json` exists | true |
| Container access token length | 108 |
| Container refresh token length | 0 |
| Container `.claude.json` exists | true |
| Container `.claude.json` has `oauthAccount` | true |
| `itmux run` exit | 3 |
| `itmux run` 401 observed | true |

## Classification

The 401 is not proof that the host account is invalid. Host Claude succeeds, but
the host success path is backed by `CLAUDE_CODE_OAUTH_TOKEN` in the environment.
The Docker workspace does not receive that env token. Its disk credential file
contains an expired access token and no usable refresh token after Claude starts,
so the first submitted prompt fails with 401.

This makes Claude hook validation blocked on a credential-delivery decision:
either securely inject the env OAuth token into the workspace/Claude process, or
require a fresh disk login/credential shape that preserves refresh capability.
