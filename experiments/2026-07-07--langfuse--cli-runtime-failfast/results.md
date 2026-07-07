# Results

## Summary

| Probe | Evidence | Result |
| --- | --- | --- |
| Runtime fail-fast | `runs/runtime-exit.txt`, `runs/result.json`, `runs/stdout.jsonl`, `runs/stderr.txt` | Passed: command exited 0, run succeeded, and LangFuse exporter reported `status = failed` because `LANGFUSE_BASE_URL` was missing. |
| Artifact inspection | `runs/inspection-summary.txt` | Passed: stdout contained 6 valid event lines with seq `0..5`; result carried one failed `langfuse_otlp` exporter. |
| Format check | `runs/fmt-check.txt`, `runs/fmt-check-exit.txt` | Passed: exited 0. |
| Full driver tests | `runs/full-test.txt`, `runs/full-test-exit.txt` | Passed: exited 0. |
| Clippy | `runs/clippy.txt`, `runs/clippy-exit.txt` | Passed: exited 0. |

## Exit Codes

| Command | Exit |
| --- | ---: |
| runtime probe | 0 |
| fmt check | 0 |
| full test | 0 |
| clippy | 0 |

## Observations

- The fake Codex harness emitted representative successful `codex exec --json`
  lines.
- `itmux codex-exec --observability-langfuse` produced a successful
  `AgentRunResult` even though LangFuse config was absent.
- The final result included:
  - `kind = langfuse_otlp`
  - `status = failed`
  - `events_exported = 0`
  - `error = missing required LangFuse config: LANGFUSE_BASE_URL`
  - no links
- Stdout stayed pure `AgentRunEvent` JSONL:
  `tool_start, tool_start, tool_end, tool_end, token_usage, session_end`.
- Cargo still prints non-fatal APSS template diagnostics about `{{slug}}`
  package names from the git dependency checkout.
