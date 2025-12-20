# Session Recordings

This directory contains recorded agent sessions for testing.

See [ADR-030: Session Recording for Testing](../../../../docs/adrs/030-session-recording-testing.md).

## Quick Start

### In Tests

```python
from agentic_events import load_recording

# Load by short name
player = load_recording("list-files")

# Get all events instantly
events = player.get_events()
assert len(events) == 12

# Replay with timing at 100x speed
await player.play(emit_fn=store.insert_one, speed=100)
```

### With Pytest Fixture

```python
@pytest.mark.recording("list-files")
def test_something(recording):
    events = recording.get_events()
    assert len(events) > 0
```

## Available Recordings

| File | CLI | Model | Events | Duration | Description |
|------|-----|-------|--------|----------|-------------|
| v2.0.74_claude-sonnet-4-5_list-files.jsonl | 2.0.74 | claude-sonnet-4-5 | 12 | 4.2s | List files using Bash |

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
{"_recording": {"version": 1, "event_schema_version": 1, "cli_version": "1.0.52", "model": "claude-3-5-sonnet-20241022", ...}}
{"_offset_ms": 0, "event_type": "session_started", ...}
{"_offset_ms": 150, "event_type": "tool_execution_started", ...}
{"_offset_ms": 1200, "event_type": "tool_execution_completed", ...}
...
```

### Event Schema Evolution

Recordings include `event_schema_version` for handling format changes:

- Version 0: Original format (implicit, no version field)
- Version 1: Current format with standardized field names

The `SessionPlayer` automatically migrates old formats to current schema.

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

### Option 2: Container logging capture (zero overhead)

```bash
# Pipe from docker run
docker run --rm agentic-workspace-claude-cli claude -p "Task" 2>&1 | \
    python scripts/capture_recording.py -o recording.jsonl -v

# Capture from running container
python scripts/capture_recording.py -c my-container -o recording.jsonl -f
```

## How to Use in Tests

### Unit Tests (instant playback)

```python
from agentic_events import load_recording

player = load_recording("list-files")

for event in player.get_events():
    await store.insert_one(event)

assert len(await projection.get(player.session_id)) > 0
```

### Integration Tests (timed playback)

```python
player = load_recording("list-files")

# Play at 100x speed (45 second session in 450ms)
await player.play(emit_fn=store.insert_one, speed=100)
```

## Troubleshooting

### "No recording found matching..."

Check available recordings:
```python
from agentic_events import list_recordings
print([p.name for p in list_recordings()])
```

### "Recording format is invalid"

Verify the recording has a metadata header:
```bash
head -1 recording.jsonl
# Should start with: {"_recording": ...}
```

### Events look wrong after playback

Check the event schema version:
```python
player = load_recording("my-recording")
print(f"Schema version: {player.metadata.event_schema_version}")
```

## Contributing

When adding a new recording:

1. Use the naming convention: `v{version}_{model}_{task-slug}.jsonl`
2. Include a descriptive task name
3. Update this README with the recording details
4. Keep recordings small when possible (< 100 events)
