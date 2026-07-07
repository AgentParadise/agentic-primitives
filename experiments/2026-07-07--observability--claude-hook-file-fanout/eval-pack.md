# Eval Pack

## Probe A: Baseline File Fanout

Run a minimal Claude recipe through `itmux run` with only
`--observability-file runs/baseline-events.jsonl` and
`--result-file runs/baseline-result.json`.

Record:

- stdout JSONL as `runs/baseline-stdout.jsonl`
- exporter file as `runs/baseline-events.jsonl`
- result file as `runs/baseline-result.json`

## Probe B: Claude Plugin Hook Fanout

Run the same recipe with the observability plugin loaded through the supported
Claude plugin-dir mechanism and the same file exporter settings.

Record:

- stdout JSONL as `runs/treatment-stdout.jsonl`
- exporter file as `runs/treatment-events.jsonl`
- result file as `runs/treatment-result.json`

## Scoring

For each probe, count:

- total stdout events
- total exported file events
- session lifecycle events
- tool lifecycle events
- exporter report status
- exporter report event count

The treatment passes if the plugin-loaded run produces observable hook-derived
lifecycle/tool data and the exporter report matches the artifact.
