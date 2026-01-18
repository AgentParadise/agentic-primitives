# MISSION CONTROL — Agentic Primitives

## Purpose
A universal framework for building and deploying agentic primitives (prompts, tools, hooks) across multiple AI providers (Claude, OpenAI, Google). This project provides a CLI tool and specification system that enables standardized, versioned, and provider-agnostic agentic workflows with built-in analytics and middleware support.

**Vision (2026)**: This repo is the composable foundation for an **IDE-less agentic engineering system** where AI agents perform all coding work, enabling 100% observability and explicit rework detection.

## Current Milestone (v2-simplification worktree)
**✅ V2 Architecture Simplification - Phase 1.5 Complete**

**✅ Milestone 1.0: CLI Restructure** - COMPLETE
- Separated CLI into `cli/v1/` (maintenance) and `cli/v2/` (active)
- V1 binary: `agentic-p-v1`, V2 binary: `agentic-p`
- Clean separation for independent evolution

**✅ Milestone 1.1: Source Structure** - COMPLETE
- Created `primitives/v2/` with simplified flat structure
- Migrated 4 example primitives (2 commands, 1 skill, 1 tool)
- Category organization preserved, unnecessary nesting removed

**✅ Milestone 1.2: Build System** - COMPLETE
- V2 discovery logic (`build_v2.rs`)
- V2 transformer (`claude_v2.rs`)
- `--primitives-version v2` CLI flag
- Successfully builds to `build/claude/` with correct structure

**✅ Milestone 1.5.1: Schemas & Validation** - COMPLETE
- JSON schemas for command and skill frontmatter
- `agentic-p validate` command with `--all` flag
- Automatic validation during build
- All primitives pass validation

**✅ Milestone 1.5.2: CLI Generators** - COMPLETE
- `agentic-p new command/skill/tool` commands
- Handlebars templates for all primitive types
- Interactive mode with dialoguer prompts
- Non-interactive mode with flags
- Automatic validation after generation

**✅ Milestone 1.5.3: Documentation** - COMPLETE
- `docs/v2/` with comprehensive V2 documentation
- Quick start guide (5-minute tutorial)
- Authoring guides for commands, skills, tools
- CLI reference, frontmatter reference
- Migration guide from V1 to V2

### Upcoming (Phase 2)
- **Granular Install Commands** - `install command <name>`, `install skill <name>`
- **MCP Adapter Generation** - Auto-generate FastMCP servers from tool.yaml
- **Full Migration** - Convert remaining high-value primitives to v2
- **Testing** - Integration tests for v2 build system

### Main Branch Milestones (completed in main, not in this worktree)
- **✅ Subagent Observability** - EventParser tracks subagent lifecycle
- **✅ Full Build System** - All 9 Claude Code event handlers
- **✅ Atomic Hook Architecture** - Handlers + pure validators

## Architecture / Structure Summary

### V2 Architecture (This Worktree)
- **Source Structure** (NEW):
  - `primitives/v2/commands/{category}/{name}.md` - Single file per command with frontmatter
  - `primitives/v2/skills/{category}/{name}.md` - Single file per skill with frontmatter
  - `primitives/v2/tools/{category}/{name}/` - Directory with tool.yaml + impl.py

- **Build System** (ENHANCED):
  - `cli/src/commands/build_v2.rs` - V2 discovery logic
  - `cli/src/providers/claude_v2.rs` - V2 transformer (frontmatter parsing)
  - `--primitives-version v2` flag routes to v2 logic
  - Defaults to v1 (backward compatible)

- **Output Structure** (PRESERVED):
  - `build/claude/commands/{category}/{name}.md` - Same as v1
  - `build/claude/skills/{name}/SKILL.md` - Same as v1 (Claude Code format)
  - `build/claude/tools/{category}/{name}/` - Copied with tool.yaml

### V1 Architecture (Unchanged)
- **CLI (Rust)**: Core command-line tool (`agentic-p`) in `/cli`
- **Specifications**: JSON schemas in `/specs/v1` + `tool-spec.v1.json` (NEW)
- **Primitives V1**: `/primitives/v1/` - Complex nested structure with .meta.yaml files
- **Providers**: Model configs and agent frameworks
- **Libraries**: Python libs in `/lib/python/` (STABLE - not refactored)
- **Services**: Analytics service in `/services/analytics`

## Key Decisions

### V2 Simplification (This Worktree)
- **V2 Structure**: Flat `primitives/v2/` with categories but no extra nesting
- **No Per-File Versioning**: Git tags for repo version; removed BLAKE3 hashing
- **Frontmatter Only**: Simple YAML frontmatter in markdown; no .meta.yaml files
- **Tool Specification**: JSON Schema (`tool-spec.v1.json`) for tool.yaml validation
- **Build Modes**: `--primitives-version` flag switches v1/v2; defaults to v1
- **Backward Compatible**: V2 output structure matches v1 (commands/, skills/, tools/)
- **Category Preserved**: Keep `{category}/` for organization despite flattening

### Main Branch ADRs (Historical)
- **ADR-001 through ADR-011**: Foundation decisions
- **ADR-012**: Provider taxonomy
- **ADR-014**: Atomic Hook Architecture
- **ADR-015**: Parallel QA Workflows
- **ADR-016**: Hook Event Correlation
- **ADR-031**: Tool Primitives with Auto-Generated Adapters (V2 FOUNDATION)

## Key Insights (V2 Simplification)

### V2-Specific Learnings
- **Frontmatter Parsing**: YAML special characters (square brackets) must be quoted in frontmatter
- **Category Preservation Important**: User feedback confirmed categories should be kept despite flattening
- **Backward Compatible Output**: V2 must generate same `build/claude/` structure as v1 for downstream tools
- **Python Import Stability Critical**: `lib/python/` packages unchanged; imports remain functional
- **Tool Specification Schema**: JSON Schema validation enables auto-generation and IDE autocomplete
- **No Per-File Versioning**: Git tags handle repo versioning; removed BLAKE3 complexity
- **Build Mode Switching**: `--primitives-version` flag allows v1/v2 coexistence during migration
- **Manifest Needs Refinement**: Path format inconsistencies (absolute vs relative) to be fixed

### Main Branch Insights (Historical Context)
- **Wrapper+Impl FAILED**: Python packaging issues in hook architecture
- **Atomic Design**: Handlers compose validators as pure functions
- **No Package Dependencies**: Hooks use Python stdlib only
- **Agent-Centric Hooks**: Events defined by agent provider
- **Subagent Correlation**: Use `parent_tool_use_id` for tracking

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
- Library (Analytics): `/lib/python/agentic_analytics/`
- Library (Isolation): `/lib/python/agentic_isolation/`
- Playground/Eval: `/playground/`
- Model Configs: `/providers/models/anthropic/`
- ADRs: `/docs/adrs/`
- Event Sourcing Platform: `https://github.com/NeuralEmpowerment/event-sourcing-platform`

## Status Summary (v2-simplification worktree)

### Phase 1: Foundation (Complete)
✅ **Milestone 1.1: Source Structure** - `primitives/v2/` with flat, atomic primitives
✅ **Milestone 1.2: Build System** - V2 discovery + transformation logic working
✅ **4 V2 Primitives** - 2 commands, 1 skill, 1 tool migrated and building
✅ **Python Imports** - Verified `lib/python/` packages unchanged and functional
✅ **Backward Compatible** - Build output matches v1 structure (`build/claude/`)

### Phase 2: Completion (Pending)
📋 **Milestone 1.3: Output Compatibility** - Fix manifest paths, test with Claude Code
📋 **MCP Adapter Generation** - Auto-generate FastMCP servers from tool.yaml
📋 **V2 CLI Generators** - Commands to create new v2 primitives
📋 **Documentation** - ADR-032, migration guide, updated architecture docs
📋 **Full Migration** - Convert remaining high-value primitives to v2

### Technical Debt
⚠️ **Manifest Inconsistencies** - Mix of absolute/relative paths in `.agentic-manifest.yaml`
⚠️ **No Install Logic** - Currently just copies; needs skip/force/interactive modes
⚠️ **No Adapter Generation** - Tool.yaml exists but adapters not yet auto-generated
⚠️ **Limited Test Coverage** - Need integration tests for v2 build system

### Main Branch Status (Not in This Worktree)
✅ All core architecture features from main branch remain intact
✅ 324 Rust tests, 9 E2E hook tests passing
✅ CI/CD workflows, subagent observability complete
