# Results

## Headline

| Probe | Baseline | Treatment | Evidence |
|---|---:|---:|---|
| Claude `agent_tools.names` | `[]` | `["Read"]` | `runs/baseline-treatment-agent-tools-comparison.json` |
| Claude `agent_tools.end_count` | `0` | `1` | `runs/baseline-treatment-agent-tools-comparison.json` |
| Codex `agent_tools.names` | `[]` | `["exec_command"]` | `runs/baseline-treatment-agent-tools-comparison.json` |
| Codex `agent_tools.end_count` | `0` | `1` | `runs/baseline-treatment-agent-tools-comparison.json` |
| MCP trace-summary Claude tool rollup | not run | `["Read"]` | `runs/mcp-trace-summary.json` |
| MCP trace-summary Codex tool rollup | not run | `["exec_command"]` | `runs/mcp-trace-summary.json` |
| Official raw `TOOL` observations | Claude `1`, Codex `1` | unchanged | `runs/raw-claude-tool-observations.json`, `runs/raw-codex-tool-observations.json` |

## Baseline

The known real official-plugin traces were queryable, but the old compact
summary dropped official tools from agent-facing rollups:

- Claude trace `0e553fc833c71639acd03be9807eb616` had
  `observation_types: ["GENERATION", "SPAN", "TOOL"]`, but
  `summary.agent_tools.names: []`.
  Evidence: `runs/baseline-claude-summary.json`.
- Codex trace `b3d2561d7c0557c12fd427c02a16e2f3` had
  `observation_types: ["AGENT", "GENERATION", "TOOL"]`, but
  `summary.agent_tools.names: []`.
  Evidence: `runs/baseline-codex-summary.json`.

Raw observation samples confirmed the missing data was present before the code
change:

- Claude: one `TOOL` observation named `Tool: Read`.
  Evidence: `runs/raw-claude-tool-observations.json`.
- Codex: one `TOOL` observation named `exec_command`.
  Evidence: `runs/raw-codex-tool-observations.json`.

## Treatment

The Rust summarizer now treats official LangFuse `TOOL` observations as
completed agent tools unless explicit `agentic.event.type` metadata is already
present. Tool names prefer `agentic.tool.name`, then strip `Tool: ` from the
observation name, then fall back to the raw observation name.

Treatment summaries for the same trace IDs now show:

- Claude `agent_tools.names: ["Read"]`, `end_count: 1`,
  `success_count: 1`.
  Evidence: `runs/treatment-claude-summary.json`.
- Codex `agent_tools.names: ["exec_command"]`, `end_count: 1`,
  `success_count: 1`.
  Evidence: `runs/treatment-codex-summary.json`.

## Verification

- `cargo test --manifest-path providers/workspaces/interactive-tmux/driver-rs/Cargo.toml langfuse_trace_summary -- --nocapture`
  passed. Evidence: `runs/test-langfuse-summary-rerun.txt`.
- `cargo test --manifest-path providers/workspaces/interactive-tmux/driver-rs/Cargo.toml cli_exporters -- --nocapture`
  passed. Evidence: `runs/test-cli-exporters.txt`.
- `cargo fmt --manifest-path providers/workspaces/interactive-tmux/driver-rs/Cargo.toml -- --check`
  passed after rustfmt. Evidence: `runs/test-cargo-fmt-rerun.txt`.
- MCP stdio calls to `agentic_langfuse_trace_summary` passed for the same
  Claude and Codex trace IDs, returning the improved `agent_tools` summaries.
  Evidence: `runs/mcp-trace-summary.json`.
- Unredacted LangFuse key scan found no matches. Evidence:
  `runs/secret-scan-final.txt` and `runs/secret-scan-final-exit.txt`.
- Run artifacts contain no fallback `--observability-langfuse` invocation.
  Evidence: `runs/fallback-export-runs-scan-rerun.txt` and
  `runs/fallback-export-runs-scan-rerun-exit.txt`.

Cargo still prints non-fatal diagnostics from the APSS git dependency's
template `Cargo.toml` files containing `{{slug}}`; the crate build/tests
complete successfully. Evidence: `runs/test-langfuse-summary-rerun.txt`.
