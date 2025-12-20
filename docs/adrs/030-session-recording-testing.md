# ADR-030: Session Recording for Testing

## Status
Accepted

## Date
2024-12-20

## Context

Testing AI agent integrations is challenging because:

1. **API Costs**: Each test run against real Claude API costs money
2. **Non-determinism**: Agent responses vary, making tests flaky
3. **Speed**: Real agent sessions take 30-300+ seconds
4. **CI/CD Complexity**: Requires API keys and network access
5. **Edge Cases**: Hard to reproduce errors, timeouts, specific tool sequences

We need a way to test the observability pipeline (events → store → projections → API → UI) without running real agent sessions every time.

## Decision

Implement a **Session Recording and Playback** system in `agentic_events`:

### 1. SessionRecorder
Captures events with timing during real agent sessions.

```python
from agentic_events import SessionRecorder

recorder = SessionRecorder(
    output_path="fixtures/v1.0.52_claude-3-5-sonnet_git-status.jsonl",
    cli_version="1.0.52",
    model="claude-3-5-sonnet-20241022",
    task="Simple git status check"
)

# Events are recorded with timing offsets
recorder.record({"event_type": "session_started", ...})
recorder.record({"event_type": "tool_execution_started", ...})
recorder.close()
```

### 2. SessionPlayer
Replays recorded sessions at configurable speed.

```python
from agentic_events import SessionPlayer

player = SessionPlayer("fixtures/v1.0.52_claude-3-5-sonnet_git-status.jsonl")

# Instant playback for unit tests
events = player.get_events()

# Timed playback at 100x speed for integration tests
await player.play(emit_fn=event_store.insert_one, speed=100)
```

### 3. Recording Format (JSONL)

```jsonl
{"_recording": {"version": 1, "cli_version": "1.0.52", "model": "claude-3-5-sonnet-20241022", "recorded_at": "2024-12-20T...", "duration_ms": 45000, "task": "Simple git status check", "event_count": 12}}
{"_offset_ms": 0, "event_type": "session_started", "session_id": "abc-123", ...}
{"_offset_ms": 150, "event_type": "tool_execution_started", "context": {"tool_name": "Bash"}, ...}
{"_offset_ms": 1200, "event_type": "tool_execution_completed", "context": {"success": true}, ...}
{"_offset_ms": 45000, "event_type": "session_completed", ...}
```

### 4. Naming Convention

```
{cli_version}_{model}_{task-slug}.jsonl
```

Examples:
- `v1.0.52_claude-3-5-sonnet-20241022_git-status-check.jsonl`
- `v1.0.52_claude-3-5-opus-20240229_complex-refactor.jsonl`
- `v1.0.50_claude-3-5-sonnet-20241022_error-recovery.jsonl`

CLI version first for better sorting (versions change together).

### 5. Fixture Location

Recordings live near the provider workspace they were captured from:

```
providers/workspaces/claude-cli/
  fixtures/
    recordings/
      README.md
      v1.0.52_claude-3-5-sonnet-20241022_simple-bash.jsonl
      v1.0.52_claude-3-5-sonnet-20241022_code-review.jsonl
```

### 6. Container Logging Capture (Zero Overhead)

For production scale (10k+ agents), we use external capture instead of in-process recording.
The agent writes events to stderr as JSONL, and an external process captures them.

**Why external capture?**
- Zero overhead on the agent (no listeners, no middleware)
- Agent just writes to stderr and continues
- Recording happens outside the agent process
- Scales to 10k+ concurrent agents

**Architecture:**
```
┌─────────────────────────────────────────────────────────────────┐
│                     AGENT CONTAINER                              │
│   Claude CLI → hooks → EventEmitter → stderr (JSONL)            │
│                                 │                                │
│                     (writes, doesn't wait)                       │
└─────────────────────────────────┼────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────┴────────────────────────────────┐
│                     EXTERNAL CAPTURE                              │
│   docker logs → capture_recording.py → recording.jsonl           │
└──────────────────────────────────────────────────────────────────┘
```

**Usage:**
```bash
# Pipe from docker run
docker run --rm agentic-workspace-claude-cli claude -p "Task" 2>&1 | \
    python scripts/capture_recording.py -o recording.jsonl -v

# Capture from running container
python scripts/capture_recording.py -c my-container -o recording.jsonl -f

# Auto-generate filename
python scripts/capture_recording.py --generate-name \
    --cli-version 1.0.52 --model claude-3-5-sonnet --task "git status"
```

## Consequences

### Positive
- **Fast tests**: 45-second session replays in 45ms at 1000x speed
- **Deterministic**: Same events every time
- **No API costs**: Record once, replay forever
- **CI/CD friendly**: No secrets needed for playback
- **Debuggable**: Share recordings to reproduce issues
- **Version tracking**: CLI version + model in filename

### Negative
- Recordings can become stale if event format changes
- Need to re-record after schema changes
- Storage for recording files

### Mitigations
- Version field in recording metadata
- Schema validation on playback
- Git LFS for large recordings (if needed)

## Implementation

```
lib/python/agentic_events/agentic_events/
  recorder.py    # SessionRecorder class (in-process)
  player.py      # SessionPlayer class (playback)

scripts/
  capture_recording.py  # External capture from container logs

providers/workspaces/claude-cli/fixtures/recordings/
  README.md
  *.jsonl
```

### Capture Methods

| Method | Use Case | Overhead |
|--------|----------|----------|
| `SessionRecorder` | Dev/testing, direct access | Low |
| `capture_recording.py` | Production, containers | Zero |

## Related ADRs

- ADR-029: Simplified Event System (event types)
- ADR-027: Provider Workspace Images (where recordings live)
