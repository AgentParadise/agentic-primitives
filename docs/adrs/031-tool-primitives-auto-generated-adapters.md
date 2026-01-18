---
title: "ADR-031: Tool Primitives with Auto-Generated Adapters"
status: proposed
created: 2026-01-13
updated: 2026-01-13
author: System Design
tags: [architecture, tools, mcp, simplification, v2]
---

# ADR-031: Tool Primitives with Auto-Generated Adapters

## Status

**Proposed**

- Created: 2026-01-13
- Updated: 2026-01-13
- Author(s): System Design
- Supersedes: None (introduces v2 architecture)
- Related: ADR-005 (Polyglot Implementations), ADR-007 (Generated Outputs)

## Context

### Current Complexity

The v1 agentic-primitives architecture has evolved to include:
- Complex build/transform pipeline (`agentic-p build --provider X`)
- Provider abstraction layers with multiple adapters
- Custom metadata format (`.meta.yaml` with BLAKE3 hashes, version tracking)
- Non-standard file naming (`<id>.prompt.v1.md`, `<id>.meta.yaml`)
- Manual adapter maintenance for each framework (Claude, LangChain, OpenAI)

While this provides powerful versioning and validation, it creates barriers:
1. **Complexity**: Users need to understand build steps, provider models, and custom formats
2. **Compatibility**: Not aligned with Claude Code's plugin standard (`.claude-plugin/plugin.json`)
3. **Maintenance burden**: Hand-written adapters for each framework
4. **Vendor lock-in risk**: Heavy investment in custom tooling

### Key Insights from Claude Code Documentation

After reviewing Claude Code's plugin system, we identified:
- Plugins use simple directory structures with ready-to-use files
- No build step required: `claude --plugin-dir ./my-plugin` just works
- Minimal metadata in `plugin.json` (name, version, description)
- Standard markdown files with frontmatter for commands/skills
- Distribution via GitHub repos as marketplaces

### Tool vs MCP Distinction

A critical philosophical insight emerged: **MCP is a protocol adapter, not the tool itself**.

Tools should be:
- **Pure functions/scripts**: Lightweight, portable implementations
- **Standalone executable**: `uv run tool.py` or direct import
- **Framework-agnostic**: No forced protocol overhead

MCP servers are:
- **Optional wrappers**: Only when context-heavy operations benefit from protocol
- **Generated on demand**: Not committed to repository
- **Protocol adapters**: One of many possible integrations (alongside LangChain, OpenAI, etc.)

This distinction prevents forcing context-heavy MCP overhead on simple operations while still supporting MCP when beneficial.

### Multi-Framework Requirement

While we want Claude Code alignment, we need true framework agnosticism:
- Claude Code plugins (primary use case)
- LangChain tools (for custom agents)
- OpenAI function calling (for GPT integration)
- Standalone CLI usage (for scripts/automation)

The solution must support all targets without vendor lock-in.

## Decision

We will adopt a **"Standard Tool Definition with Auto-Generated Adapters"** architecture for v2:

### Core Principles

1. **Tools are pure implementations** with standard YAML specifications
2. **Plugins are thin orchestration** using Claude Code's format
3. **Adapters are auto-generated** on demand from tool specs
4. **No committed adapter code** - generated to `build/` and gitignored
5. **FastMCP for Python MCP** - simple, decorator-based pattern

### Architecture Components

```
tools/
├── <tool-name>/
│   ├── tool.yaml           # ⭐ Standard specification (source of truth)
│   ├── impl.py             # Pure implementation
│   └── pyproject.toml      # Dependencies

plugins/                    # Claude Code plugins (standard format)
├── <plugin-name>/
│   ├── .claude-plugin/
│   │   └── plugin.json
│   ├── commands/
│   ├── skills/
│   └── .mcp.json           # References generated MCP servers

build/                      # Generated artifacts (gitignored)
└── adapters/
    ├── mcp/                # FastMCP servers
    ├── langchain/          # LangChain wrappers
    └── openai/             # OpenAI function schemas
```

### Standard Tool Specification

Tools define their interface in `tool.yaml`:

```yaml
id: example-tool
version: "1.0.0"
name: Example Tool
description: What this tool does

interface:
  function: main_function
  parameters:
    param1:
      type: string
      required: true
      description: Parameter description
  returns:
    type: object
    properties:
      result: { type: string }

implementation:
  language: python
  runtime: uv
  entry_point: impl.py
  function: main_function
  requires:
    python: ">=3.11"
    packages:
      - dep1>=1.0.0

generators:
  mcp:
    framework: fastmcp
    server_name: example-tool
  langchain:
    tool_type: StructuredTool
  openai:
    function_name: example_tool
```

### Auto-Generation Workflow

```bash
# Generate MCP adapter on demand
agentic-p gen-adapter example-tool --target mcp
# → build/adapters/mcp/example_tool_server.py (FastMCP)

# Generate LangChain wrapper
agentic-p gen-adapter example-tool --target langchain
# → build/adapters/langchain/example_tool.py

# Or generate all at install time
agentic-p install plugin my-plugin --target claude
# → Auto-generates needed adapters, updates .mcp.json
```

### Plugin Structure (Claude Code Standard)

Plugins follow Claude Code's format exactly:

```
my-plugin/
├── .claude-plugin/
│   └── plugin.json         # Standard Claude metadata
├── commands/
│   └── review.md           # Standard markdown commands
├── skills/
│   └── testing-expert/
│       └── SKILL.md        # Standard skill format
└── .mcp.json               # Points to generated MCP servers (optional)
```

## Alternatives Considered

### Alternative 1: Full Claude Code Alignment (Simplest)

**Description**: Restructure entire repo as Claude Code plugins, abandon custom tooling.

**Pros**:
- Zero build step
- Maximum Claude compatibility
- Simplest for users
- GitHub-based distribution built-in

**Cons**:
- Lose versioning sophistication
- Lose provider abstraction
- No multi-framework support
- Abandon existing CLI investment

**Reason for rejection**: Too limiting for multi-framework goals and tool management needs.

---

### Alternative 2: Universal Primitive Format (UPF)

**Description**: Define our own minimal format that's a superset of all frameworks.

**Pros**:
- True framework agnosticism
- Clean abstraction
- Can add targets without changing primitives

**Cons**:
- Inventing yet another format
- Not Claude-native (still requires builds)
- Over-engineering risk
- Users must learn custom format

**Reason for rejection**: Adds complexity rather than reducing it; not aligned with existing standards.

---

### Alternative 3: Primitive Packages with Target Manifests

**Description**: Each primitive as npm-style package with target-specific subdirectories.

**Pros**:
- Explicit multi-framework support
- Clear separation (targets/ vs src/)
- Framework-specific optimizations possible

**Cons**:
- Code duplication across targets/
- Package management complexity
- Maintenance burden for each target
- Still requires build orchestration

**Reason for rejection**: Doesn't solve the fundamental problem of hand-written adapters.

---

### Alternative 4: MCP-First Architecture

**Description**: Make everything MCP servers, use MCP as universal protocol.

**Pros**:
- MCP is model-agnostic
- Rich ecosystem emerging
- Protocol-based (not vendor-specific)

**Cons**:
- Forces MCP overhead on simple tools
- Server processes for everything (heavy)
- MCP doesn't have "skills" concept
- Over-engineering for lightweight operations

**Reason for rejection**: Violates the "tools are pure functions" principle; MCP should be optional.

---

### Alternative 5: Marketplace + Registry Hybrid

**Description**: Be a curated marketplace wrapping primitives in whatever format they need.

**Pros**:
- Maximum flexibility
- No forced abstractions
- Registry provides discoverability

**Cons**:
- Code duplication (no DRY)
- High maintenance burden
- No consistency guarantees
- Doesn't leverage automation

**Reason for rejection**: Doesn't utilize code generation to reduce maintenance.

## Consequences

### Positive Consequences

- **Dramatically simpler**: Single source of truth (tool.yaml), zero committed adapter code
- **Claude Code native**: Plugins work with `claude --plugin-dir` out of the box
- **Framework agnostic**: Generate adapters for any target (MCP, LangChain, OpenAI, etc.)
- **Lower maintenance**: Adapters regenerated from spec, not hand-maintained
- **Lightweight tools**: No forced MCP overhead; tools are pure functions
- **Better DX**: Standard formats everyone understands (plugin.json, tool.yaml)
- **FastMCP integration**: Modern, Pythonic MCP server generation
- **Extensible**: Add new adapter generators without touching tools

### Negative Consequences

- **Migration effort**: v1 → v2 migration for existing primitives
- **Generator complexity**: CLI must implement multiple adapter generators
- **Build step remains**: Still need `gen-adapter` for MCP/LangChain (but simpler)
- **Schema maintenance**: tool.yaml schema evolution across versions
- **Loss of BLAKE3 hashing**: Simpler versioning (semantic only)
- **Type safety**: Generated code quality depends on generator implementation

### Neutral Consequences

- **Different file structure**: tools/ and plugins/ separation
- **JSON schema validation**: Shifts from custom validators to JSON schema
- **CLI command changes**: New commands (gen-adapter, validate-tool)
- **Documentation updates**: All guides need updating for v2

## Implementation Notes

### Phase 1: Foundation (Week 1-2)

1. **Create tool.yaml JSON Schema**
   - Define complete specification format
   - Version as v1.0.0 for stability
   - Document all fields with examples

2. **Implement Generator Framework**
   - Abstract generator trait in Rust CLI
   - Plugin architecture for new generators
   - Template rendering engine

3. **Build FastMCP Generator**
   - Python MCP server generator
   - Uses FastMCP decorator pattern
   - Handles type conversions and docstrings

### Phase 2: Multi-Framework Support (Week 3-4)

4. **Implement Additional Generators**
   - LangChain tool wrapper generator
   - OpenAI function schema generator
   - Add generator registry

5. **Plugin Scaffolding**
   - `agentic-p new plugin` command
   - Claude Code .claude-plugin/ structure
   - Auto-generate plugin.json

6. **Validation Layer**
   - JSON schema validation for tool.yaml
   - Runtime tests for generated adapters
   - Integration test framework

### Phase 3: Migration Path (Week 5-6)

7. **V1 → V2 Migration Tool**
   - Convert .meta.yaml → tool.yaml
   - Restructure primitives/ → tools/ + plugins/
   - Preserve git history

8. **Documentation**
   - Update all guides for v2
   - Migration guide for v1 users
   - Generator development guide

9. **Backwards Compatibility**
   - Optional v1 support mode
   - Gradual migration strategy
   - Deprecation timeline (6 months)

### Breaking Changes

- File structure: `primitives/v1/` → `tools/` + `plugins/`
- Metadata format: `.meta.yaml` → `tool.yaml`
- CLI commands: `build/install` → `gen-adapter/validate-tool`
- Build output: `build/<provider>/` → `build/adapters/<target>/`
- No more BLAKE3 hashes (semantic versioning only)

### Migration Strategy

**For Tool Authors**:
```bash
# Migrate existing tool
agentic-p migrate tool primitives/v1/tools/scrape/firecrawl-scraper

# Creates: tools/firecrawl-scraper/tool.yaml
```

**For Plugin Authors**:
```bash
# Create new plugin from existing commands
agentic-p migrate plugin primitives/v1/commands/qa/

# Creates: plugins/qa-suite/ (Claude Code format)
```

**For Users**:
- V1 still works until deprecation (6 months)
- V2 opt-in via `agentic-p config set version v2`
- Side-by-side support during transition

### New Directory Structure

```
agentic-primitives/
├── tools/                      # Pure tool implementations
│   ├── firecrawl-scraper/
│   │   ├── tool.yaml
│   │   ├── firecrawl_scraper.py
│   │   └── pyproject.toml
│   └── docker-isolation/
│       ├── tool.yaml
│       ├── isolation.py
│       └── pyproject.toml
│
├── plugins/                    # Claude Code plugins
│   ├── qa-suite/
│   │   ├── .claude-plugin/
│   │   ├── commands/
│   │   ├── skills/
│   │   └── .mcp.json
│   └── devops-tools/
│       └── .claude-plugin/
│
├── schemas/                    # JSON schemas
│   ├── tool-spec.v1.json
│   └── plugin-manifest.json
│
├── cli/                        # Rust CLI (generators)
│   └── src/
│       └── generators/
│           ├── mcp.rs
│           ├── langchain.rs
│           └── openai.rs
│
├── build/                      # Generated (gitignored)
│   └── adapters/
│
└── marketplace.json            # Plugin marketplace manifest
```

## References

- [Claude Code Plugin Documentation](../deps/unknown/claude-code@latest-20260113.md) - Official plugin format
- [FastMCP Quickstart](../deps/python/fastmcp@latest-20260113.md) - MCP server generation pattern
- [Model Context Protocol Specification](https://spec.modelcontextprotocol.io/) - MCP protocol details
- ADR-005: Polyglot Implementations - Tool implementation flexibility
- ADR-007: Generated Provider Outputs - Build-time generation precedent
- ADR-020: Agentic Prompt Taxonomy - Primitive type definitions
- ADR-021: Primitives Directory Structure - Current v1 structure

---

## Additional Notes

### Why FastMCP?

FastMCP provides the ideal pattern for auto-generated MCP servers:
- Decorator-based (`@mcp.tool()`)
- Type hints → automatic schema extraction
- Docstrings → tool descriptions
- Minimal boilerplate
- Entry point: `fastmcp run server.py:mcp`

This makes generation trivial: read tool.yaml, generate decorated wrapper, done.

### Generator Extensibility

The generator framework supports community contributions:
```bash
# Install community generator
agentic-p add-generator crewai --from github.com/user/crewai-generator

# Use it
agentic-p gen-adapter my-tool --target crewai
```

### Tool Distribution

Tools can be:
1. **In-repo**: Bundled with agentic-primitives
2. **External**: Reference GitHub repos in tool.yaml
3. **Local**: Development/testing with `--tool-dir`

### Version Evolution

tool.yaml schema uses semantic versioning:
- `schema_version: "1.0.0"` in each tool.yaml
- CLI supports multiple schema versions
- Migration tools for schema upgrades
