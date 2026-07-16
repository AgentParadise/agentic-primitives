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

## Probe C: Current CLI Rerun

Until real LangFuse credentials are available, run the current CLI path with the
deterministic fake Codex harness:

```bash
cargo run --manifest-path providers/workspaces/interactive-tmux/driver-rs/Cargo.toml -- \
  codex-exec \
  --codex-bin experiments/2026-07-07--langfuse--cli-runtime-failfast/fixtures/fake-codex-success.sh \
  --prompt "synthetic current langfuse export" \
  --observability-file experiments/2026-07-07--observability--langfuse-otel-export/runs/current/events.jsonl \
  --observability-langfuse \
  --result-file experiments/2026-07-07--observability--langfuse-otel-export/runs/current/result.json \
  > experiments/2026-07-07--observability--langfuse-otel-export/runs/current/stdout.jsonl \
  2> experiments/2026-07-07--observability--langfuse-otel-export/runs/current/stderr.txt
```

This rerun does not prove LangFuse ingestion. It only keeps this experiment's
current-state evidence aligned with the implemented exporter path.

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
