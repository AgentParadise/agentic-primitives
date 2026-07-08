# Current Rust OTLP Trace Contract

Source:
`providers/workspaces/interactive-tmux/driver-rs/src/run/observability.rs`

## Evidence

- `encode_otlp_trace_request` creates one root span named
  `agentic_primitives.run`.
- Root attributes include `session.id`, `langfuse.session.id`,
  `langfuse.trace.name`, `langfuse.trace.metadata.run_id`,
  `langfuse.trace.metadata.observer`, and tags.
- Root attributes do not include `langfuse.trace.input`,
  `langfuse.trace.output`, `langfuse.observation.input`, or
  `langfuse.observation.output`.
- Child spans are created with `name: event.payload.type_name()`.
- `type_name()` maps event payloads to generic names such as `tool_start`,
  `tool_end`, `token_usage`, `hook_event`, `session_end`, and `result`.
- `encode_span` hardcodes end time as start time plus 1 ms for every span.
- Tool starts and ends are separate child spans. The exporter does not pair
  `ToolStart` and `ToolEnd` into one LangFuse tool observation.
- Tool data is emitted as `agentic.tool.name`,
  `agentic.tool.input_redacted`, `agentic.tool.input_summary`,
  `agentic.tool.success`, and optional `agentic.tool.output_summary`.
- Token usage emits useful `gen_ai.usage.*`, `llm.usage.*`, and
  `agentic.usage.*` attributes, but the span remains a generic `token_usage`
  event rather than a LangFuse `generation` observation with input/output.

## Runtime Query

Skipped in this run because the shell does not currently have
`LANGFUSE_BASE_URL`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`,
`LANGFUSE_PROJECT_ID`, or `LANGFUSE_TRACING_ENVIRONMENT` loaded.

Known prior UI evidence from local LangFuse trace
`37f5920448612df0be0a2228a671a055` / `run-88868068` matches the source
contract: generic `tool_start`/`tool_end`/`token_usage` observations and empty
preview input/output despite useful metadata and cost fields.

## Scoring Against Probe C

- Root trace input/output populated: fail.
- Semantic child observation names: fail for tool/event spans.
- Paired tool observation durations: fail.
- Usage/cost available: partial, as attributes on `token_usage`.
- Generation observation with input/output/model/usage: fail.

