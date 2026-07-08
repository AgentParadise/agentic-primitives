# Results

## Headline

| Probe | Evidence | Result |
|---|---|---|
| Preflight | `runs/preflight.md` | Passed: local LangFuse stack was up; Claude 2.1.204, Codex 0.142.5, Node 22.17.1, `uv`, and Python were present. |
| Claude marketplace install | `runs/claude-session/install.md` | Passed with caveat: marketplace add and local plugin install succeeded; `claude plugin list` showed `langfuse-observability@langfuse-observability` enabled in local scope. Install-time `--config` reported userConfig still unset, so the successful run used the official hook's env fallback. |
| Claude real session | `runs/claude-session/claude-output.json`, `runs/claude-session/hook-log-tail.txt`, `runs/claude-session/trace-compact.json`, `runs/claude-session/trace-observation-sample.json` | Passed: real `claude -p` session emitted trace `0e553fc833c71639acd03be9807eb616`, session `dfec301e-8152-4566-9253-cc211739b80b`, with root IO, `Tool: Read`, 2 generations, usage/cost, and `local-macbook` environment. |
| Codex marketplace install | `runs/codex-session/install.md` | Passed: marketplace `codex-observability-plugin` added and `tracing@codex-observability-plugin` installed/enabled. |
| Codex real session | `runs/codex-session/codex-output.jsonl`, `runs/codex-session/trace-compact.json`, `runs/codex-session/trace-observation-sample.json` | Passed: real `codex exec` session emitted trace `b3d2561d7c0557c12fd427c02a16e2f3`, session `019f4324-c997-72c1-bae9-9eae62d84fc8`, with root IO, `exec_command` tool, 2 generations, usage/cost, and `local-macbook` environment. |
| Noise audit | `runs/noise-audit.txt`, `runs/noise-audit-exit.txt` | Passed: no official-plugin trace evidence used `itmux --observability-langfuse` or `--observability-langfuse-force`. |
| Fallback guard regression | `runs/cli-exporters-test.txt`, `runs/cli-exporters-test-exit.txt` | Passed: 5 focused CLI exporter tests prove suppression/force/file/Syntropic exporter behavior remains green. |

## Trace Details

### Claude

- Trace: `0e553fc833c71639acd03be9807eb616`
- Session: `dfec301e-8152-4566-9253-cc211739b80b`
- Name: `Claude Code - Turn 1 (dfec301e)`
- Environment: `local-macbook`
- Observation count from trace list: 4
- Generation summary: 2 generations, model `claude-sonnet-5`, 15,445 input
  tokens, 149 output tokens, calculated total cost `0.1139603`.
- Observation sample included:
  - root `Claude Code - Turn 1` input/output with the run marker;
  - `LLM Call 1` generation requesting `Read`;
  - `Tool: Read` with file path and output;
  - `LLM Call 2` generation returning the marker.

The hook log shows the official Claude hook ran twice and processed one turn:
`runs/claude-session/hook-log-tail.txt`.

### Codex

- Trace: `b3d2561d7c0557c12fd427c02a16e2f3`
- Session/thread: `019f4324-c997-72c1-bae9-9eae62d84fc8`
- Name: `Codex Turn`
- Environment: `local-macbook`
- Observation count from trace list: 4
- Generation summary: 2 generations, model `gpt-5.5`, 34,341 input tokens,
  104 output tokens, calculated total cost `0.174825`.
- Observation sample included:
  - root `Codex Turn` input/output with the run marker;
  - generation requesting `exec_command`;
  - `exec_command` tool with command input and output;
  - final generation returning the marker.

## Caveats

- Claude local install did not persist the passed `--config` values according
  to the CLI message. The official hook still supports plain env fallback, and
  that is the path used for the successful real-session trace. Durable setup
  should still use `/plugin configure` or re-test install-time config behavior
  before relying on stored plugin config.
- `itmux langfuse-trace` summarizes official plugin traces well enough for
  learning loops, but its compact `agent_tools` rollup currently keys off
  agentic-primitives metadata and does not count official plugin `TOOL`
  observations. The raw observation samples prove the tools are present.
- The local repo's `.claude/settings.local.json` now has an uncommitted local
  plugin enablement side effect from the experiment. It contains no LangFuse
  keys and is intentionally not part of the experiment commit.
