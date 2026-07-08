# Verdict

## inconclusive

This probe did not test the hypothesis. The baseline succeeded, but the
treatment command in the frozen eval pack was invalid for the installed Codex
exec surface.

## Hypothesis scorecard

| Prediction | Observed | Score | Notes |
|---|---|---|---|
| A fresh `codex exec --json` run with `TRACE_TO_LANGFUSE=true` will create a new trace. | Not tested. `codex exec` rejected `--ask-for-approval`. | inconclusive | The model turn did not start. |
| The trace will be discoverable through `itmux langfuse-traces`. | Not tested for a new trace. Baseline discovery worked for existing traces. | inconclusive | No new trace candidate was created. |
| The trace summary will report generation/tool/cost data. | Not tested. | inconclusive | No new trace candidate was created. |
| The run will not use the Rust OTLP fallback exporter. | The command artifact did not include fallback export flags. | partial | Hygiene signal is valid, but no successful run occurred. |
| Artifacts will not contain raw LangFuse keys. | Pending final hygiene scan in the follow-up. | inconclusive | This probe stops at the invalid command finding. |

## Follow-up

Run a corrected follow-up experiment that removes `--ask-for-approval` from the
`codex exec` invocation and keeps the same official-plugin/no-fallback question.
