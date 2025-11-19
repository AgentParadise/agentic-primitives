# Hooks System Documentation

Welcome to the comprehensive documentation for the Agentic Primitives hooks system.

---

## 📚 Documentation Index

### Core Documentation

- **[Architecture](./architecture.md)** - Comprehensive architecture diagrams and system design
- **[Analytics Integration](../analytics-integration.md)** - Guide for integrating analytics
- **[Analytics Event Reference](../analytics-event-reference.md)** - Complete event schema reference
- **[Analytics Troubleshooting](../analytics-troubleshooting.md)** - Debugging and troubleshooting guide

### Service Documentation

- **[Analytics Service README](../../services/analytics/README.md)** - Analytics service overview
- **[Analytics Architecture](../../services/analytics/ARCHITECTURE.md)** - Technical design details
- **[Security Audit](../../services/analytics/SECURITY.md)** - Security assessment and guidelines

### Specifications

- **[Hook Metadata Schema](../../specs/v1/hook-meta.schema.json)** - Hook primitive specification
- **[Analytics Events Schema](../../specs/v1/analytics-events.schema.json)** - Event schema specification
- **[Model Config Schema](../../specs/v1/model-config.schema.json)** - Model configuration schema

### Architecture Decision Records

- **[ADR-011: Analytics Middleware](../adrs/011-analytics-middleware.md)** - Analytics architecture decisions

---

## 🎯 Quick Start

### For Users

**Install a hook primitive:**

```bash
# Install the analytics-collector hook for Claude
agentic install --provider claude \
  --primitive primitives/v1/hooks/analytics/analytics-collector
```

**Configure analytics:**

```bash
# File backend (local storage)
export ANALYTICS_PUBLISHER_BACKEND=file
export ANALYTICS_OUTPUT_PATH=./analytics/events.jsonl

# API backend (remote storage)
export ANALYTICS_PUBLISHER_BACKEND=api
export ANALYTICS_API_ENDPOINT=https://analytics.example.com/events
```

### For Developers

**Create a new hook primitive:**

```bash
# Create directory structure
mkdir -p primitives/v1/hooks/my-category/my-hook

# Create metadata file
cat > primitives/v1/hooks/my-category/my-hook/my-hook.hook.yaml << EOF
id: my-hook
kind: hook
category: my-category
event: PreToolUse
summary: "My custom hook"
execution:
  strategy: parallel
  timeout_sec: 5
  fail_on_error: false
middleware:
  - id: "my-middleware"
    path: "../../../services/my-service/middleware/my_middleware.py"
    type: "custom"
    enabled: true
EOF

# Create implementation
touch primitives/v1/hooks/my-category/my-hook/impl.python.py
touch primitives/v1/hooks/my-category/my-hook/my-hook.sh
```

**Build and test:**

```bash
# Validate
agentic validate primitives/v1/hooks/my-category/my-hook/

# Build
agentic build --provider claude \
  --primitive primitives/v1/hooks/my-category/my-hook

# Test
echo '{"provider":"claude","event":"PreToolUse","data":{...}}' | \
  ./build/claude/hooks/scripts/my-hook.sh
```

---

## 🏗️ System Architecture

### High-Level Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        AI Agent                              │
│  (Claude Desktop, OpenAI Codex, Cursor, etc.)               │
└───────────────────────┬─────────────────────────────────────┘
                        │ triggers
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                     Hook System                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ Hook Manager │→ │ Hook Primitive│→ │  Middleware  │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└───────────────────────┬─────────────────────────────────────┘
                        │ processes
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                  Analytics Service                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │  Normalizer  │→ │   Publisher  │→ │   Storage    │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
```

**Key Principles:**
- ✅ **Non-Blocking**: Hooks never block agent execution
- ✅ **Provider-Agnostic**: Works with any AI agent provider
- ✅ **Fail-Safe**: Errors are logged but don't crash the agent
- ✅ **Extensible**: Easy to add new hooks and middleware

---

## 📖 Concepts

### Hook Primitive

A **hook primitive** is a reusable, self-contained unit that defines:
- **Metadata**: Event type, category, execution strategy
- **Implementation**: Shell script + Python orchestrator
- **Configuration**: Environment variables, middleware pipeline

**Example Structure:**

```
primitives/v1/hooks/analytics/analytics-collector/
├── analytics-collector.hook.yaml   # Metadata
├── analytics-collector.sh           # Shell wrapper
├── impl.python.py                   # Python orchestrator
└── README.md                        # Documentation
```

### Hook Events

**10 Standard Hook Events:**

| Event | Description | When Triggered |
|-------|-------------|----------------|
| `SessionStart` | Session begins | Agent starts |
| `SessionEnd` | Session ends | Agent stops |
| `UserPromptSubmit` | User submits prompt | User input received |
| `PreToolUse` | Before tool execution | Tool about to run |
| `PostToolUse` | After tool execution | Tool completed |
| `PermissionRequest` | Permission needed | Agent requests permission |
| `Stop` | Agent stopped | User stops agent |
| `SubagentStop` | Subagent stopped | Subagent completes |
| `Notification` | System notification | System event |
| `PreCompact` | Before context compaction | Context about to compact |

### Middleware

**Middleware** is a processing unit in the hook pipeline:
- Receives input via stdin (JSON)
- Processes data
- Outputs result via stdout (JSON)
- Can be chained in a pipeline

**Example Middleware:**

```python
#!/usr/bin/env python3
import json
import sys

# Read input
input_data = json.loads(sys.stdin.read())

# Process
output_data = process(input_data)

# Write output
sys.stdout.write(json.dumps(output_data))
sys.stdout.flush()
```

---

## 🔧 CLI Commands

### Build

Build hook primitives for a specific provider:

```bash
agentic build --provider <provider> --primitive <path>
```

**Options:**
- `--provider`: Target provider (claude, openai, cursor)
- `--primitive`: Path to hook primitive directory

**Output:**
- `./build/<provider>/hooks/hooks.json` - Hook configuration
- `./build/<provider>/hooks/scripts/*.sh` - Shell scripts
- `./build/<provider>/hooks/scripts/*.py` - Python implementations

### Install

Install built hooks to the provider's directory:

```bash
agentic install --provider <provider> --build-dir <path>
```

**Options:**
- `--provider`: Target provider
- `--build-dir`: Path to build output directory

**Output:**
- Files copied to `.claude/`, `.openai/`, or `.cursor/`

### Validate

Validate hook primitive metadata:

```bash
agentic validate <path>
```

**Checks:**
- YAML syntax
- Required fields
- Schema compliance
- File existence

---

## 🎨 Analytics System

### Overview

The **analytics system** is a provider-agnostic middleware that:
1. Captures hook events from any provider
2. Normalizes events to a standard schema
3. Publishes events to file or API backends

### Event Flow

```
Provider Hook → HookInput → EventNormalizer → NormalizedEvent → Publisher → Storage
```

### Configuration

**File Backend (Local Storage):**

```bash
export ANALYTICS_PUBLISHER_BACKEND=file
export ANALYTICS_OUTPUT_PATH=./analytics/events.jsonl
```

**API Backend (Remote Storage):**

```bash
export ANALYTICS_PUBLISHER_BACKEND=api
export ANALYTICS_API_ENDPOINT=https://analytics.example.com/events
export ANALYTICS_API_TIMEOUT=30
export ANALYTICS_RETRY_ATTEMPTS=3
```

### Event Schema

**Normalized Event Structure:**

```json
{
  "event_type": "tool_execution_started",
  "timestamp": "2025-11-19T12:00:00+00:00",
  "session_id": "abc123-def456-ghi789",
  "provider": "claude",
  "context": {
    "tool_name": "Write",
    "tool_input": {"file_path": "test.py"},
    "tool_use_id": "toolu_123"
  },
  "metadata": {
    "hook_event_name": "PreToolUse",
    "transcript_path": "/path/to/transcript.jsonl",
    "permission_mode": "default"
  },
  "cwd": "/workspace"
}
```

---

## 🔒 Security

### Security Principles

1. **Non-Blocking**: Analytics never blocks agent execution
2. **Fail-Safe**: Errors are logged, not propagated
3. **Input Validation**: All inputs validated with Pydantic
4. **No PII**: No personally identifiable information collected by default
5. **HTTPS Only**: API backend enforces HTTPS

### Security Checklist

- ✅ Input validation with Pydantic
- ✅ File path validation
- ✅ Atomic writes
- ✅ HTTPS enforced
- ✅ Timeout configuration
- ✅ Retry logic with backoff
- ✅ No credentials stored
- ✅ No PII collected

**See**: [Security Audit](../../services/analytics/SECURITY.md)

---

## 🧪 Testing

### Test Coverage

- **Unit Tests**: 132 tests, 91% coverage
- **E2E Tests**: Full pipeline validation
- **Integration Tests**: Middleware and CLI
- **Performance Tests**: Throughput and memory

### Running Tests

**Analytics Service:**

```bash
cd services/analytics
uv run pytest tests/ -v --cov
```

**CLI:**

```bash
cd cli
cargo test
```

---

## 📊 Performance

### Benchmarks

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Throughput | 100 events/5s | 100 events/3s | ✅ PASS |
| Memory | No leaks | 1000 events OK | ✅ PASS |
| Latency | < 100ms/event | ~30ms/event | ✅ PASS |
| Concurrency | 5 publishers | 5 publishers OK | ✅ PASS |

---

## 🤝 Contributing

### Adding a New Hook

1. Create hook primitive directory
2. Write metadata YAML
3. Implement shell wrapper + Python orchestrator
4. Add tests
5. Update documentation
6. Submit PR

### Adding a New Provider

1. Create transformer in `cli/src/providers/`
2. Implement `ProviderTransformer` trait
3. Add provider-specific tests
4. Update CLI commands
5. Submit PR

---

## 📝 Examples

### Example 1: Basic Analytics Hook

See: [Analytics Collector](../../primitives/v1/hooks/analytics/analytics-collector/)

### Example 2: Custom Middleware

See: [Event Normalizer](../../services/analytics/middleware/event_normalizer.py)

### Example 3: Provider Transformer

See: [Claude Transformer](../../cli/src/providers/claude.rs)

---

## 🐛 Troubleshooting

### Common Issues

**Issue**: Hook not triggering

**Solution**:
1. Check hook is installed: `ls .claude/hooks/scripts/`
2. Verify `hooks.json` contains hook entry
3. Check hook permissions: `chmod +x .claude/hooks/scripts/*.sh`

**Issue**: Analytics events not written

**Solution**:
1. Check output path: `echo $ANALYTICS_OUTPUT_PATH`
2. Verify directory exists and is writable
3. Check logs: `tail -f /tmp/analytics.log`

**See**: [Troubleshooting Guide](../analytics-troubleshooting.md)

---

## 📞 Support

- **Documentation**: [docs/hooks/](.)
- **Issues**: [GitHub Issues](https://github.com/your-org/agentic-primitives/issues)
- **Discussions**: [GitHub Discussions](https://github.com/your-org/agentic-primitives/discussions)

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](../../LICENSE) file for details.

