---
title: "ADR-039: Official LangFuse Plugins Are Canonical for Agent Traces"
status: proposed
created: 2026-07-08
updated: 2026-07-08
author: Neural
supersedes: ADR-038 partial
tags: [architecture, observability, langfuse, claude, codex]
---

# ADR-039: Official LangFuse Plugins Are Canonical for Agent Traces

## Status

**Proposed**

- Created: 2026-07-08
- Updated: 2026-07-08
- Author(s): Neural
- Partially supersedes: ADR-038's Rust OTLP-to-LangFuse fallback decision
- Related OKRs: `okrs-51p.6`, `okrs-51p.9`

## Context

ADR-038 chose a modular observability architecture with normalized local
events, exporter fanout, LangFuse support, and Syntropic137 compatibility. That
decision was directionally correct, but later experiments showed that one part
of the design caused product confusion: exporting normalized `itmux` events
directly to LangFuse through the Rust OTLP writer produced valid but weak
LangFuse traces.

The Rust OTLP traces had generic `agentic_primitives.run`, `tool_start`,
`tool_end`, `token_usage`, and `session_end` observations. They were useful as
transport smoke tests, but they did not provide the user-facing trace UX we
want for learning loops: clear turns, model calls, native tool observations,
root input/output, costs, and harness session grouping.

The official LangFuse Claude Code and Codex plugins behaved differently. They
read the harness-native transcript/rollout and emit LangFuse-native traces:

- Claude Code traces contain a Claude turn, generation observations, tool
  observations such as `Tool: Read`, usage, costs, and session grouping.
- Codex traces contain a `Codex Turn`, generation observations, tool
  observations such as `exec_command`, usage, costs, and session grouping.

The evidence also showed that the SDK language shown in LangFuse identifies
the plugin implementation path:

- Official Codex plugin traces report `telemetry.sdk.language = nodejs` and
  `langfuse-sdk`.
- Official Claude plugin traces report `telemetry.sdk.language = python` and
  `langfuse-sdk`.

That is expected and accurate. It means the Claude plugin is exporting through
the Python LangFuse/OpenTelemetry SDK path, while the Codex plugin is exporting
through the Node.js LangFuse/OpenTelemetry SDK path.

We still need normalized local event fanout. Local JSONL is useful for
debugging, test evidence, replay, and Syntropic137. Syntropic137 still needs a
HookWatcher-compatible JSONL projection. Those are separate from rich LangFuse
trace ownership.

## Experiment Evidence

The detailed experiment folders remain the audit trail. This ADR distills the
decision-driving results:

| Evidence | Result | Decision Impact |
|---|---|---|
| Rust OTLP writer to local LangFuse | Accepted by backend, but produced generic `agentic_primitives.run`, `tool_start`, `tool_end`, and `token_usage` observations with weak input/output and tool semantics | Remove from rich-trace path; keep only historical evidence |
| Official Claude plugin real run | Trace `0e553fc833c71639acd03be9807eb616` showed native Claude generation/tool shape, usage/cost, and `telemetry.sdk.language=python` | Use official Claude plugin as canonical Claude producer |
| Official Codex plugin real run | Trace `b3d2561d7c0557c12fd427c02a16e2f3` showed native Codex turn/tool shape, usage/cost, and `telemetry.sdk.language=nodejs` | Use official Codex plugin as canonical Codex producer |
| Fresh direct Codex plugin invocation | Trace `b928a86e0c44784896a2224778c339c4` confirmed rich trace upload against the local LangFuse backend | Treat remaining Codex work as hook/config readiness, not exporter design |
| JSONL/Syntropic fanout experiments | Local `AgentRunEvent` JSONL and Syntropic137 HookWatcher-style JSONL both worked independently of LangFuse | Keep backend-independent evidence and Syntropic bridge |

The Claude run evidence confirms that seeing
`telemetry.sdk.language=python` on Claude traces is accurate. It identifies the
SDK implementation used by LangFuse's official plugin, not the language of the
Claude harness itself.

## Decision

We will make official LangFuse plugins the only canonical rich trace path for
Claude Code and Codex.

We will remove Rust OTLP-to-LangFuse from the user-facing `itmux` exporter
surface. In practice:

- Do not present `--observability-langfuse` as a supported way to get rich
  Claude/Codex traces.
- Remove or deprecate the `langfuse_otlp` exporter from public run specs,
  generated schema, CLI flags, setup guide, and smoke scripts.
- Keep `itmux langfuse-trace`, `itmux langfuse-traces`,
  `itmux langfuse-score`, and the `agentic-langfuse` MCP read/write tools.
  Those are query/learning-loop tools, not exporters.
- Keep `--observability-file` as the canonical local `AgentRunEvent` JSONL
  artifact.
- Keep `--observability-syntropic-file` as the Syntropic137-compatible JSONL
  projection.
- Package setup around official plugins plus secret-safe environment/config
  injection for MacBooks, Mac Mini/VPS hosts, and isolated Docker workspaces.

For unsupported future harnesses, we will not revive the Rust OTLP writer by
default. The preferred approach is to write a harness-native LangFuse adapter
or plugin that exports native turns/generations/tools, then keep local JSONL as
the durable side channel.

## Alternatives Considered

### Alternative 1: Keep Rust OTLP as an Explicit Fallback

**Description**: Keep `langfuse_otlp`, but require a force flag or explicit
fallback mode.

**Pros**:

- Existing transport code and tests continue to pass.
- Provides a generic OpenTelemetry path for any future collector.
- Useful as a backend smoke test.

**Cons**:

- Still creates low-quality LangFuse traces when used.
- Users naturally open the noisy trace and assume LangFuse is not working.
- Requires ongoing docs, tests, flags, and support for a path we no longer want
  for Claude/Codex.

**Reason for rejection**: The fallback path consumed attention and confused the
product evaluation. The official plugins already solve the rich trace problem
better.

### Alternative 2: Keep Both and Improve Rust OTLP Semantics

**Description**: Continue exporting from Rust, but map normalized events into
more LangFuse-native trace shapes.

**Pros**:

- One exporter could work across many harnesses.
- Keeps tracing inside the `itmux` run lifecycle.

**Cons**:

- Reconstructing native turns/generations/tools from normalized events repeats
  work the official plugins already do from better source data.
- The Rust path lacks harness-specific transcript semantics, especially for
  Claude and interactive Codex.
- More code, more tests, and more divergence from maintained LangFuse plugins.

**Reason for rejection**: For Claude/Codex, source-native plugins have better
data and lower maintenance cost.

### Alternative 3: Use Only Local JSONL and No LangFuse Plugins

**Description**: Keep local JSONL/Syntropic JSONL only and query those files for
learning loops.

**Pros**:

- Simple local implementation.
- No external backend required.
- Works in isolated workspaces.

**Cons**:

- Loses LangFuse dashboards, sessions, scores, cost views, and API query tools.
- Does not satisfy the `.9` backend requirement.
- Makes cross-machine learning loops harder.

**Reason for rejection**: LangFuse is the chosen primary observability backend.
JSONL is a durable side channel, not the primary trace UX.

## Consequences

### Positive Consequences

- LangFuse dashboard traces become easier to interpret because only rich
  official-plugin traces are expected for Claude/Codex.
- Setup instructions become clearer: install official plugin, inject
  credentials, verify with doctor, then query traces.
- Syntropic137 support stays cleanly separated through JSONL projection.
- The codebase can delete a large custom OTLP/protobuf exporter surface.

### Negative Consequences

- We lose a generic Rust OTLP smoke path unless it is replaced by a smaller
  backend health check or direct LangFuse API check.
- Unsupported future harnesses need their own adapter/plugin rather than using
  the Rust exporter as a default.
- Existing experiments and docs that reference `langfuse_otlp` become
  historical evidence, not current implementation guidance.

### Neutral Consequences

- `itmux langfuse-*` query and score commands remain important because they are
  how agents consume LangFuse for learning loops.
- `TRACE_TO_LANGFUSE=true` remains the official plugin opt-in signal.
- Claude and Codex may show different SDK languages in LangFuse because their
  official plugins are implemented with different SDK runtimes.

## Implementation Notes

- Remove `ObservabilityExporter::LangFuseOtlp` and the `langfuse_otlp` schema
  variant.
- Remove `--observability-langfuse`, `--observability-langfuse-force`,
  `--langfuse-project-id`, and `--langfuse-label` from `itmux run`,
  `itmux codex-exec`, and `itmux claude-transcript`.
- Keep `--observability-file` and `--observability-syntropic-file`.
- Remove Rust OTLP sink code from `ObservabilityFanout`; keep file and
  Syntropic JSONL sinks.
- Keep shared LangFuse query helpers that are used by `itmux langfuse-trace`,
  `itmux langfuse-traces`, score commands, and MCP tools.
- Replace `scripts/langfuse-local.sh smoke` with an official-plugin-oriented
  check or rename the old smoke as historical/deprecated.
- Update `scripts/langfuse-observability-doctor.sh` so it checks official
  plugin readiness, JSONL/Syntropic support, and MCP/query support, not Rust
  OTLP noise guards.
- Update `docs/guides/langfuse-observability-setup.md` to make official plugin
  setup the packaged path for MacBook, Mac Mini/VPS, and Docker workspaces.
- Mark OTLP experiments as historical in the audit docs; they explain why the
  path was removed but are not current acceptance gates.

## References

- ADR-038: Modular Agent Observability
- `docs/guides/langfuse-observability-setup.md`
- `docs/plans/2026-07-07-observability-primitive-completion-audit.md`
- `experiments/2026-07-08--langfuse--official-plugin-e2e-local`
- `experiments/2026-07-08--langfuse--official-plugin-real-session`
- `experiments/2026-07-08--langfuse--official-plugin-tool-rollups`
- `experiments/2026-07-08--langfuse--official-plugin-discovery-report`
- `experiments/2026-07-08--langfuse--runtime-noise-guard`
- `experiments/2026-07-08--langfuse--codex-plugin-hooks-remediation`
- `experiments/2026-07-08--langfuse--codex-official-hooks-fresh-run-corrected`
- `experiments/2026-07-08--syntropic137--jsonl-fanout-compat`
