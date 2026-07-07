# Verdict

**Go for real LangFuse ingestion smoke; no-go for claiming backend visibility
yet.**

The actual exporter path now buffers normalized `AgentRunEvent`s and sends an
OTLP HTTP/protobuf request to a mock receiver on `finish()`. A 2xx mock response
is reflected as an `ok` exporter report. The remaining question is no longer
local transport shape; it is LangFuse backend acceptance and trace
discoverability.

## Hypothesis Scorecard

| Predicted | Observed | Score | Notes |
|---|---|---|---|
| One POST is sent on finish | Mock receiver test passed | correct | `runs/mock-transport.txt` |
| Headers match LangFuse OTLP expectations | Test asserted protobuf content type, Basic auth, ingestion-version header | correct | `runs/mock-transport.txt` |
| Body is non-empty protobuf-shaped data | Test asserted non-empty body containing `agentic_primitives.run` | correct | `runs/mock-transport.txt` |
| 2xx mock response reports exporter OK | Test asserted `status = ok`, event count 1, no error | correct | `runs/mock-transport.txt` |

## Design Impact

- `.9` now has local transport implementation, not just config validation.
- The next required experiment is the real
  `experiments/2026-07-07--langfuse--otel-ingestion-smoke` against LangFuse
  Cloud or the Mac Mini self-host.
- If real LangFuse rejects the payload, the architecture decision should narrow
  to either fixing the local OTLP protobuf encoder or switching this exporter
  slice to the official OpenTelemetry SDK/exporter crates.
