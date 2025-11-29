# MISSION CONTROL — Agentic Primitives

## Purpose
A universal framework for building and deploying agentic primitives (prompts, tools, hooks) across multiple AI providers (Claude, OpenAI, Google). This project provides a CLI tool and specification system that enables standardized, versioned, and provider-agnostic agentic workflows with built-in analytics and middleware support.

**Vision (2026)**: This repo is the composable foundation for an **IDE-less agentic engineering system** where AI agents perform all coding work, enabling 100% observability and explicit rework detection.

## Current Milestone
**🚧 Pre-Execution: Merge & Branch**
1. Merge `feat/examples-002-observability` to main
2. Create new branch `feat/event-schema-consolidation`
3. Execute Event Schema Consolidation plan

### Upcoming Milestones
- **🚧 Event Schema Consolidation** - Define canonical event schemas in `agentic_analytics` library

### Previous Milestones
- **✅ Full Build System** - Build generates all 9 Claude Code event handlers + validators
- **✅ Audit Trail Enhancement** - Added full audit trail fields and security test scenarios
- **✅ Atomic Hook Architecture** - Replaced wrapper+impl pattern with atomic handlers + pure validators
- **✅ Observability Dashboard POC** - Example 002 with FastAPI + React dashboard

## Architecture / Structure Summary
- **CLI (Rust)**: Core command-line tool (`agentic-p`) in `/cli` with commands for init, build, validate, install, test, migrate
- **Specifications**: JSON schemas in `/specs/v1` defining metadata structures
- **Providers**: TWO-TIER structure:
  - `/providers/models/{anthropic,openai,google}` - LLM API providers (pricing, capabilities)
  - `/providers/agents/{claude-code,cursor,langgraph}` - Agent frameworks (hooks, tools, execution)
- **Primitives**: Versioned primitives in `/primitives/v1/hooks/` - handlers/ + validators/
- **Services**: Analytics service (Python) in `/services/analytics` with pluggable middleware pipeline
- **Libraries**: Python libs in `/lib/python/` (agentic_analytics, agentic_logging)
- **Examples**: Integration examples in `/examples/` demonstrating real-world usage
- **Build System**: Copies handlers + validators to `.claude/hooks/`

## Key Decisions
- **ADR-001 through ADR-011**: Foundation decisions
- **ADR-012**: Provider taxonomy - separate model providers from agent providers
- **ADR-013**: Hybrid hook architecture - universal collector (observability) + specialized hooks (control)
- **ADR-014**: Atomic Hook Architecture - handlers compose pure validators, inline analytics
- **ADR-015**: Parallel QA Workflows - Modular component-based CI with max parallelization
- **ADR-016**: Hook Event Correlation - `tool_use_id` as correlation key across agent/hook events

## Key Insights
- **Wrapper+Impl FAILED**: Python packaging issues made imports unreliable across subprocess boundaries
- **Atomic Design**: 3 handlers compose N validators, validators are pure functions
- **No Package Dependencies**: Hooks use Python stdlib only
- **Inline Analytics**: 6 lines of code per handler, not a package import
- **Agent-Centric Hooks**: Hook events defined by agent provider, not hook primitives
- **Security**: Dangerous commands blocked (rm -rf /, git add -A, .env files, SSH keys)
- **Model Pricing**: Loaded from `providers/models/` YAML configs for cost estimation
- **Full Audit Trail**: Every hook decision includes `audit.transcript_path` linking to Claude Code's conversation log
- **Event Schema Scatter**: Events currently defined in examples, need consolidation to library

## Strategic Direction

### This Repo (agentic-primitives)
1. **Event Schema Consolidation** (CURRENT) - Canonical events in `agentic_analytics`
2. **Hook Primitives** - Security validators, audit trail, analytics
3. **Build System** - Provider-specific artifact generation

### New Repo (agentic-engineering-system) - PLANNED
- Uses `agentic-primitives` as composable base
- Uses `event-sourcing-platform` for event store
- Tracks DORA metrics + Agent KPIs
- IDE-less agent orchestration

## Metrics Vision
| Category | Metrics |
|----------|---------|
| DORA | Deployment Frequency, Lead Time, Change Failure Rate, MTTR |
| Agent KPIs | Cognitive Efficiency, Cost Efficiency, Semantic Durability, Rework Token Ratio, Token Velocity, Semantic Yield |
| Milestone | Token Estimation Accuracy, Completion Time, Deliverable Rate |
| Workflow | Lead Time, Phase Efficiency, Artifact Reuse |

## Constraints
- Must maintain backward compatibility within released spec versions
- Provider APIs have different capabilities and limitations
- Analytics must be privacy-preserving and opt-in
- CLI must work across platforms (macOS, Linux, Windows)
- Build artifacts must be provider-specific and isolated
- Python projects use `uv` for package management (NEVER pip directly)
- **Hooks use Python stdlib only - no external package dependencies**

## Important Links / Files
- Codebase: `/Users/neural/Code/AgentParadise/agentic-primitives`
- **Plan (Local Refactor)**: `/PROJECT-PLAN_20251128_event-schema-consolidation.md`
- **Plan (New Repo)**: `/PROJECT-PLAN_20251128_agentic-engineering-system.md`
- Handler Templates: `/primitives/v1/hooks/handlers/`
- Validator Templates: `/primitives/v1/hooks/validators/`
- Example 001: `/examples/001-claude-agent-sdk-integration/`
- Example 002: `/examples/002-observability-dashboard/`
- Library: `/lib/python/agentic_analytics/`
- Model Configs: `/providers/models/anthropic/`
- ADRs: `/docs/adrs/`
- Event Sourcing Platform: `https://github.com/NeuralEmpowerment/event-sourcing-platform`

## Status Summary
✅ **Core Architecture** - All tests passing (324 Rust tests, 9 E2E hook tests)
✅ **CI/CD** - Parallelized QA workflows for Rust + Python validation
✅ **Build System** - Auto-discovers handlers/, generates settings.json for all 9 events
✅ **9 Event Handlers** - PreToolUse, PostToolUse, UserPromptSubmit, Stop, SubagentStop, SessionStart, SessionEnd, PreCompact, Notification
✅ **Example 000** - Updated with atomic hooks + audit trail
✅ **Example 001** - Claude Agent SDK with metrics collection + security scenarios
✅ **Example 002** - Observability Dashboard (FastAPI + React)
🚧 **Event Consolidation** - Moving event schemas from examples to library
📋 **New Repo Planned** - `agentic-engineering-system` architecture designed
