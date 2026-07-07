# Results

## Summary

| Probe | Evidence | Result |
| --- | --- | --- |
| Mixed exporter runtime | `runs/runtime-exit.txt`, `runs/result.json`, `runs/stdout.jsonl`, `runs/events.jsonl`, `runs/stderr.txt` | Passed: command exited 0; file exporter reported `ok`; LangFuse exporter reported `failed`. |
| Artifact inspection | `runs/inspection-summary.txt` | Passed: stdout and file exporter both contained 6 events with matching types and seq `0..5`. |
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

- The run result was successful.
- The file exporter report was independent of the LangFuse failure:
  - `kind = file`
  - `status = ok`
  - `events_exported = 6`
  - one link to `runs/events.jsonl`
- The LangFuse exporter report failed cleanly:
  - `kind = langfuse_otlp`
  - `status = failed`
  - `events_exported = 0`
  - `error = missing required LangFuse config: LANGFUSE_BASE_URL`
  - no links
- `runs/stdout.jsonl` and `runs/events.jsonl` both contained:
  `tool_start, tool_start, tool_end, tool_end, token_usage, session_end`.
- Sequence numbers matched exactly: `0,1,2,3,4,5`.
- Cargo still prints non-fatal APSS template diagnostics about `{{slug}}`
  package names from the git dependency checkout.
