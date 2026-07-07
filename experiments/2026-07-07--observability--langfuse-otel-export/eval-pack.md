# Eval Pack

## Probe A: Local Baseline

Run `itmux run` with the file exporter enabled and capture:

- `runs/baseline-stdout.jsonl`
- `runs/baseline-events.jsonl`
- `runs/baseline-result.json`

## Probe B: LangFuse Export

Run the same task with file exporter and LangFuse/OTEL exporter enabled.

Capture:

- `runs/langfuse-stdout.jsonl`
- `runs/langfuse-events.jsonl`
- `runs/langfuse-result.json`
- `runs/langfuse-trace-summary.json` fetched from the LangFuse API or exported
  manually from the UI
- screenshot or textual evidence of the trace, if API query support is not yet wired

## Scoring

Pass requires:

- local run still succeeds
- file exporter still succeeds
- LangFuse exporter reports success
- result contains a trace link
- trace contains at least three run phase observations

Failure modes to classify:

- credential/config failure
- OTEL mapping failure
- trace exists but is not useful
- trace link cannot be reconstructed
