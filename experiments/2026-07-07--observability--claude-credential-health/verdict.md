# Verdict

**No-go for Claude hook validation until credential delivery is fixed.**

The source of the 401 is now classified. Host Claude auth is healthy because
`CLAUDE_CODE_OAUTH_TOKEN` is set. The interactive-tmux Docker workspace relies
on staged disk credentials, and the staged container credential state has an
expired access token with an empty refresh token. Recipe-driven `itmux run`
therefore reproduces the 401 on first prompt submission.

## Hypothesis scorecard

| Predicted | Observed | Score | Notes |
|---|---|---|---|
| Host `claude -p` succeeds | Succeeded with exit 0 and expected output | correct | `runs/host-claude-stdout.txt` |
| Container staging has expected redacted credential shape | Files existed, but refresh token length was 0 | partial | Shape present, but not usable for refresh. |
| `itmux run` still fails with Claude 401 | Reproduced exit 3 and `API Error: 401` | correct | `runs/itmux-run-result.json` |

## Design Impact

- `.6` should not claim Claude hook observability until Claude credential
  delivery works for a submitted prompt.
- The next architecture decision is how to securely bridge
  `CLAUDE_CODE_OAUTH_TOKEN` or equivalent fresh credential material into
  Docker workspaces without leaking secrets through argv or stdout.
- The existing file fanout remains valid: even the failed Claude run exported
  11 normalized driver events and reported exporter status `ok`.
