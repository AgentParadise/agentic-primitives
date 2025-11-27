# MISSION CONTROL — Agentic Primitives

## Purpose
A universal framework for building and deploying agentic primitives (prompts, tools, hooks) across multiple AI providers (Claude, OpenAI, Google). This project provides a CLI tool and specification system that enables standardized, versioned, and provider-agnostic agentic workflows with built-in analytics and middleware support.

## Current Milestone
**✅ Audit Trail Enhancement - COMPLETE** - Added full audit trail fields and security test scenarios.

### Previous Milestone
**✅ Atomic Hook Architecture - COMPLETE** - Replaced wrapper+impl pattern with atomic handlers + pure validators.

## Architecture / Structure Summary
- **CLI (Rust)**: Core command-line tool (`agentic-p`) in `/cli` with commands for init, build, validate, install, test, migrate
- **Specifications**: JSON schemas in `/specs/v1` defining metadata structures
- **Providers**: TWO-TIER structure:
  - `/providers/models/{anthropic,openai,google}` - LLM API providers (pricing, capabilities)
  - `/providers/agents/{claude-code,cursor,langgraph}` - Agent frameworks (hooks, tools, execution)
- **Primitives**: Versioned primitives in `/primitives/v1/hooks/` - **NEW: handlers/ + validators/**
- **Services**: Analytics service (Python) in `/services/analytics` with pluggable middleware pipeline
- **Libraries**: Python libs in `/lib/python/` (agentic_analytics, agentic_logging) - hooks do NOT depend on these
- **Examples**: Integration examples in `/examples/` demonstrating real-world usage
- **Build System**: Copies handlers + validators to `.claude/hooks/`

## Key Decisions
- **ADR-001 through ADR-011**: Foundation decisions
- **ADR-012**: Provider taxonomy - separate model providers from agent providers
- **ADR-013**: Hybrid hook architecture - universal collector (observability) + specialized hooks (control)
- **ADR-014**: **Atomic Hook Architecture** - handlers compose pure validators, inline analytics
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

## Constraints
- Must maintain backward compatibility within released spec versions (v1 may still be in alpha)
- Provider APIs have different capabilities and limitations
- Analytics must be privacy-preserving and opt-in
- CLI must work across platforms (macOS, Linux, Windows)
- Build artifacts must be provider-specific and isolated
- Python projects use `uv` for package management (NEVER pip directly)
- **Hooks use Python stdlib only - no external package dependencies**

## Important Links / Files
- Codebase: `/Users/codedev/Code/ai/agentic-primitives`
- Project Plan: `/PROJECT-PLAN_20251127_atomic-hook-architecture.md` (✅ COMPLETE)
- Handler Templates: `/primitives/v1/hooks/handlers/`
- Validator Templates: `/primitives/v1/hooks/validators/`
- Current Example: `/examples/001-claude-agent-sdk-integration/`
- Model Configs: `/providers/models/anthropic/`
- ADRs: `/docs/adrs/`

## Status Summary
✅ **Core Architecture** - All tests passing (324 Rust tests, 9 E2E hook tests)
✅ **CI/CD** - Parallelized QA workflows for Rust + Python validation
✅ **Example 000** - Updated with atomic hooks + audit trail
✅ **Example 001** - Updated with atomic hooks + analytics + security scenarios
✅ **ADR-014** - Rewritten for atomic hook architecture
✅ **ADR-016** - Hook event correlation with audit trail fields
✅ **Atomic Hook Refactor** - 9/9 milestones complete
✅ **Audit Trail Enhancement** - 5/5 milestones complete
