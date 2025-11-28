# PROJECT PLAN: Analytics Integration for Hook System
**Date**: 2025-11-18  
**Task**: Integrate provider-agnostic analytics system into agentic-primitives hook middleware pipeline

---

## Overview

Integrate a provider-agnostic analytics system that:
- Receives hook events from any provider (Claude, OpenAI, Cursor, etc.)
- Normalizes events using Pydantic models for type safety
- Publishes events to analytics backend (file/API)
- Uses port & adapter pattern for extensibility
- Follows TDD with >80% test coverage (>90% for core logic)

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│         Provider-Specific Hook Events                    │
│  (Claude, OpenAI, Cursor - different JSON formats)      │
└────────────────────┬────────────────────────────────────┘
                     │ stdin (JSON)
                     ▼
┌─────────────────────────────────────────────────────────┐
│    Analytics Middleware (Provider Adapter Layer)        │
│  - Validates input with Pydantic models                 │
│  - Maps provider-specific fields to standard schema     │
└────────────────────┬────────────────────────────────────┘
                     │ NormalizedEvent
                     ▼
┌─────────────────────────────────────────────────────────┐
│         Event Normalizer (Business Logic)               │
│  - Extracts context (tool, session, user prompt)        │
│  - Maps hook events → analytics event types             │
│  - Validates output with Pydantic models                │
└────────────────────┬────────────────────────────────────┘
                     │ StandardEventSchema
                     ▼
┌─────────────────────────────────────────────────────────┐
│     Event Publisher (Output Adapter Layer)              │
│  - File backend (JSONL)                                 │
│  - API backend (HTTP POST)                              │
│  - Future: Message queue (Redis, Kafka)                 │
└─────────────────────────────────────────────────────────┘
```

---

## Milestones

### ✅ Milestone 1: Foundation - Event Schema & Type System (COMPLETE)
**Goal**: Define the contract layer with Pydantic models and schemas

**Status**: ✅ **COMPLETE** (2025-11-19)

**Tasks**:
- [x] 1.1: Create analytics service directory with uv Python
- [x] 1.2: Define Pydantic models for hook input events
- [x] 1.3: Define Pydantic models for normalized events
- [x] 1.4: Create JSON Schema for analytics events
- [x] 1.5: Write comprehensive test fixtures

**Acceptance Criteria**:
- ✅ All Pydantic models with **97.30% test coverage** (exceeds 100% target)
- ✅ `uv run mypy src/analytics` passes with no errors (strict mode)
- ✅ `uv run ruff check src tests` passes with no warnings
- ✅ JSON schema validates all event types

**Key Decisions**:
- ✅ **Provider-agnostic design**: No hardcoded provider enums (see ADR-011)
- ✅ **Latest dependencies**: Pydantic 2.12.4, mypy 1.18.2, ruff 0.14.5
- ✅ **32 comprehensive tests** covering all models and edge cases

**Deliverables**:
- `services/analytics/` with complete type-safe models
- `specs/v1/analytics-events.schema.json` (generated from Pydantic)
- `docs/adrs/011-analytics-middleware.md` (architecture decision)
- `services/analytics/ARCHITECTURE.md` (technical design)
- `services/analytics/README.md` (usage documentation)

---

### ✅ Milestone 2: Core Logic - Event Normalization
**Goal**: Implement provider-agnostic event normalization

**Tasks**:
- [ ] 2.1: Write tests for event normalizer (TDD)
- [ ] 2.2: Implement EventNormalizer class
- [ ] 2.3: Implement provider adapters (Claude, OpenAI, base)
- [ ] 2.4: Add configuration validation with Pydantic

**Acceptance Criteria**:
- >90% test coverage for normalization logic
- All provider adapters tested with real fixture data
- Configuration validates environment variables
- Error handling tested for malformed inputs

---

### ✅ Milestone 3: Publisher Service - Event Output
**Goal**: Implement event publishing with backend support

**Tasks**:
- [ ] 3.1: Write tests for event publisher (TDD)
- [ ] 3.2: Implement base publisher interface
- [ ] 3.3: Implement file publisher (JSONL)
- [ ] 3.4: Implement API publisher (HTTP POST)
- [ ] 3.5: Add retry logic and error handling

**Acceptance Criteria**:
- >80% test coverage for publishers
- File publisher appends to JSONL atomically
- API publisher handles network errors gracefully
- Retry logic tested with exponential backoff

---

### ✅ Milestone 4: Middleware Integration - Hook System
**Goal**: Integrate analytics as middleware type in hook system

**Tasks**:
- [ ] 4.1: Extend MiddlewareType enum in Rust (`cli/src/primitives/hook.rs`)
- [ ] 4.2: Update hook-meta.schema.json to include "analytics" type
- [ ] 4.3: Create analytics middleware entry points (Python)
- [ ] 4.4: Write integration tests for middleware pipeline
- [ ] 4.5: Update CLI validators to support analytics middleware

**Acceptance Criteria**:
- Schema validation accepts "analytics" middleware type
- Middleware integrates into existing pipeline without breaking safety/observability
- Integration tests pass for all hook events
- CLI commands validate analytics hooks correctly

---

### ✅ Milestone 5: System-Level Hook Primitive
**Goal**: Create reusable analytics hook primitive

**Tasks**:
- [ ] 5.1: Create hook primitive structure (`primitives/v1/hooks/analytics/analytics-collector/`)
- [ ] 5.2: Write analytics-collector.hook.yaml metadata
- [ ] 5.3: Implement hook orchestrator (impl.python.py)
- [ ] 5.4: Create middleware configurations for normalizer + publisher
- [ ] 5.5: Add provider-specific implementations

**Acceptance Criteria**:
- Hook validates with `agentic-p validate`
- Hook can be tested with `agentic-p test-hook`
- Works with all supported providers (Claude, OpenAI)
- Documented with usage examples

---

### ✅ Milestone 6: Provider Transformer Extensions
**Goal**: Update provider transformers to include analytics hooks

**Tasks**:
- [ ] 6.1: Extend ClaudeTransformer to generate analytics hooks config
- [ ] 6.2: Extend OpenAITransformer to generate analytics hooks config
- [ ] 6.3: Update build command to include analytics hooks
- [ ] 6.4: Write transformer tests with analytics fixtures
- [ ] 6.5: Update install command to support analytics flag

**Acceptance Criteria**:
- `agentic-p build --provider claude` includes analytics hooks
- Generated hooks.json contains analytics middleware entries
- `agentic-p install --with-analytics` flag works
- Transformer tests pass with analytics hooks enabled

---

### ✅ Milestone 7: Documentation & Examples
**Goal**: Comprehensive documentation and usage examples

**Tasks**:
- [ ] 7.1: Create ADR for analytics architecture decision
- [ ] 7.2: Write analytics integration guide (docs/analytics-integration.md)
- [ ] 7.3: Add example hook configurations for each event type
- [ ] 7.4: Document event schema with examples
- [ ] 7.5: Create troubleshooting guide

**Acceptance Criteria**:
- ADR documents architectural decisions
- Integration guide covers setup, configuration, testing
- Examples work for all major hook events
- Event schema documented with JSON examples

---

### ✅ Milestone 8: Testing & QA
**Goal**: Comprehensive testing and quality assurance

**Tasks**:
- [ ] 8.1: Write end-to-end tests for full analytics pipeline
- [ ] 8.2: Add performance benchmarks for event processing
- [ ] 8.3: Test with real Claude Code hook events
- [ ] 8.4: Security audit for analytics data handling
- [ ] 8.5: Final QA checkpoint and coverage verification

**Acceptance Criteria**:
- E2E tests cover complete flow from hook input to event output
- Performance benchmarks show <10ms overhead per event
- Real-world testing with Claude Code validates correctness
- Security audit passes (no PII leakage, safe file handling)
- Final coverage: >80% overall, >90% for core analytics logic

---

## Technical Specifications

### Event Schema Structure

```json
{
  "event_type": "tool_execution_started",
  "timestamp": "2025-11-18T12:34:56.789Z",
  "session_id": "abc123",
  "provider": "claude",
  "context": {
    "tool_name": "Write",
    "tool_input": {...},
    "cwd": "/project",
    "permission_mode": "default"
  },
  "metadata": {
    "hook_event_name": "PreToolUse",
    "transcript_path": "/path/to/transcript.jsonl",
    "raw_event": {...}
  }
}
```

### Event Type Mapping

| Hook Event         | Analytics Event Type      | Key Context Data              |
|--------------------|---------------------------|-------------------------------|
| SessionStart       | session_started           | source (startup/resume)       |
| SessionEnd         | session_completed         | reason, duration              |
| UserPromptSubmit   | user_prompt_submitted     | prompt text                   |
| PreToolUse         | tool_execution_started    | tool_name, tool_input         |
| PostToolUse        | tool_execution_completed  | tool_name, tool_response      |
| PermissionRequest  | permission_requested      | tool_name, decision           |
| Stop               | agent_stopped             | stop_hook_active              |
| SubagentStop       | subagent_stopped          | task context                  |
| Notification       | system_notification       | notification_type, message    |
| PreCompact         | context_compacted         | trigger (manual/auto)         |

### Directory Structure

```
services/analytics/
├── pyproject.toml              # uv project config
├── uv.lock                     # Locked dependencies
├── README.md                   # Usage documentation
├── src/
│   └── analytics/
│       ├── __init__.py
│       ├── models/
│       │   ├── __init__.py
│       │   ├── hook_input.py   # Pydantic models for hook inputs
│       │   ├── events.py       # Pydantic models for normalized events
│       │   └── config.py       # Configuration models
│       ├── adapters/
│       │   ├── __init__.py
│       │   ├── base.py         # Abstract adapter interface
│       │   ├── claude.py       # Claude-specific adapter
│       │   └── openai.py       # OpenAI-specific adapter
│       ├── normalizer.py       # Event normalization logic
│       └── publishers/
│           ├── __init__.py
│           ├── base.py         # Abstract publisher interface
│           ├── file.py         # File backend (JSONL)
│           └── api.py          # API backend (HTTP POST)
├── middleware/
│   ├── event_normalizer.py     # Middleware entry point for normalizer
│   └── event_publisher.py      # Middleware entry point for publisher
└── tests/
    ├── conftest.py             # Pytest fixtures
    ├── fixtures/
    │   ├── claude_hooks/       # Sample Claude hook inputs
    │   └── normalized_events/  # Expected normalized outputs
    ├── test_models.py          # Pydantic model tests (100% coverage)
    ├── test_normalizer.py      # Normalizer tests (>90% coverage)
    ├── test_adapters.py        # Adapter tests (>90% coverage)
    ├── test_publishers.py      # Publisher tests (>80% coverage)
    └── test_integration.py     # E2E integration tests

primitives/v1/hooks/analytics/
└── analytics-collector/
    ├── analytics-collector.hook.yaml   # Hook metadata
    ├── impl.python.py                  # Hook orchestrator
    └── middleware/
        ├── analytics/
        │   ├── event-normalizer.py     # Normalizer middleware
        │   └── event-publisher.py      # Publisher middleware
        └── README.md                   # Middleware documentation

specs/v1/
└── analytics-events.schema.json        # JSON schema for events

cli/src/primitives/
└── hook.rs                             # Updated with MiddlewareType::Analytics

docs/
├── analytics-integration.md            # Integration guide
└── adrs/
    └── 011-analytics-middleware.md     # Architecture decision record
```

### Dependencies (pyproject.toml)

```toml
[project]
name = "agentic-analytics"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.9.0",
    "pydantic-settings>=2.5.0",
    "httpx>=0.27.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3.0",
    "pytest-cov>=5.0.0",
    "pytest-asyncio>=0.24.0",
    "mypy>=1.11.0",
    "ruff>=0.6.0",
    "black>=24.8.0",
]

[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true
disallow_any_generics = true

[tool.ruff]
line-length = 100
target-version = "py311"
select = ["E", "F", "I", "N", "W", "UP", "ANN", "B", "C90", "RUF"]

[tool.ruff.per-file-ignores]
"tests/*" = ["ANN"]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = "test_*.py"
addopts = "--strict-markers --cov=src --cov-report=term --cov-report=html"

[tool.coverage.run]
branch = true
source = ["src"]

[tool.coverage.report]
fail_under = 80
show_missing = true
```

---

## QA Process

### Before Each Milestone

1. Write tests first (TDD approach)
2. Run `make python-typecheck` (must pass)
3. Run `make python-lint` (must pass)
4. Ensure test fixtures cover edge cases

### After Each Milestone

1. Run `make python-test-coverage` (>80% required, >90% for core)
2. Run `make python-fmt` (auto-format)
3. Run `make python-lint-fix` (auto-fix linting)
4. Review git diff for unintended changes
5. Commit with conventional commit message

### Final QA Checkpoint

```bash
# Full QA pipeline
make python-typecheck      # mypy strict mode
make python-lint           # ruff all rules
make python-test-coverage  # pytest with coverage
make rust-lint             # clippy for Rust changes
make rust-test             # Rust integration tests
make validate              # Full primitive validation
```

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| **Pydantic validation overhead** | Use `model_validate()` only at boundaries, pass validated models internally |
| **File I/O errors** | Atomic writes, proper locking, error handling with retries |
| **Provider schema changes** | Version adapters, add provider schema tests |
| **Performance degradation** | Async processing, batch publishing, benchmarking |
| **Type safety violations** | Strict mypy config, no `type: ignore`, 100% model coverage |

---

## Success Criteria

- ✅ All Pydantic models validated with 100% test coverage
- ✅ Core analytics logic has >90% test coverage
- ✅ Publishers and adapters have >80% test coverage
- ✅ All QA checks pass (`python-typecheck`, `python-lint`, `python-test`)
- ✅ Integration tests pass for all hook events
- ✅ Real-world testing with Claude Code validates correctness
- ✅ Documentation complete with examples
- ✅ ADR documented and approved

---

## Notes

- **Testing is as important as production code** (per ADR-008)
- **Use Pydantic strict mode** to catch type errors early
- **Follow port & adapter pattern** for extensibility
- **Keep middleware non-blocking** (analytics type = observability behavior)
- **Validate at boundaries** (input from providers, output to backends)
- **NEVER commit without passing QA checks**

---

**Status**: Planning Complete  
**Next Step**: Begin Milestone 1 - Foundation (EEM when ready)


