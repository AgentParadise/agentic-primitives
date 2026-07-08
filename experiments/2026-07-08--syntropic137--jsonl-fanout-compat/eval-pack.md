# Eval Pack

This eval pack is frozen after the hypothesis commit.

## Probe A: Syntropic137 Parser Surface

Record the relevant current Syntropic137 parser and event type surface:

- `HOOK_EVENT_MAP` from `hook_parser.py`
- `CollectedEvent` required fields from `events/types.py`

Evidence:

- `runs/syntropic-parser-surface.md`

## Probe B: Baseline AgentRunEvent JSONL

Create a representative current agentic-primitives `AgentRunEvent` JSONL file
with:

- `session_start`
- `tool_start`
- `tool_end`
- `token_usage`
- `session_end`

Feed it through Syntropic137's `HookWatcher.read_existing()`.

Evidence:

- `runs/baseline-agent-run-events.jsonl`
- `runs/baseline-parse.json`

## Probe C: Control Hook-Style JSONL

Create equivalent hook-style JSONL with top-level Syntropic137 event names.
Feed it through the same watcher.

Evidence:

- `runs/control-hook-events.jsonl`
- `runs/control-parse.json`

## Probe D: Treatment Verification

If an adapter/exporter is added, run a focused local test proving:

- current `file` exporter still emits `AgentRunEvent`;
- Syntropic137 exporter emits hook-style events;
- LangFuse fallback behavior is unchanged.

Evidence:

- `runs/treatment-test.txt`
- `runs/treatment-test-exit.txt`

## Hygiene

Run:

```bash
git diff --check
```

Evidence:

- `runs/diff-check.txt`
- `runs/diff-check-exit.txt`

## Verdict Rules

Use verdict `go` if the current compatibility state is proven and either direct
compatibility exists or a bridge/exporter is implemented and verified.

Use verdict `no-go` if Syntropic137 cannot consume either current JSONL or a
reasonable bridge shape without invasive changes.

Use verdict `inconclusive` if Syntropic137 dependencies cannot be imported
locally.
