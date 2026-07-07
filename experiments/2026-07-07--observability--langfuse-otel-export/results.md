# Results

| Probe | Evidence | Result |
|---|---|---|
| Local baseline | `runs/baseline-stdout.jsonl`, `runs/baseline-events.jsonl`, `runs/baseline-result.json`, `runs/summary.json` | File exporter worked with 11 stdout events and 11 exported events, but Claude run failed with 401. |
| LangFuse export | `runs/langfuse-treatment-not-run.txt`, `runs/langfuse-trace-summary.json` | Not run: no LangFuse/OTEL exporter exists in the current `ObservabilityExporter` enum and LangFuse env is absent. |

## Observations

- Current fanout supports `file` only.
- The LangFuse exporter cannot be configured without extending the contract and
  fanout implementation.
- The local baseline repeats the Claude credential issue seen in the Claude hook
  experiment: the harness reaches Claude Code, then fails with Anthropic 401.
