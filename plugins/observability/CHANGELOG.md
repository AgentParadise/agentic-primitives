# Changelog — observability plugin

## 0.3.6
- Added a `uv`-run, chunked Claude historical replay utility to the LangFuse
  runbook. It feeds the official Claude exporter bounded, verbatim source-turn
  batches through isolated state and records a resumable submission manifest.

## 0.3.5
- Added the `langfuse-learning-loops` agent skill, documenting the project API
  and MCP query path, trace/session analysis workflow, and score feedback
- Documented the LangFuse dashboard API boundary: reusable observation widgets
  can be created programmatically, but dashboard-grid placement and absolute
  trace/session widgets remain UI-managed

## 0.3.4
- Launch the packaged `agentic-langfuse` MCP server through `uv run --script`
  rather than a host `python3` command

## 0.3.3
- Added `agentic_langfuse_session_report`, which groups the canonical
  per-turn LangFuse traces by `session_id` and returns turn, token, cost, tool,
  and score rollups for Claude and Codex learning loops
- Added MCP self-test coverage for the session-report command path

## 0.3.2
- Added default learning-loop insights to
  `agentic_langfuse_learning_loop_report`, including cost hotspots, token
  hotspots, missing model/cost/token coverage, unscored traces, and failed
  agent-tool recommendations
- Expanded the MCP self-test to cover both populated trace insights and
  missing-coverage recommendations

## 0.3.1
- Added `agentic_langfuse_learning_loop_report`, an MCP tool that combines
  trace discovery with per-trace drilldown to return aggregate learning-loop
  cost, token, generation, tool outcome, and score summaries for Claude and
  Codex traces
- Expanded the MCP self-test to exercise aggregate report generation through a
  deterministic local `itmux` test double

## 0.3.0
- Added the `agentic-langfuse` MCP server, which exposes agent-facing LangFuse
  trace discovery, trace summaries, score reads, and score write-back by
  delegating to the proven `itmux langfuse-*` CLI commands
- The MCP server falls back to direct LangFuse public API calls when `itmux` is
  not available in a packaged Claude/Codex environment
- MCP command failures redact sensitive-looking stdout/stderr before returning
  tool errors

## 0.2.3
- Claude hook handler now supports the `AGENTIC_EVENTS_JSONL` sink so workspace
  drivers can capture hook JSONL without using hook stdout
- Documented stderr plus sink output semantics for Claude hooks

## 0.2.2
- Git hooks (post-merge, post-rewrite, pre-push) now emit structured sha/branch/repo context via the typed git event payloads in agentic_events

## 0.1.0 (2026-02-18)
- Initial release: full-spectrum observability across all 14 Claude Code hook events
- Single generic handler (`observe.py`) dispatches all events
- Added SubagentStart, PostToolUseFailure, TeammateIdle, TaskCompleted event types to agentic_events
- Git hooks: post-commit, post-merge, post-rewrite, pre-push emitting via agentic_events
- Git hook installer (`install.py`) with --global and --uninstall support
