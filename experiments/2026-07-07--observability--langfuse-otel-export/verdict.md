# Verdict

**No-go for `.9` implementation until `.6` adds the exporter interface and the
LangFuse OTLP smoke passes.**

This experiment confirms the ordering: `.9` depends on `.6` not just as a board
edge, but technically. The current primitive can export local JSONL; it cannot
yet instantiate a LangFuse/OTEL exporter or produce trace links.

## Hypothesis scorecard

| Predicted | Observed | Score | Notes |
|---|---|---|---|
| LangFuse/OTEL exporter creates one trace per run | No exporter exists yet; no trace created | wrong | `runs/langfuse-treatment-not-run.txt`. |
| Trace contains child observations for run phases | Not observed | wrong | Blocked by missing exporter and missing LangFuse config. |
| Result report includes a usable LangFuse trace link | Not observed | wrong | Current result has only file exporter reports. |

## Design Impact

- `.6` needs a typed exporter abstraction that can support `file` now and
  `otlp`/`langfuse` next without putting backend logic in harness observers.
- `.9` should begin with config validation and OTLP smoke evidence, then add
  run-event to span mapping.
