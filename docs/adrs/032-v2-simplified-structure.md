---
title: "ADR-032: V2 Simplified Structure"
status: accepted
created: 2026-01-14
updated: 2026-01-14
author: System Implementation
tags: [architecture, v2, simplification, implementation]
---

# ADR-032: V2 Simplified Structure

## Status

**Accepted** - Implemented in `v2-simplification` worktree

- Created: 2026-01-14
- Updated: 2026-01-14
- Author(s): System Implementation
- Supersedes: ADR-021 (Primitives Directory Structure)
- Related: ADR-031 (Tool Primitives with Auto-Generated Adapters), ADR-019 (File Naming Convention)

## Context

### The V1 Complexity Problem

The v1 primitives architecture, while powerful, created significant friction:

```
primitives/v1/
├── commands/
│   └── qa/
│       └── review/
│           ├── review.prompt.v1.md     ← Deep nesting
│           └── review.meta.yaml         ← Separate metadata file
├── skills/
│   └── testing/
│       └── testing-expert/
│           ├── testing-expert.prompt.v1.md
│           └── testing-expert.meta.yaml
└── tools/
    └── scrape/
        └── firecrawl-scraper/
            ├── firecrawl-scraper.tool.yaml
            ├── firecrawl_scraper.py
            └── firecrawl-scraper.meta.yaml
```

**Problems:**
1. **3-4 levels of nesting** for a single primitive
2. **Separate metadata files** (`.meta.yaml`) with BLAKE3 hashes, version tracking
3. **Non-standard naming** (`<id>.prompt.v1.md`) requires explanation
4. **Per-file versioning** adds complexity without clear value (git already tracks versions)
5. **Manual adapters** for each framework (FastMCP, LangChain, OpenAI)

### Design Goals for V2

1. **Flat structure** - Minimize nesting while preserving organization
2. **Single-file primitives** - Metadata in frontmatter, not separate files
3. **Standard naming** - `{name}.md` for commands/skills, familiar patterns
4. **Git-based versioning** - Repo tags instead of per-file hashes
5. **Auto-generated adapters** - From standard `tool.yaml` specification
6. **Claude Code native** - Works directly with `claude --plugin-dir`
7. **Backward compatible** - Build output structure unchanged

## Decision

### V2 Source Structure

```
primitives/v2/
├── commands/
│   ├── {category}/
│   │   └── {name}.md              ← Single file with frontmatter
│   └── qa/
│       └── review.md
├── skills/
│   ├── {category}/
│   │   └── {name}.md              ← Single file with frontmatter
│   └── testing/
│       └── testing-expert.md
└── tools/
    ├── {category}/
    │   └── {name}/                ← Directory with tool.yaml
    │       ├── tool.yaml          ← Standard spec (tool-spec.v1.json)
    │       ├── impl.py            ← Implementation
    │       ├── pyproject.toml     ← Dependencies
    │       └── README.md
    └── scrape/
        └── firecrawl-scraper/
            ├── tool.yaml
            ├── impl.py
            ├── pyproject.toml
            └── README.md
```

### Key Architectural Decisions

#### 1. Category Preservation

**Decision:** Keep `{category}/` directories despite flattening

**Rationale:**
- User feedback confirmed categories provide valuable organization
- Balance between flat structure and discoverability
- Examples: `qa/`, `devops/`, `testing/`, `scrape/`

**Structure:**
- V1: `primitives/v1/commands/qa/review/review.prompt.v1.md` (4 levels)
- V2: `primitives/v2/commands/qa/review.md` (3 levels, simpler naming)

#### 2. Frontmatter-Only Metadata

**Decision:** Embed metadata in YAML frontmatter, remove `.meta.yaml` files

**Example:**
```markdown
---
description: Review implementation against project plan and verify completeness
argument-hint: <path-to-project-plan.md>
model: sonnet
allowed-tools: Read, Grep, Glob, Bash
---

# Review Command

[Content here...]
```

**Removed from V1:**
- `id`, `kind`, `category`, `domain` (derivable from file path)
- `versions` array with BLAKE3 hashes (git tracks this)
- `default_version` (no per-file versioning)
- `context_usage`, `defaults`, `tags` (optional, rarely used)

**Kept:**
- `description` - Core documentation
- `model` - Default model preference
- `allowed-tools` - Security constraint
- `argument-hint` - User guidance

#### 3. Tool Specification Schema

**Decision:** Standardize on `tool.yaml` with JSON Schema validation (`tool-spec.v1.json`)

**Schema Structure:**
```yaml
schema_version: "1.0.0"
id: tool-name
version: "1.0.0"
name: Human Readable Name
description: What this tool does

interface:          ← Function signature
  function: name
  parameters: {...}
  returns: {...}

implementation:     ← How to execute it
  language: python
  runtime: uv
  entry_point: impl.py
  function: main
  requires: {...}

execution:          ← Runtime constraints
  timeout_seconds: 60
  requires_network: false
  requires_filesystem: true

generators:         ← Auto-generate adapters
  mcp:
    framework: fastmcp
  langchain:
    tool_type: StructuredTool
  openai:
    function_name: my_tool
```

**Benefits:**
- Single source of truth for tool interface
- JSON Schema validation ensures correctness
- Generator hints enable automatic adapter creation
- IDE autocomplete for tool.yaml authoring

#### 4. Build System v2

**Decision:** Add `--primitives-version v2` flag, preserve v1 by default

**Implementation:**
- `cli/src/commands/build_v2.rs` - V2 discovery logic
- `cli/src/providers/claude_v2.rs` - V2 transformer (frontmatter parsing)
- Default: `--primitives-version v1` (backward compatible)
- Switch: `--primitives-version v2` for new structure

**Discovery Logic:**
```rust
// V2 discovers:
// - primitives/v2/commands/{category}/{name}.md (markdown with frontmatter)
// - primitives/v2/skills/{category}/{name}.md (markdown with frontmatter)
// - primitives/v2/tools/{category}/{name}/ (directory with tool.yaml)
```

**Transformation:**
- Commands: Parse frontmatter, copy to `build/claude/commands/{category}/{name}.md`
- Skills: Copy to `build/claude/skills/{name}/SKILL.md` (Claude Code format)
- Tools: Copy directory to `build/claude/tools/{category}/{name}/`

#### 5. Manifest Simplification

**Decision:** Use relative paths only in `.agentic-manifest.yaml`

**V1 Manifest Issues:**
- Mixed absolute/relative paths
- Extraneous tool ID entries (not files)

**V2 Manifest:**
```yaml
version: '1.0'
source: agentic-primitives
provider: claude
primitives:
- id: qa/review.md
  kind: commands
  version: 1
  hash: unknown
  files:
  - commands/qa/review.md          ← Relative path
- id: testing/testing-expert.md
  kind: skills
  version: 1
  hash: unknown
  files:
  - skills/testing-expert/SKILL.md  ← Relative path
- id: scrape/firecrawl-scraper
  kind: tools
  version: 1
  hash: unknown
  files:
  - tools/scrape/firecrawl-scraper/tool.yaml  ← Relative path
```

**Fix:** Transformer returns relative paths using `strip_prefix(output_dir)`

## Consequences

### Positive

✅ **Dramatically Simpler:**
- 1 file instead of 2 (no .meta.yaml)
- 50% reduction in nesting depth (3 levels vs 4-5)
- Standard naming conventions (`{name}.md`)

✅ **Claude Code Native:**
- Plugins work directly without build step
- Standard frontmatter format
- Compatible with Claude's marketplace

✅ **Auto-Generated Adapters:**
- FastMCP, LangChain, OpenAI from tool.yaml
- Single source of truth for tool interface
- No manual adapter maintenance

✅ **Git-Based Versioning:**
- Repo tags for versions (semantic versioning)
- Content hashes via git SHA
- No per-file BLAKE3 tracking needed

✅ **Backward Compatible:**
- Build output structure unchanged
- Python imports (`lib/python/`) unchanged
- Existing consumers continue working

✅ **Easier Authoring:**
- Create primitive = create single markdown file
- No `.meta.yaml` to maintain
- JSON Schema validation for tools

### Negative

⚠️ **No Per-File Versioning:**
- Can't version commands/skills independently
- Mitigation: Use git branches for WIP changes
- Git tags version entire primitive set

⚠️ **Category Directories Required:**
- Can't just drop files in `primitives/v2/commands/`
- Must place in category: `primitives/v2/commands/qa/review.md`
- Mitigation: Provides organization, prevents flat sprawl

⚠️ **Build Still Required for V1 Compatibility:**
- V2 sources don't match v1 build output directly
- Must run `agentic-p build --primitives-version v2`
- Mitigation: Build is simple copy+transform, no complex logic

### Deferred to Phase 2

📋 **Not Implemented Yet:**
- Auto-generated MCP adapters from tool.yaml
- Granular install commands (`install command review`)
- Interactive install mode (prompt per file)
- V2 CLI generators (`agentic-p new command qa review`)
- Version manifest (`.agentic-versions.json`)
- Git pre-commit hooks for version validation

## Implementation

### Phase 1: Foundation ✅ COMPLETE

**Milestone 1.1: Source Structure**
- Created `primitives/v2/` with flat, categorized structure
- Migrated 4 example primitives (2 commands, 1 skill, 1 tool)
- Verified Python `lib/python/` imports unchanged

**Milestone 1.2: Build System**
- Implemented `build_v2.rs` for v2 discovery
- Implemented `claude_v2.rs` for frontmatter parsing
- Added `--primitives-version v2` CLI flag
- Successfully builds to `build/claude/`

**Milestone 1.3: Output Compatibility**
- Fixed manifest path inconsistencies (all relative)
- Verified commands have proper frontmatter
- Verified skills use Claude Code format (SKILL.md)
- Verified tools have valid tool.yaml (schema compliant)
- Tested Python imports work correctly

### Phase 2: Enhanced Features 📋 PENDING

**Milestone 2.1: MCP Adapter Generation**
- Read `tools/*/tool.yaml`
- Generate FastMCP server from interface definition
- Update `.mcp.json` with server references
- Test generated servers with MCP Inspector

**Milestone 2.2: Granular Installs**
- `agentic-p install command review` (single primitive)
- `agentic-p install skill testing-expert`
- File-exists logic: skip/force/interactive
- Target detection: `./.claude/` vs `~/.claude/`

**Milestone 2.3: CLI Generators**
- `agentic-p new command <category> <name>`
- `agentic-p new skill <category> <name>`
- `agentic-p new tool <category> <name>`
- Enforce v2 structure, generate frontmatter/tool.yaml

**Milestone 2.4: Documentation**
- Migration guide (v1 → v2)
- Updated architecture docs
- Updated getting-started guide

## Testing

### Verification Results ✅ ALL PASSING

**Build Test:**
```bash
./cli/target/release/agentic-p build --provider claude --primitives-version v2
# Result: 4 primitives built (2 commands, 1 skill, 1 tool)
```

**Output Structure:**
```bash
tree build/claude/
# commands/{category}/{name}.md     ✅
# skills/{name}/SKILL.md             ✅
# tools/{category}/{name}/tool.yaml  ✅
```

**Manifest Paths:**
```yaml
files:
- commands/qa/review.md                          ✅ Relative
- skills/testing-expert/SKILL.md                 ✅ Relative
- tools/scrape/firecrawl-scraper/tool.yaml       ✅ Relative
```

**Python Imports:**
```python
from agentic_isolation import WorkspaceDockerProvider  ✅
from agentic_adapters import generate_hooks             ✅
from agentic_events import SessionRecorder              ✅
```

**Frontmatter Validation:**
```markdown
---
description: Review implementation against project plan
model: sonnet
allowed-tools: Read, Grep, Glob, Bash
---
# ✅ Valid YAML, parsed correctly by claude_v2.rs
```

## Related Decisions

- **ADR-031**: Tool Primitives with Auto-Generated Adapters (foundation)
- **ADR-021**: Primitives Directory Structure (superseded by v2)
- **ADR-019**: File Naming Convention (simplified in v2)
- **ADR-007**: Generated Outputs (still applies to build system)
- **ADR-005**: Polyglot Implementations (still applies to tools)

## References

- Project Plan: `PROJECT-PLAN_20260113_v2-simplification.md`
- Tool Schema: `tool-spec.v1.json`
- V2 Discovery: `cli/src/commands/build_v2.rs`
- V2 Transformer: `cli/src/providers/claude_v2.rs`
- Example Primitives: `primitives/v2/commands/`, `primitives/v2/skills/`, `primitives/v2/tools/`
