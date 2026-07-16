# Official Plugin Discovery Report

## Question

Can the discovery-driven LangFuse learning-loop report reliably include and
classify official Claude Code and Codex plugin traces, instead of skipping them
or favoring older fallback OTLP traces?

## Hypothesis

1. Current `itmux langfuse-traces --environment local-macbook` lists the real
   official-plugin traces, but their discovery rows have null
   harness/provider/model fields because those values live in trace names and
   child observations rather than `metadata.agentic.*`.
2. Current MCP `agentic_langfuse_learning_loop_report` omits those official
   plugin traces from its drilled summaries because the discovery row shape is
   incompatible with `_trace_selector_from_row`.
3. Normalizing discovery rows to include stable `trace_id` plus inferred
   harness/provider/model for official-plugin traces will let the report include
   Claude `Read` and Codex `exec_command` traces without relying on fallback
   OTLP metadata.
4. Harness filters (`harness=claude` and `harness=codex`) should select the
   official plugin traces after inference, so learning loops can separate the
   two harnesses.

## Setup

- Repository: `agentic-primitives`
- Branch: `feat/observability-exporter-primitive`
- Local LangFuse: Docker Compose stack at `http://localhost:3000`
- Known official traces:
  - Claude: `0e553fc833c71639acd03be9807eb616`
  - Codex: `b3d2561d7c0557c12fd427c02a16e2f3`

## Conditions

1. Baseline `itmux langfuse-traces --environment local-macbook --limit 20`.
2. Baseline MCP `agentic_langfuse_learning_loop_report` for
   `environment=local-macbook`.
3. Patch discovery row normalization and MCP selector/filter handling if
   baseline confirms omission or missing classification.
4. Treatment `itmux langfuse-traces` and MCP report against the same backend.
5. Focused tests and secret scan.

## Expected Signals

- Baseline trace list includes the two official trace IDs but lacks complete
  harness/provider/model classification.
- Baseline MCP report either omits those trace IDs or records errors for them.
- Treatment report includes both official trace IDs with tool rollups:
  `Read` for Claude and `exec_command` for Codex.
- Treatment `harness=claude` and `harness=codex` filters each select the
  matching official trace.
