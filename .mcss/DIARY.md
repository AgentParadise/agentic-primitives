# SESSION LOG — Agentic Primitives

---

## 2026-01-06 — Subagent Observability & Eval Library ✅ COMPLETE

### Objective
Enable observability for subagent lifecycle (start/stop/duration/tools) and create a lightweight eval library using the playground.

### What Was Built

#### 1. Model Alias Support
- Version-agnostic aliases: `claude-haiku` → `claude-haiku-4-5-20251001`
- Created `playground/src/models.py` with resolver
- Supports 3 formats: alias, model ID, full API name
- 12 tests passing

#### 2. Subagent Event Types
- Added `SUBAGENT_STARTED` and `SUBAGENT_STOPPED` to `EventType` enum
- Extended `ObservabilityEvent` with `parent_tool_use_id`, `agent_name`, `duration_ms`
- Extended `SessionSummary` with `subagent_count`, `subagent_names`, `tools_by_subagent`

#### 3. EventParser Subagent Tracking
- Detects `tool_use.name == "Task"` as subagent start
- Tracks concurrent subagents via dict keyed by `tool_use_id`
- Correlates tool events using `parent_tool_use_id`
- Emits `SUBAGENT_STOPPED` on Task tool_result
- 15 tests passing (9 existing + 6 new)

#### 4. Hook Configuration
- Added `subagent-stop` to `manifest.yaml` handlers
- Updated `entrypoint.sh` with `Stop` and `SubagentStop` hooks
- Rebuilt workspace image with new hooks

#### 5. Eval Library
- Created `playground/scenarios/subagent-concurrent.yaml` - Tests concurrent subagents
- Created `playground/scenarios/quick-haiku.yaml` - Fast iteration with Haiku
- Created `playground/prompts/subagent-test.md` - 3-subagent test prompt

#### 6. Justfile Recipes (Cross-Platform)
- `just eval <scenario> <task>` - Run any scenario
- `just eval-subagent` - Run subagent test
- `just eval-quick <task>` - Fast Haiku test
- `just eval-list` - List scenarios
- `just eval-test` - Run playground tests

### Integration Verified
```
🚀 STARTED: "Run date command" (active: 1)
🚀 STARTED: "Run whoami command" (active: 2)
🚀 STARTED: "Run pwd command" (active: 3)   ← 3 concurrent!
🛑 STOPPED: "Run date command" (active: 2)
🛑 STOPPED: "Run pwd command" (active: 1)
🛑 STOPPED: "Run whoami command" (active: 0)

SESSION SUMMARY
Total subagents: 3
Names: ['Run date command', 'Run pwd command', 'Run whoami command']
```

### Files Changed
| Category | Files |
|----------|-------|
| Model Aliases | `providers/models/anthropic/config.yaml`, `playground/src/models.py` |
| Event Types | `agentic_isolation/.../types.py` |
| EventParser | `agentic_isolation/.../event_parser.py` |
| Tests | `playground/tests/test_models.py`, `agentic_isolation/.../tests/test_event_parser.py` |
| Hooks | `manifest.yaml`, `entrypoint.sh` |
| Scenarios | `playground/scenarios/`, `playground/prompts/` |
| Justfile | `justfile` (eval recipes) |

### Branch
`feat/subagent-observability` - Ready for commit

---

## 2025-11-28 — Strategic Planning Session

### Objectives
1. Define canonical event schemas in `agentic_analytics` library
2. Plan the `agentic-engineering-system` repo architecture

### Context
User's 2026 vision: **IDE-less agentic engineering system** where AI agents perform all coding work. This enables:
- 100% observability (all actions are agent actions)
- Explicit rework detection (no hidden human edits)
- DORA metrics + Agent KPIs tracking

### Research Findings
Events are currently scattered across:
| Location | Events Defined |
|----------|----------------|
| `examples/001/src/metrics.py` | `ToolCallMetric`, `InteractionMetrics`, `SessionMetrics` |
| `examples/002/backend/src/models/events.py` | `AgentEvent`, `HookDecisionEvent`, `ToolExecutionEvent`, `SessionEvent` |
| `services/analytics/src/models/events.py` | `NormalizedEvent`, various context models |
| `lib/python/agentic_analytics/models.py` | `HookDecision` only |

### Problem
- No canonical event schemas in the library
- Examples define their own events → duplication
- New consumers must copy definitions
- Schema drift between examples

### Solution: Two Project Plans

#### Plan 1: Event Schema Consolidation (agentic-primitives)
`PROJECT-PLAN_20251128_event-schema-consolidation.md`
- Define `SessionStarted`, `TokensUsed`, `ToolCalled`, `SessionEnded` in library
- Extend `HookDecision` with `AuditContext`
- Refactor Examples 001 and 002 to use library
- 4 milestones, ~5-8 hours total

#### Plan 2: Agentic Engineering System (new repo)
`PROJECT-PLAN_20251128_agentic-engineering-system.md`

**Architecture:**
- Uses `event-sourcing-platform` (Rust event store + TypeScript SDK)
- Uses `agentic-primitives` (canonical event schemas)

**Domain Aggregates:**
- `AgentSessionAggregate` - Tracks agent sessions
- `MilestoneAggregate` - Tracks logical work units
- `WorkflowAggregate` - Tracks entire projects

**Event Collectors:**
- Agent events (from `.agentic/analytics/events.jsonl`)
- Git events (from git hooks)
- CI events (from GitHub Actions webhooks)

**Projections:**
- DORA metrics (Deployment Frequency, Lead Time, Change Failure Rate, MTTR)
- Agent KPIs (Cognitive Efficiency, Semantic Durability, Rework Token Ratio, etc.)
- Milestone performance (Token Estimation Accuracy, Completion Time)

**Timeline:** 6-week phased implementation

### Pre-Execution Steps
Before starting the local refactor:
1. Merge `feat/examples-002-observability` to `main`
2. Create new branch `feat/event-schema-consolidation`
3. Enter EXECUTE mode

### Next Action
Approve merge and branch creation, then execute Plan 1.

---

## 2025-11-27 (Evening) — Full Build System ✅ COMPLETE

### Objective
Fix build system to auto-discover handlers and generate all 9 Claude Code event handlers.

### Problem
- Build said "No primitives found" because it looked for `.hook.yaml` files
- Old architecture had YAML metadata per hook, new atomic architecture doesn't
- Only 3 handlers existed (PreToolUse, PostToolUse, UserPromptSubmit)
- Claude Code supports 9 hook events

### Solution Implemented
1. **Build Discovery** - Modified `has_metadata_file()` and `detect_primitive_kind()` to recognize `handlers/` directory as atomic hooks
2. **Path Fix** - `transform_hook()` now correctly uses source path when `handlers/` exists
3. **6 New Handlers** - Added missing event handlers:
   - `stop.py` - Conversation stop
   - `subagent-stop.py` - Subagent completion
   - `session-start.py` - Session lifecycle
   - `session-end.py` - Session lifecycle
   - `pre-compact.py` - Context compaction
   - `notification.py` - Various notifications
4. **settings.json** - Generates all 9 events with correct handler paths

### Build Output
```
15 files:
- 9 handlers
- 5 validators
- 1 settings.json
- 0 .impl files ✅
```

### Test Results
- ✅ All Rust tests passing
- ✅ Python lint passing
- ✅ Build generates complete hooks

---

## 2025-11-27 (Afternoon) — Audit Trail Enhancement ✅ COMPLETE

### Objective
Add full audit trail to hook analytics so every decision can be traced back to the original Claude Code conversation.

### Problem
Hook decisions were logging basic correlation (`tool_use_id`, `session_id`) but missing:
- Which Claude hook event triggered the decision
- Link to the full conversation log
- Working directory and permission context

### Solution Implemented
Added fields to all handler analytics:

| Field | Purpose |
|-------|---------|
| `hook_event` | Claude's hook event type (PreToolUse, PostToolUse, etc.) |
| `tool_input_preview` | What was the actual tool input |
| `audit.transcript_path` | Direct link to Claude Code's conversation JSONL |
| `audit.cwd` | Working directory context |
| `audit.permission_mode` | Security mode (default, plan, bypassPermissions) |

### Security Test Scenarios Added
- `write-env-file` → blocks .env files
- `read-etc-passwd` → blocks /etc/passwd
- `bash-git-add-all` → blocks git add -A
- `pii-in-prompt` → blocks SSN in prompts

### Test Results
- ✅ 324 Rust CLI tests passing
- ✅ 9 E2E hook tests passing
- ✅ All analytics events include new fields

---

## 2025-11-27 (Morning) — Atomic Hook Architecture ✅ COMPLETE

### Objective
Replace the failing wrapper+impl pattern with a simpler, more reliable atomic architecture.

### Problem (Identified Previous Session)
Hooks weren't writing to `.agentic/analytics/events.jsonl` due to Python import issues:
- `agentic_analytics` import failed in subprocess context
- Different Python environments in shell vs subprocess
- The wrapper+impl pattern created import complexity

### Solution Implemented
**Atomic Hook Architecture** with handlers + validators:

**Handlers** (3 files):
- `pre-tool-use.py` - Routes PreToolUse to validators, logs decisions
- `post-tool-use.py` - Logs PostToolUse events
- `user-prompt.py` - Routes UserPromptSubmit to PII validator

**Validators** (pure functions):
- `security/bash.py` - Blocks dangerous shell commands
- `security/file.py` - Blocks writes to sensitive files
- `prompt/pii.py` - Detects SSN, credit cards, etc.

### Key Principles
- **No external package dependencies** - stdlib only
- **Inline analytics** - 6 lines per handler, not a package import
- **Pure validators** - input → validation → output, nothing else
- **Composable** - handlers mix-and-match validators via TOOL_VALIDATORS map

---

## 2025-11-26 (Afternoon) — Hook Event Correlation (ADR-016) ✅ DESIGNED

### Objective
Implement provider-agnostic correlation between agent events and hook events.

### Solution
Use `tool_use_id` (provided by Claude) as correlation key:
- Agent wrapper includes it in `tool_call` events
- Hooks include it in `hook_decision` events
- Analysis joins by this key

### Created
- ADR-016: Provider-Agnostic Hook Event Correlation
- Updated `HookDecision` model with `tool_use_id` field

---

## 2025-11-26 (Morning) — 001-claude-agent-sdk-integration ✅ COMPLETE

### Objective
Build comprehensive Claude Agent SDK example with real prompts, metrics, cost estimation.

### All 9 Milestones Completed
1. Project scaffold with uv
2. Model config loader (pricing from YAML)
3. Metrics collection (SessionMetrics, JSONL output)
4. Instrumented agent wrapper
5. Security hooks (copied from 000)
6. Test scenarios (7 scenarios)
7. Main entry point (CLI)
8. Demo & docs
9. Cleanup & lint

**Committed as:** `7db9a03` - feat(examples): add 001-claude-agent-sdk-integration example

---

## Previous Sessions

### 2025-11-26 — CI/CD Workflows (ADR-015)
- Completed parallel QA workflows
- 46/46 tests passing

### 2025-11-18 — Analytics Integration
- Built agentic_analytics library
- Self-logging hooks pattern (now replaced with atomic hooks)

---

*This log follows RIPER-5 methodology with QA checkpoints at each milestone.*
