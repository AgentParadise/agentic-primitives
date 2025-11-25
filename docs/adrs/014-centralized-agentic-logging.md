---
title: "ADR-014: Centralized Agentic Logging System"
status: proposed
created: 2025-11-25
updated: 2025-11-25
author: AI Agent (Claude)
---

# ADR-014: Centralized Agentic Logging System

## Status

**Proposed**

- Created: 2025-11-25
- Updated: 2025-11-25
- Author(s): AI Agent (Claude)

## Context

The agentic-primitives codebase currently has fragmented logging approaches across different Python components:

1. **Analytics service** uses Python's standard `logging` module with `logging.getLogger(__name__)` but has no centralized configuration. The `ANALYTICS_DEBUG` config field exists but is never used to configure logging behavior.

2. **Hook scripts** (e.g., `hooks-collector.py`) use `print()` statements to stderr for diagnostic messages, resulting in:
   - Inconsistent formatting
   - No log level control
   - Difficult to parse programmatically
   - No structured context

3. **No shared logging infrastructure** exists across services, leading to:
   - Duplicated configuration logic
   - Inconsistent log formats
   - No session correlation across components
   - Poor AI agent debugging experience

### Key Problems

**For AI Agents:**
- Logs are unstructured text, hard to parse
- No way to enable DEBUG for specific components
- Cannot correlate logs across service boundaries (no session IDs)
- Context window pollution when debugging (too much or too little info)

**For Developers:**
- No central place to configure logging behavior
- Inconsistent log formats across components
- Cannot easily filter or search logs
- No rotating log files (disk space issues)

**For Operations:**
- Production systems log everything or nothing (no granular control)
- No JSONL output for log aggregation systems
- Cannot trace requests through the system (no session correlation)

### Forces at Play

1. **AI-First Philosophy**: This system is built for AI agents to operate autonomously. Logs are feedback for agents, not just humans. Structured, parseable logs are critical.

2. **Multiple Python Components**: Analytics service, hook scripts, middleware, and future services all need consistent logging.

3. **UV Ecosystem**: The project uses UV for Python dependency management, requiring workspace-compatible solutions.

4. **Fail-Safe Operation**: Logging errors must never crash the agent system. Hooks especially must be resilient.

5. **Performance**: Logging overhead must be minimal (<1ms per call) to avoid slowing down hook execution.

6. **Developer Experience**: Humans need readable logs during development, but agents need structured JSON in production.

## Decision

**We will implement a centralized logging library at `/lib/python/agentic_logging/` that provides a unified logging interface for all Python code in the repository.**

The system will:

1. **Use Python's standard `logging` module** as the foundation (no custom logging framework)
2. **Extend with `python-json-logger`** for structured JSON output (single additional dependency)
3. **Provide a simple factory API**: `get_logger(__name__, session_id=None)`
4. **Support environment variable configuration** for all logging behavior
5. **Enable per-component log level control** via `LOG_LEVEL_{COMPONENT_NAME}` pattern
6. **Output JSON to files** (JSONL format) and **hybrid console** (human-readable or JSON)
7. **Include session context** in every log entry for cross-component correlation
8. **Use rotating file handlers** (10MB files, 5 backups) to prevent disk exhaustion
9. **Be integrated via UV workspace** for dependency management

### Core API

```python
from agentic_logging import get_logger

logger = get_logger(__name__, session_id="abc123")
logger.debug("Detailed info", extra={"key": "value"})
logger.warning("Recoverable issue", extra={"reason": "timeout"})
logger.error("Operation failed", exc_info=True)
```

### Configuration

```bash
# System-wide
LOG_LEVEL=WARNING                     # Default production level
LOG_FILE=./logs/agentic.jsonl         # Single rotating log
LOG_CONSOLE_FORMAT=human              # human | json
LOG_MAX_BYTES=10485760                # 10MB rotation
LOG_BACKUP_COUNT=5                    # Keep 5 backups

# Per-component (granular control for debugging)
LOG_LEVEL_HOOKS_COLLECTOR=DEBUG
LOG_LEVEL_ANALYTICS=INFO
```

## Alternatives Considered

### Alternative 1: Continue with Ad-Hoc Logging

**Description**: Keep using `print()` in hooks and `logging.getLogger()` in services without centralized configuration.

**Pros**:
- No code changes required
- No new dependencies
- Developers familiar with current approach

**Cons**:
- Fragmentation continues to worsen
- AI agents cannot parse logs effectively
- No session correlation across components
- Production debugging remains difficult
- Inconsistent formats make log aggregation impossible

**Reason for rejection**: Does not solve the core problem. As more services are added, the fragmentation will become unmanageable.

---

### Alternative 2: Use `structlog` Library

**Description**: Adopt `structlog` as a structured logging framework instead of extending Python's standard `logging`.

**Pros**:
- Purpose-built for structured logging
- Excellent JSON formatting
- Rich processor pipeline (filtering, formatting, enrichment)
- Popular in modern Python projects

**Cons**:
- Additional dependency (not in standard library)
- Learning curve for developers unfamiliar with structlog
- More complex configuration
- Less compatible with existing `logging.getLogger()` calls
- Requires more migration effort

**Reason for rejection**: Adds unnecessary complexity. Python's standard `logging` + `python-json-logger` provides 90% of structlog's benefits with better compatibility and fewer dependencies.

---

### Alternative 3: Service-Specific Logging (No Shared Library)

**Description**: Each service (analytics, hooks) implements its own logging configuration without a shared library.

**Pros**:
- Services remain independent
- No shared library to maintain
- Flexibility per service

**Cons**:
- Code duplication across services
- Inconsistent log formats
- No session correlation across services
- Cannot enable DEBUG globally for investigation
- Migration effort multiplied across services

**Reason for rejection**: Does not achieve the goal of centralized, consistent logging for AI agents.

---

### Alternative 4: Use `loguru` Library

**Description**: Adopt `loguru` as a modern, simpler logging library.

**Pros**:
- Simpler API than standard logging
- Built-in JSON support
- Automatic rotation
- Better defaults
- Nice color formatting

**Cons**:
- Another external dependency
- Incompatible with standard `logging` (cannot mix)
- Requires replacing all existing `logging.getLogger()` calls
- Less widespread adoption (risk of abandonment)
- Not compatible with libraries that use standard logging

**Reason for rejection**: Too disruptive. Standard logging is ubiquitous and compatible with the ecosystem. Loguru's API simplicity doesn't justify the migration cost.

---

### Alternative 5: Multiple Log Files (Per-Component or Per-Session)

**Description**: Write separate log files for each component (hooks.jsonl, analytics.jsonl) or each session (session-abc123.jsonl).

**Pros**:
- Clear separation by component/session
- Easy to isolate specific logs
- Can set different retention policies

**Cons**:
- Many files to manage (potentially hundreds of session files)
- Harder to see system-wide patterns
- Correlation across components requires external tools
- More complex configuration

**Reason for rejection**: Single log file with session_id in each entry provides the same benefits via filtering (`grep '"session_id":"abc123"'`) without the file management overhead.

## Consequences

### Positive Consequences

1. **AI Agents Get Structured Feedback**
   - JSON logs are trivially parseable
   - Session correlation enables tracing across components
   - Per-component DEBUG enables focused investigation
   - Context window optimization (only relevant logs)

2. **Consistent Logging Across Codebase**
   - Single API: `get_logger(__name__)`
   - Same format everywhere (JSONL files, configurable console)
   - Shared configuration reduces duplication

3. **Production Debugging Simplified**
   - Enable DEBUG for specific components without code changes
   - Session IDs enable request tracing
   - Rotating logs prevent disk exhaustion
   - Structured fields enable powerful filtering

4. **Developer Experience Improved**
   - Human-readable console format in development
   - Color-coded log levels
   - Familiar standard logging API
   - No print() statements cluttering code

5. **Fail-Safe Operation**
   - Logging errors never crash the system
   - Graceful degradation to stderr
   - Default levels prevent log spam

### Negative Consequences

1. **Migration Effort Required**
   - All `print()` statements in hooks must be replaced
   - Analytics service needs minor updates
   - Developers must learn new configuration variables
   - Estimated: 4-6 hours of implementation

2. **Additional Dependency**
   - `python-json-logger` must be maintained
   - Slight increase in dependency surface area
   - **Mitigation**: Well-maintained library (2.0.7+, active development)

3. **Configuration Complexity**
   - More environment variables to manage
   - Per-component naming convention requires understanding
   - **Mitigation**: Comprehensive documentation and examples

4. **Breaking Changes**
   - `ANALYTICS_DEBUG` environment variable removed
   - Log file format changes from text to JSONL
   - **Mitigation**: Migration guide provided

5. **Learning Curve**
   - Developers must learn environment variable patterns
   - Understanding when to use each log level
   - **Mitigation**: Philosophy documentation and examples

### Neutral Consequences

1. **File Format Changes**
   - JSONL instead of text logs
   - Better for agents, requires tools for humans (jq)

2. **UV Workspace Required**
   - Repo-level pyproject.toml needed
   - Standard practice for modern Python monorepos

3. **Single Log File Strategy**
   - All logs in one file with rotation
   - Filtering required for isolation (grep, jq)

## Implementation Notes

### Affected Components

1. **New Library**: `/lib/python/agentic_logging/`
   - Create package with config, logger, formatters
   - Add tests (90%+ coverage required)
   - Write comprehensive README with philosophy

2. **Workspace Configuration**: `/pyproject.toml`
   - Define UV workspace members
   - Include agentic_logging as workspace member

3. **Analytics Service**: `services/analytics/`
   - Replace `logging.getLogger()` with `get_logger()`
   - Add session_id extraction from hook events
   - Remove `ANALYTICS_DEBUG` config field
   - Update documentation

4. **Hook Scripts**: `primitives/v1/hooks/`
   - Replace `print(..., file=sys.stderr)` with logger calls
   - Add session_id extraction
   - Keep JSON output to stdout (not logging)

### Migration Path

**Phase 1: Foundation**
- Create agentic_logging library
- Configure UV workspace
- Write comprehensive documentation

**Phase 2: Analytics Integration**
- Migrate analytics service
- Test with existing workflows
- Update analytics documentation

**Phase 3: Hooks Migration**
- Migrate hooks-collector (core)
- Migrate security hooks
- Test with Claude Code integration

**Phase 4: Validation**
- End-to-end testing
- Performance validation
- Documentation review

### Breaking Changes

1. **Environment Variable**: `ANALYTICS_DEBUG=true` → `LOG_LEVEL_ANALYTICS=DEBUG`
2. **Log Format**: Text logs → JSONL
3. **Log Location**: Service-specific → Centralized `./logs/agentic.jsonl`

### Configuration Migration

```bash
# OLD (analytics service)
export ANALYTICS_DEBUG=true
export ANALYTICS_OUTPUT_PATH=./analytics-events.jsonl

# NEW (centralized logging)
export LOG_LEVEL_ANALYTICS=DEBUG
export LOG_FILE=./logs/agentic.jsonl
```

## References

- [Python Logging HOWTO](https://docs.python.org/3/howto/logging.html) - Official documentation
- [Python Logging Cookbook](https://docs.python.org/3/howto/logging-cookbook.html) - Best practices
- [python-json-logger](https://github.com/madzak/python-json-logger) - JSON formatter library
- ADR-006: Middleware Hooks Architecture - Related context for hooks
- ADR-011: Analytics Middleware - Integration point for analytics
- `/docs/analytics-integration.md` - Current analytics logging approach
- Project Plan: `/PROJECT-PLAN_20251125_centralized-logging.md` - Implementation plan

---

**Review Status**: Ready for approval
**Implementation Status**: Not started (awaiting approval)
**Target Completion**: 2025-11-25 (1 day)

