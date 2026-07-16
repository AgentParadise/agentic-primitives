# Results

## Headline

| Probe | Result | Evidence |
|---|---:|---|
| Baseline discovery included official traces but had weak row classification | confirmed | `runs/baseline-traces.json` |
| Baseline MCP report skipped the official traces via wrong selector | confirmed | `runs/baseline-mcp-report.json` |
| Treatment discovery classifies official Codex/Claude rows | pass | `runs/treatment-traces.json` |
| Treatment harness filters select official traces | pass | `runs/treatment-traces-codex.json`, `runs/treatment-traces-claude.json` |
| Treatment MCP report drills official traces into learning-loop data | pass | `runs/treatment-mcp-report.json` |
| Focused tests and hygiene | pass | `runs/test-langfuse-traces-summary.txt`, `runs/test-langfuse-trace-summary.txt`, `runs/test-mcp-self-test.txt`, `runs/diff-check.txt`, `runs/secret-scan.txt` |

## Baseline

`runs/baseline-traces.json` showed the two real official plugin traces at the
top of the local LangFuse list:

- Codex `b3d2561d7c0557c12fd427c02a16e2f3`, `name="Codex Turn"`,
  `total_cost=0.174825`, `observation_count=4`.
- Claude `0e553fc833c71639acd03be9807eb616`,
  `name="Claude Code - Turn 1 (dfec301e)"`, `total_cost=0.1139603`,
  `observation_count=4`.

Baseline rows already had some classification from an earlier code path, but
the MCP report still failed to use those rows correctly. In
`runs/baseline-mcp-report.json`, the report tried selectors based on
`run_id`/`sessionId` and produced 404s for both official traces. It then
summarized older fallback traces instead of the official plugin traces.

## Treatment Discovery

`runs/treatment-traces.json` returned 20 local traces and classified the top
official rows:

- Codex `b3d2561d7c0557c12fd427c02a16e2f3`:
  `harness=codex`, `provider=openai`, `total_cost=0.174825`,
  `observation_count=4`.
- Claude `0e553fc833c71639acd03be9807eb616`:
  `harness=claude`, `provider=anthropic`, `total_cost=0.1139603`,
  `observation_count=4`.

Harness filtering selected the expected official rows:

- `runs/treatment-traces-codex.json`: first row is `Codex Turn`
  `b3d2561d7c0557c12fd427c02a16e2f3`.
- `runs/treatment-traces-claude.json`: first row is
  `Claude Code - Turn 1 (dfec301e)` `0e553fc833c71639acd03be9807eb616`.

The discovery list rows still have `model=null` for official plugin traces
because the trace list endpoint does not include child generation observations.
Model names are resolved during trace drill-down.

## Treatment MCP Report

`runs/treatment-mcp-report.json` queried the top two official traces by
`trace_id` and returned no errors:

- `trace_count=2`
- `harnesses=["claude","codex"]`
- `providers=["anthropic","openai"]`
- `models=["claude-sonnet-5","gpt-5.5"]`
- `usage.total_tokens=132249`
- `cost.calculated_total_usd=0.2887853`
- `agent_tools.success_count=2`, `failure_count=0`

Per trace:

- Codex `b3d2561d7c0557c12fd427c02a16e2f3`: model `gpt-5.5`,
  `34445` tokens, `$0.174825`, agent tool `exec_command`.
- Claude `0e553fc833c71639acd03be9807eb616`: model `claude-sonnet-5`,
  `97804` tokens, `$0.1139603`, agent tool `Read`.

Filtered MCP reports also passed:

- `runs/treatment-mcp-report-codex.json`: one Codex trace, model `gpt-5.5`,
  tool `exec_command`, no errors.
- `runs/treatment-mcp-report-claude.json`: one Claude trace, model
  `claude-sonnet-5`, tool `Read`, no errors.

## Tests

- `cargo test ... langfuse_traces_summary`: exit `0`.
- `cargo test ... langfuse_trace_summary`: exit `0`.
- `python3 plugins/observability/mcp/langfuse_server.py --self-test`: exit `0`.
- `git diff --check`: exit `0`.
- Secret pattern scan over changed source and experiment artifacts: no matches
  (`rg` exit `1`, empty output).
