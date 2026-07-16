# Results

## Headline

| Probe | Result | Evidence |
| --- | --- | --- |
| Official Claude plugin trace contract | Pass | `runs/official-claude-trace-contract.md`, `runs/official-claude-tests.txt` |
| Official Codex plugin trace contract | Pass by source; runtime test inconclusive | `runs/official-codex-trace-contract.md`, `runs/official-codex-tests.txt` |
| Current Rust OTLP trace contract | Confirms noisy/low-level LangFuse mapping | `runs/current-rust-otlp-contract.md` |
| Pivot and noise-control decision | Go | `runs/pivot-decision.md` |

## Probe A: Official Claude Plugin Trace Contract

The official Claude plugin passes the contract check.

Evidence:

- The plugin registers `Stop` and `SessionEnd` hooks.
- It reads Claude transcript JSONL incrementally with state/offset handling.
- It creates a root `Conversational Turn` span with user input and assistant
  output.
- It creates `generation` observations with model, input, output, metadata, and
  usage when present.
- It creates `tool` observations named from actual tool names, with tool
  input/output and backdated timings.
- `uv run pytest` passed 48/48 tests.

## Probe B: Official Codex Plugin Trace Contract

The official Codex plugin passes the source-level contract check.

Evidence:

- It registers a Codex `Stop` hook.
- It reads Codex rollout transcript JSONL.
- It reconstructs turns, model steps, tool calls, subagents, usage, and final
  output.
- It emits `Codex Turn` as an `agent` observation with root input/output.
- It emits `generation` observations with model and `usageDetails`.
- It emits `tool` observations with actual tool names, input/output,
  error/status, and timings.
- It records uploaded completed turn ids in a sidecar file to avoid duplicate
  uploads.

Runtime test note:

- `pnpm test` was attempted after installing locked dependencies, but the local
  `/tmp` shell used Node 20.12/pnpm 9.1.4 while the plugin requires Node >=22
  and pnpm 9.5. Vitest then failed on a missing Rolldown native binding. This
  leaves local runtime test execution inconclusive, but does not contradict the
  source-level trace-contract evidence.

## Probe C: Current Rust OTLP Trace Contract

The current Rust OTLP exporter is useful but too low-level to be the default
rich LangFuse path.

Evidence:

- Root span is `agentic_primitives.run`.
- Child spans are named by normalized event type (`tool_start`, `tool_end`,
  `token_usage`, etc.).
- Root input/output is not populated.
- Observation input/output is not populated for the event spans.
- Tool start/end are separate 1 ms child spans instead of one tool observation
  with real duration.
- Usage/cost metadata is available, but attached to a generic `token_usage`
  span rather than a generation observation with model input/output.

This matches the operator-observed LangFuse UI problem: metadata and cost can
exist while the trace remains weak for human and agent learning loops.

## Probe D: Pivot And Noise-Control Decision

Verdict: go.

The architecture should pivot as follows:

- Official LangFuse Claude and Codex plugins are canonical for rich LangFuse
  trace UX.
- JSONL fanout remains a durable local/source-of-truth artifact for replay,
  debugging, Docker/VPS portability, and Syntropic137 consumption.
- Rust OTLP remains useful as fallback, smoke-test path, and generic
  collector/Syntropic137 bridge.
- Rust OTLP should not be enabled by default alongside official Claude/Codex
  LangFuse plugins because it creates duplicate/noisy low-level observations.
- Direct Rust OTLP-to-LangFuse for unsupported harnesses is allowed only as an
  explicit fallback and should be upgraded before being marketed as rich
  LangFuse support.

## Next Required Probe

Before closing `.9`, run an end-to-end official-plugin validation against the
local self-hosted LangFuse stack:

1. Configure official Claude plugin against local LangFuse.
2. Configure official Codex plugin against local LangFuse.
3. Run one minimal tool-using Claude turn and one minimal tool-using Codex turn.
4. Capture UI/API evidence for root input/output, generation observations,
   tool observations, usage/cost, environment/session filtering, and MCP/CLI
   queryability.
5. Verify Rust OTLP is not also sending duplicate rich traces by default.
