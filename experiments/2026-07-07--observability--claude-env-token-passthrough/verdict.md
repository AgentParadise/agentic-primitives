# Verdict

**Go for Claude recipe credential health; continue to Claude hook ingestion.**

The env passthrough fix converted the previously failing recipe-driven Claude
run from 401 to success while preserving exporter parity. This does not yet
prove the observability plugin hook stream, but it removes the authentication
blocker that prevented that validation.

## Hypothesis scorecard

| Predicted | Observed | Score | Notes |
|---|---|---|---|
| Docker argv uses `-e CLAUDE_CODE_OAUTH_TOKEN` without a token value | Unit test passed before live run | correct | `docker_run_argv_passes_env_names_without_secret_values` |
| Recipe-driven Claude run succeeds | Exit 0, result success true, session contained `CLAUDE_ENV_TOKEN_OK` | correct | `runs/itmux-run-result.json` |
| File exporter remains consistent | 11 stdout events, 11 exported events, exporter status `ok` | correct | `runs/summary.json` |

## Design Impact

- `.6` no longer has a basic Claude Docker auth blocker for host-token-backed
  runs.
- The env bridge is intentionally narrow: only Claude receives
  `CLAUDE_CODE_OAUTH_TOKEN`, and Docker argv carries only the env var name.
- Next validation should rerun the Claude hook/file-fanout experiment with the
  observability plugin loaded.
