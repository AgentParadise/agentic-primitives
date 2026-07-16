# Official Plugin Tool Rollups

## Question

Can the agentic-primitives LangFuse summary path preserve official LangFuse
plugin tool observations as agent-facing tool rollups for both Claude Code and
Codex traces?

## Hypothesis

1. The current summary path will show zero `agent_tools` for the known official
   Claude Code and Codex traces even though raw LangFuse observations include
   `type: "TOOL"` records.
2. Treating official LangFuse `TOOL` observations as completed agent tools will
   make the Claude trace show `Read` and the Codex trace show `exec_command` in
   `agent_tools.names`.
3. The same change will leave existing agentic-primitives
   `tool_start`/`tool_end` rollups intact because those metadata-shaped events
   still use the existing path.
4. The compact CLI/MCP-facing summary will become useful for learning loops:
   nonzero `agent_tools.end_count`, `success_count`, and tool names will be
   available without re-exporting the trace through the fallback Rust OTLP path.

## Setup

- Repository: `agentic-primitives`
- Branch: `feat/observability-exporter-primitive`
- Local LangFuse: Docker Compose stack from `scripts/langfuse-local.sh`
- Known Claude trace: `0e553fc833c71639acd03be9807eb616`
- Known Codex trace: `b3d2561d7c0557c12fd427c02a16e2f3`
- Prior evidence:
  `experiments/2026-07-08--langfuse--official-plugin-real-session/`

## Conditions

1. Baseline: query both known traces through the current
   `itmux langfuse-trace --output summary` path and store the summaries.
2. Treatment: update the Rust summary code to count official `TOOL`
   observations as completed agent tools, while preserving existing
   metadata-shaped `tool_start`/`tool_end` behavior.
3. Regression: run focused unit tests proving both official `TOOL` and existing
   agentic-primitives tool events are summarized.
4. Re-query: query the same two trace IDs after the patch and compare the
   compact summaries.
5. Hygiene: verify no secrets are introduced and no fallback rich trace export
   is needed for this experiment.
