# Runtime Noise Guard

## Question

Does the `itmux` runtime boundary enforce the intended exporter ownership
policy: official Claude/Codex LangFuse plugins remain canonical for rich traces,
JSONL fanout remains available, and the Rust OTLP fallback does not send noisy
duplicate LangFuse traces unless explicitly forced?

## Hypothesis

1. With `TRACE_TO_LANGFUSE=true`, `itmux claude-transcript
   --observability-langfuse` will suppress the Rust `langfuse_otlp` exporter
   at runtime, so a local OTLP receiver will receive zero HTTP requests.
2. In the same suppressed run, `--observability-file` and
   `--observability-syntropic-file` will still write local JSONL artifacts and
   report `ok` exporters in the final result.
3. Adding `--observability-langfuse-force` will restore exactly one Rust OTLP
   POST to the local receiver and report a `langfuse_otlp` exporter alongside
   local JSONL exporters.
4. The forced OTLP path will use redacted normalized events, not official
   plugin rich trace data, reinforcing that it is a fallback/collector path
   rather than the canonical Claude/Codex rich trace path.

## Setup

- Repository: `agentic-primitives`
- Branch: `feat/observability-exporter-primitive`
- Command under test: `itmux claude-transcript`
- Input transcript fixture:
  `providers/workspaces/claude-cli/fixtures/recordings/v2.0.74_claude-sonnet-4-5_file-read.jsonl`
- Receiver: local one-shot HTTP listener started by the run script

## Conditions

1. Baseline/suppressed run:
   - Set `TRACE_TO_LANGFUSE=true`.
   - Set `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and
     `LANGFUSE_TRACING_ENVIRONMENT` to local probe values.
   - Run `itmux claude-transcript` with `--observability-file`,
     `--observability-syntropic-file`, `--observability-langfuse`, and a local
     receiver base URL, but without `--observability-langfuse-force`.
   - Expected: no receiver request; file and Syntropic JSONL exist.
2. Forced run:
   - Same env and command, with `--observability-langfuse-force`.
   - Expected: one receiver request; file, Syntropic JSONL, and LangFuse
     exporter reports exist.
3. Hygiene:
   - Scan artifacts for unredacted LangFuse key values.
   - Run focused Rust exporter tests to keep the unit-level guard green.

## Expected Signals

- `runs/suppressed/result.json` has no `langfuse_otlp` exporter.
- `runs/suppressed/receiver.json` records zero requests.
- `runs/suppressed/events.jsonl` and `runs/suppressed/syntropic-events.jsonl`
  are non-empty.
- `runs/forced/result.json` includes a successful `langfuse_otlp` exporter.
- `runs/forced/receiver.json` records one request.
- The captured OTLP request contains authorization headers but committed
  artifacts redact key values.
