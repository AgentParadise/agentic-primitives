# Official Claude Plugin Trace Contract

Source: `/tmp/langfuse-claude-plugin`
Commit: `9ad0076a7a24e8673ac6e7ac6f7b658b18826bb6`

## Evidence

- `hooks/hooks.json` registers both `Stop` and `SessionEnd` hooks.
- `README.md` states the hook reads the session transcript incrementally and
  emits one span per turn, nested generations, child tool spans, and token
  usage when present.
- `hooks/langfuse_hook.py` uses transcript JSONL state with byte offsets and
  buffering, not only lifecycle hook payloads.
- `emit_turn` creates a root `Conversational Turn` observation with
  `as_type="span"` and root `input={"role":"user",...}`; it later updates root
  output with the final assistant content.
- `emit_generation_observation` creates `as_type="generation"` observations.
  `build_generation_kwargs` sets model, input, output, metadata, and
  `usage_details` when transcript usage is present.
- `emit_single_tool_observation` creates `as_type="tool"` observations named
  `Tool: <tool_name>`, sets tool input and metadata at start, updates tool
  output, and ends at a backdated tool-result timestamp.
- `_start_backdated` intentionally uses LangFuse SDK v4 internals to preserve
  historical start times.

## Runtime Test

`runs/official-claude-tests.txt`:

- `uv run pytest`
- 48 tests passed.
- Coverage includes transcript reading, turn assembly, payload builders,
  subagent discovery, subagent observations, task notifications, and integration
  emission tests.

## Scoring Against Probe A

- Stop/SessionEnd hooks: pass.
- Transcript JSONL reader: pass.
- Root input/output: pass.
- Generation model/usage: pass.
- Tool semantic names/input/output: pass.

