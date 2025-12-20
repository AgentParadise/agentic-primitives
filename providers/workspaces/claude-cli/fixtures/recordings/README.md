# Session Recordings

This directory contains recorded agent sessions for testing.

See [ADR-030: Session Recording for Testing](../../../../docs/adrs/030-session-recording-testing.md).

## Naming Convention

```
v{cli_version}_{model}_{task-slug}.jsonl
```

Examples:
- `v1.0.52_claude-3-5-sonnet-20241022_git-status-check.jsonl`
- `v1.0.52_claude-3-5-opus-20240229_complex-refactor.jsonl`

CLI version first for better sorting (related versions stay together).

## Recording Format

Each file is JSONL with a metadata header:

```jsonl
{"_recording": {"version": 1, "cli_version": "1.0.52", "model": "claude-3-5-sonnet-20241022", ...}}
{"_offset_ms": 0, "event_type": "session_started", ...}
{"_offset_ms": 150, "event_type": "tool_execution_started", ...}
{"_offset_ms": 1200, "event_type": "tool_execution_completed", ...}
...
```

## How to Create a Recording

### Option 1: Using SessionRecorder in code

```python
from agentic_events import SessionRecorder

with SessionRecorder(
    output_path="recordings/v1.0.52_claude-3-5-sonnet_my-task.jsonl",
    cli_version="1.0.52",
    model="claude-3-5-sonnet-20241022",
    task="Description of what the agent does"
) as recorder:
    # Your code that generates events
    recorder.record({"event_type": "session_started", ...})
```

### Option 2: Environment variable (future)

```bash
AGENTIC_RECORD_SESSION=/output/recording.jsonl \
claude -p "Do something"
```

## How to Use in Tests

### Unit Tests (instant playback)

```python
from agentic_events import SessionPlayer

player = SessionPlayer("fixtures/recordings/v1.0.52_claude-3-5-sonnet_task.jsonl")

for event in player.get_events():
    await store.insert_one(event)

assert len(await projection.get(player.session_id)) > 0
```

### Integration Tests (timed playback)

```python
player = SessionPlayer("fixtures/recordings/v1.0.52_claude-3-5-sonnet_task.jsonl")

# Play at 100x speed (45 second session in 450ms)
await player.play(emit_fn=store.insert_one, speed=100)
```

## Available Recordings

| File | CLI | Model | Events | Duration | Description |
|------|-----|-------|--------|----------|-------------|
| *add recordings here* | | | | | |

## Contributing

When adding a new recording:

1. Use the naming convention: `v{version}_{model}_{task-slug}.jsonl`
2. Include a descriptive task name
3. Update this README with the recording details
4. Keep recordings small when possible (< 100 events)

