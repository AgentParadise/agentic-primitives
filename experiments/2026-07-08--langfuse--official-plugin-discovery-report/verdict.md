# Verdict

## Decision

go

The official LangFuse Claude Code and Codex traces are usable for learning-loop
reports after fixing discovery classification and MCP trace selection. The
report now pulls the real local backend traces by `trace_id`, resolves models,
tokens, cost, and agent tool names, and supports `harness=claude` /
`harness=codex` filtering.

This does not mean the raw LangFuse UI is already ideal for agent review. The
useful agent-shaped view is the CLI/MCP summary layer over official LangFuse
observations.

## Evidence

- Baseline omission/error: `runs/baseline-mcp-report.json`.
- Treatment all-harness report: `runs/treatment-mcp-report.json`.
- Treatment Codex report: `runs/treatment-mcp-report-codex.json`.
- Treatment Claude report: `runs/treatment-mcp-report-claude.json`.
- Discovery filtering: `runs/treatment-traces-codex.json`,
  `runs/treatment-traces-claude.json`.
- Tests and hygiene: `runs/test-langfuse-traces-summary.txt`,
  `runs/test-langfuse-trace-summary.txt`, `runs/test-mcp-self-test.txt`,
  `runs/diff-check.txt`, `runs/secret-scan.txt`.

## Hypothesis scorecard

| Prediction | Observed | Score | Notes |
|---|---|---:|---|
| Current discovery lists real official traces but misses useful official-plugin classification | Official traces were listed; classification was incomplete for learning-loop use | partial | Earlier row classification existed for harness/provider, but model remained unavailable on list rows. |
| Current MCP report omits official traces due to selector incompatibility | Confirmed | correct | Baseline report used `sessionId` as `run_id`, derived wrong trace IDs, and hit 404s. |
| Normalizing rows and selectors lets the report include Claude `Read` and Codex `exec_command` | Confirmed | correct | Treatment report includes both official trace IDs, tools, cost, tokens, and models. |
| Harness filters select official plugin traces | Confirmed | correct | Codex and Claude filtered discovery/MCP reports select the expected official trace first. |

## Follow-up

- Keep model resolution in trace drill-down unless LangFuse exposes generation
  model names on the list endpoint.
- Improve the UI/dashboard story separately; the backend evidence is now strong,
  but the raw trace tree is still too low-level for quick agent review.
