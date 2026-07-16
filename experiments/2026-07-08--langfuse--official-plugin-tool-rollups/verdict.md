# Verdict

Go.

The patch closes the concrete learning-loop gap observed in the LangFuse UI:
official Claude Code and Codex plugin traces already contained useful tool
observations, but the CLI/MCP-facing compact summary categorized them as
`other` and omitted them from `agent_tools`. After the change, the same two
real trace IDs expose completed agent tool rollups for Claude `Read` and Codex
`exec_command`.

This does not claim that the dashboard is now perfect for every agent workflow.
It specifically proves the CLI and MCP trace-summary read paths now preserve
the official plugin tool observations that were already present in LangFuse.

## Hypothesis scorecard

| Predicted | Observed | Score | Notes |
|---|---|---|---|
| Current summary shows zero `agent_tools` for official Claude/Codex traces despite raw `TOOL` records | Confirmed: both baselines had empty `agent_tools.names`; raw samples had one `TOOL` each | correct | `runs/baseline-treatment-agent-tools-comparison.json`, `runs/raw-*-tool-observations.json` |
| Counting official `TOOL` observations as completed agent tools makes Claude show `Read` and Codex show `exec_command` | Confirmed | correct | `runs/treatment-claude-summary.json`, `runs/treatment-codex-summary.json` |
| Existing `tool_start`/`tool_end` behavior remains intact | Confirmed by focused existing summary test | correct | `runs/test-langfuse-summary-rerun.txt` |
| Compact CLI/MCP-facing summary becomes useful without fallback rich export | Confirmed for direct trace summaries through both CLI and MCP; broader discovery-driven learning reports still need a follow-up pass | partial | `runs/treatment-claude-summary.json`, `runs/treatment-codex-summary.json`, `runs/mcp-trace-summary.json`, `runs/fallback-export-runs-scan-rerun.txt` |

## Follow-Up

- Query the discovery-driven `agentic_langfuse_learning_loop_report` path after
  adding reliable official-plugin harness filters; direct MCP trace summaries
  are now proven.
- Add a separate experiment for richer official-plugin payload extraction if
  we want inputs/outputs summarized without forcing users into the LangFuse UI.
