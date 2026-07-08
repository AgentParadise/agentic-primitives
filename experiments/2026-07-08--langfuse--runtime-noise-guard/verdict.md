# Verdict

Go.

The runtime boundary matches the intended pivot:

- Official Claude/Codex LangFuse plugins remain the canonical rich trace path.
- JSONL and Syntropic137 local fanout remain available alongside official
  plugin tracing.
- Rust OTLP does not send duplicate/noisy fallback traces when
  `TRACE_TO_LANGFUSE=true` is present.
- Rust OTLP is still available when deliberately forced.

The run also re-queried the real local LangFuse backend to keep the distinction
explicit: the real official-plugin traces are queryable with native generation,
tool, usage, and cost data; the local receiver in this experiment is only the
noise-control target for fallback OTLP.

## Hypothesis scorecard

| Predicted | Observed | Score | Notes |
|---|---|---|---|
| With `TRACE_TO_LANGFUSE=true`, `--observability-langfuse` suppresses Rust OTLP at runtime and the receiver sees zero requests. | Receiver request count was `0`. | correct | `runs/suppressed/receiver.json` |
| Suppressed run still writes `--observability-file` and `--observability-syntropic-file`. | Both exporters reported `ok` and wrote `7` events. | correct | `runs/suppressed/result.json`, `runs/suppressed/events.jsonl`, `runs/suppressed/syntropic-events.jsonl` |
| `--observability-langfuse-force` restores exactly one Rust OTLP POST and reports `langfuse_otlp`. | Receiver request count was `1`; result included `langfuse_otlp` `ok` with `7` events. | correct | `runs/forced/receiver.json`, `runs/forced/result.json` |
| Forced OTLP path is redacted normalized-event fallback, not official-plugin rich trace data. | Request was protobuf OTLP with redacted authorization; real rich trace proof remains the official-plugin LangFuse traces queried separately. | correct | `runs/forced/receiver.json`, `runs/real-langfuse-*-summary.json` |

## Decision Impact

- Keep `TRACE_TO_LANGFUSE=true` as the default signal that an official
  Claude/Codex LangFuse plugin is already responsible for rich traces.
- Keep JSONL fanout enabled when useful; it does not imply duplicate LangFuse
  trace writes.
- Use `--observability-syntropic-file` for Syntropic137 hook-style session/tool
  ingestion.
- Use `--observability-langfuse-force` only for deliberate fallback OTLP,
  collector, unsupported harness, or smoke-test scenarios.
