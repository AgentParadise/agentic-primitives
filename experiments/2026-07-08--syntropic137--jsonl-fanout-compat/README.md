# Syntropic137 JSONL Fanout Compatibility

## Question

Can the current agentic-primitives `--observability-file` JSONL artifact be
consumed directly by Syntropic137's existing `syn_collector.watcher.HookWatcher`,
or does Syntropic137 need a dedicated bridge/exporter shape?

## Hypothesis

1. Syntropic137's hook watcher expects top-level hook-style events:
   `event_type`, `session_id`, `timestamp`, plus event-specific fields.
2. The current agentic-primitives file exporter writes `AgentRunEvent`
   envelopes with top-level `type`, `run_id`, `seq`, and nested event payload
   fields, so the Syntropic137 watcher will skip those lines as unknown hook
   events.
3. A dedicated Syntropic137 JSONL exporter shape can preserve the same local
   durable fanout while avoiding LangFuse noise and avoiding changes to
   Syntropic137's existing collector.

## Setup

- Agentic-primitives worktree:
  `/Users/neural/Code/Syntropic137/agentic-primitives_worktrees/20260707_itmux-run`
- Syntropic137 repo inspected read-only:
  `/Users/neural/Code/Syntropic137/syntropic137`
- Relevant Syntropic137 files:
  - `packages/syn-collector/src/syn_collector/watcher/hook_parser.py`
  - `packages/syn-collector/src/syn_collector/watcher/hooks.py`
  - `packages/syn-collector/src/syn_collector/events/types.py`

## Conditions

### Baseline

Feed representative current agentic-primitives `AgentRunEvent` JSONL into
Syntropic137's `HookWatcher.read_existing()`.

Expected baseline: zero parsed events.

### Control

Feed equivalent hook-style JSONL with top-level `event_type`, `session_id`, and
`timestamp`.

Expected control: parsed `CollectedEvent` rows for the known Syntropic137 event
types.

### Treatment

If baseline fails and control passes, add an agentic-primitives exporter or
documented adapter shape that emits hook-style Syntropic137 JSONL from the same
normalized event stream.

Expected treatment: Syntropic137 can consume local JSONL without enabling Rust
OTLP-to-LangFuse and without requiring official LangFuse plugin data.

## Expected Signals

- Baseline parser evidence proves whether current JSONL is direct-compatible.
- Control evidence proves Syntropic137's existing watcher is functional for the
  intended hook-style shape.
- Any treatment preserves existing `file` JSONL and `langfuse_otlp` contracts.
