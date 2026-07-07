# Results

| Probe | Evidence | Result |
|---|---|---|
| Local baseline | `runs/baseline-stdout.jsonl`, `runs/baseline-events.jsonl`, `runs/baseline-result.json`, `runs/summary.json` | File exporter worked with 11 stdout events and 11 exported events, but Claude run failed with 401. |
| Historical LangFuse export attempt | `runs/langfuse-treatment-not-run.txt`, `runs/langfuse-trace-summary.json` | Not run at the time: no LangFuse/OTEL exporter existed then and LangFuse env was absent. |
| Current CLI rerun | `runs/current/stdout.jsonl`, `runs/current/events.jsonl`, `runs/current/result.json`, `runs/current/summary.txt` | Current exporter path exists and runs: file exporter `ok` with 6 events; LangFuse exporter `failed` because `LANGFUSE_BASE_URL` is missing. |
| Regression hygiene | `runs/current/fmt-check.txt`, `runs/current/full-test.txt`, `runs/current/clippy.txt` | Passed: fmt, full driver tests, and clippy all exited 0. |

## Observations

- Historical baseline repeats the Claude credential issue seen in the Claude
  hook experiment: the harness reached Claude Code, then failed with Anthropic
  401.
- Current fanout supports `file` and `langfuse_otlp`.
- Current CLI setup can instantiate both exporters in one run.
- Real LangFuse export still cannot be proven in this shell because all
  required LangFuse env vars are absent.
- The current rerun keeps local observability intact while surfacing the missing
  LangFuse config as an exporter failure.
