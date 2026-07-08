# Eval Pack

## Frozen Probes

1. **Baseline summaries**
   - Query the known Claude trace with the current CLI summary path:
     `itmux langfuse-trace --api legacy-trace --output summary --trace-id 0e553fc833c71639acd03be9807eb616`
   - Query the known Codex trace with the current CLI summary path:
     `itmux langfuse-trace --api legacy-trace --output summary --trace-id b3d2561d7c0557c12fd427c02a16e2f3`
   - Store raw artifacts under `runs/baseline-*`.

2. **Raw observation confirmation**
   - Capture enough raw LangFuse observation data to prove the two traces
     contain official `TOOL` observations before the summarizer change.
   - Store Claude and Codex samples under `runs/raw-*`.

3. **Implementation**
   - Patch only the LangFuse trace summary logic and focused tests.
   - Official `TOOL` observations should be categorized as `agent_tool` unless
     explicit agentic metadata already provides a more specific tool event.
   - Tool names should prefer `agentic.tool.name`, then strip a leading
     `Tool: ` from the LangFuse observation name, then fall back to the raw
     observation name.

4. **Regression tests**
   - Run the focused Rust summary tests.
   - Run `cargo fmt --check`.
   - Store command output under `runs/test-*`.

5. **Treatment summaries**
   - Re-query the same Claude and Codex trace IDs after the patch.
   - Store artifacts under `runs/treatment-*`.
   - Compare `agent_tools.names`, `agent_tools.end_count`, and
     `agent_tools.success_count` against baseline.

6. **Hygiene checks**
   - Scan changed tracked files and experiment artifacts for unredacted
     LangFuse key patterns.
   - Confirm the experiment did not invoke fallback
     `--observability-langfuse` export to generate the treatment data.

## Success Criteria

- Baseline summaries show the known failure: zero or missing official plugin
  tool rollups despite raw `TOOL` observations.
- Treatment summaries show Claude `Read` and Codex `exec_command` in
  `agent_tools.names`.
- Existing metadata-shaped `tool_start`/`tool_end` tests remain green.
- No secrets are committed.

## Inconclusive Criteria

- Local LangFuse is unavailable or no longer contains the known trace IDs.
- The known official-plugin traces were pruned before baseline capture.
- The API response shape changed enough that raw observations cannot be
  compared to prior evidence.
