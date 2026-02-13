---
title: "ADR-034: V3 Plugin-Based Architecture"
status: accepted
created: 2026-02-12
updated: 2026-02-12
author: System Migration
supersedes: ADR-032 (V2 Simplified Structure)
tags: [architecture, v3, plugins, migration]
---

# ADR-034: V3 Plugin-Based Architecture

## Status

**Accepted**

- Created: 2026-02-12
- Updated: 2026-02-12
- Author(s): System Migration
- Supersedes: ADR-032 (V2 Simplified Structure)

## Context

The repository underwent a fundamental architectural shift from a primitives-based system (v1/v2) to a plugin-based system (v3.x). This ADR documents the final v3 architecture that replaced both the v1 primitives build system and the v2 simplified structure described in ADR-032.

### Evolution Timeline

**v1.x (2025-early)**: Rust CLI (`agentic-p`) with primitives build system
- `primitives/v1/` directory structure
- Build command: `agentic-p build --provider claude`
- Per-file versioning with BLAKE3 hashes
- Separate `.meta.yaml` metadata files
- Generated outputs to `build/{provider}/`

**v2.x (2026-01)**: Simplified primitives structure (ADR-032)
- `primitives/v2/` with flattened hierarchy
- Frontmatter metadata instead of `.meta.yaml`
- Git-based versioning instead of per-file hashes
- Still required build step
- Rust CLI still present

**v3.x (2026-02, current)**: Plugin-native architecture
- No primitives directories
- Claude Code native plugins via `claude plugin install`
- No build step required for plugin usage
- Plugins self-contained in `plugins/` directory
- Rust CLI completely removed

### The Problem with v2

ADR-032's v2 architecture was accepted but never stabilized because:

1. **Still required a build step** - plugins had to be "transformed" to work
2. **Rust CLI dependency** - maintaining a Rust CLI for simple file operations was overhead
3. **Not Claude Code native** - plugins weren't directly installable via Claude's marketplace
4. **Dual maintenance** - had to maintain both source structure and build outputs

The v2 architecture was conceptually correct (simpler than v1) but didn't go far enough—it kept the build system when Claude Code already had a native plugin system.

## Decision

### Adopt Claude Code Native Plugin Architecture

Use Claude Code's built-in plugin system as the **only** primitive distribution mechanism. Eliminate all build steps, Rust CLI, and transformation logic.

**Core principle:** Plugins are developed and used in the same format—no intermediate steps.

### Plugin Structure

```
plugins/
├── sdlc/                           # SDLC plugin
│   ├── .claude-plugin/
│   │   └── plugin.json             # Manifest (name, version, requires_env)
│   ├── commands/
│   │   ├── review.md               # Command with YAML frontmatter
│   │   ├── git_push.md
│   │   └── git_merge.md
│   ├── skills/
│   │   ├── commit/
│   │   │   └── SKILL.md            # Claude Code skill format
│   │   └── testing-expert/
│   │       └── SKILL.md
│   └── hooks/
│       ├── hooks.json              # Hook event bindings
│       └── handlers/
│           ├── pre-tool-use.py     # Security validators
│           └── validators/
│               └── security/
│                   └── bash.py
├── workspace/                      # Observability plugin
│   ├── .claude-plugin/
│   │   └── plugin.json
│   └── hooks/
│       ├── hooks.json
│       └── handlers/
│           ├── session-start.py
│           ├── session-end.py
│           ├── post-tool-use.py
│           └── ...
├── research/                       # Research tools plugin
│   ├── .claude-plugin/
│   │   └── plugin.json             # Declares FIRECRAWL_API_KEY requirement
│   └── tools/
│       └── firecrawl/
│           ├── firecrawl-scraper.tool.yaml
│           └── impl.py
└── meta/                           # Primitive generators plugin
    └── ...
```

### Installation & Usage

**Local development:**
```bash
# Install from local directory (development)
claude plugin install ./plugins/sdlc --scope user

# Or load directly without install
claude --plugin-dir ./plugins/sdlc -p "review the code"
```

**From marketplace:**
```bash
# Add marketplace (one-time)
claude plugin marketplace add AgentParadise/agentic-primitives

# Install plugin
claude plugin install sdlc@agentic-primitives --scope user

# Update
claude plugin marketplace update agentic-primitives
claude plugin update sdlc@agentic-primitives
```

**Docker workspaces (ADR-033):**
```dockerfile
# Copy plugins as-is to Docker image
COPY plugins/ /opt/agentic/plugins/

# Entrypoint auto-discovers and loads via --plugin-dir
CMD ["claude", "--plugin-dir", "/opt/agentic/plugins/sdlc", ...]
```

### Plugin Manifest Format

Each plugin has `.claude-plugin/plugin.json`:

```json
{
  "name": "sdlc",
  "version": "1.0.0",
  "description": "Software Development Lifecycle primitives",
  "requires_env": {
    "GITHUB_TOKEN": {
      "description": "GitHub personal access token for PR operations",
      "required": false,
      "secret": true
    }
  }
}
```

**Key features:**
- `requires_env`: Declares environment variables needed by tools/hooks
- `secret: true`: Values masked in logs, passed securely to Docker
- `required: false`: Plugin degrades gracefully if var not set

### Commands & Skills Format

**Commands** (`commands/*.md`):
```markdown
---
description: Review implementation against project plan
argument-hint: <path-to-project-plan.md>
model: sonnet
allowed-tools: Read, Grep, Glob, Bash
---

# Review Command

[Prompt content here...]
```

**Skills** (`skills/{name}/SKILL.md`):
```markdown
---
description: Create conventional commits with proper formatting
model: sonnet
---

# Commit Skill

[Prompt content here...]
```

### Hooks Format

**hooks.json** registers event handlers:
```json
{
  "hooks": [
    {
      "event": "PreToolUse",
      "command": ["uv", "run", "${CLAUDE_PLUGIN_ROOT}/hooks/handlers/pre-tool-use.py"]
    }
  ]
}
```

**Handler script** (Python):
```python
#!/usr/bin/env python3
import sys
import json

try:
    from agentic_events import EventEmitter
    emitter = EventEmitter(session_id="...", output=sys.stderr)
except ImportError:
    emitter = None  # Graceful degradation

# Process event
event = json.loads(sys.stdin.read())
# ... validation logic ...

# Emit decision event
if emitter:
    emitter.emit("security_decision", {...})

# Output decision to stdout (allow/block)
print(json.dumps({"allowed": True}))
```

### Python Packages (Infrastructure Primitives)

Python packages remain separate from plugins:

```
lib/python/
├── agentic_isolation/    # Docker workspace sandboxing
├── agentic_events/       # JSONL event emission
└── agentic_logging/      # Structured logging
```

**Why separate?**
- Plugins are **prompts** (Claude Code primitives)
- Packages are **infrastructure** (Python libraries)
- Installed differently: `claude plugin install` vs `pip install`
- Used differently: Loaded by Claude Code vs imported in Python code

## Alternatives Considered

### Alternative 1: Keep v2 Build System

**Description:** Maintain the `primitives/v2/` structure with Rust CLI transforming to plugin format.

**Pros:**
- Could add validation during build
- Could generate adapters (MCP, LangChain)
- Controlled deployment artifact

**Cons:**
- Build step adds friction to development
- Rust CLI maintenance overhead
- Not idiomatic for Claude Code
- Duplicates validation Claude Code already does

**Reason for rejection:** The build step was unnecessary ceremony. Claude Code's plugin system already handles validation and distribution. The v2 structure (ADR-032) was on the right track but didn't fully embrace the native plugin model.

---

### Alternative 2: Monorepo with Subplugins

**Description:** Single mega-plugin containing all primitives, with namespaced commands (`sdlc:commit`, `workspace:session-start`).

**Pros:**
- Single install command
- Simplified versioning

**Cons:**
- All-or-nothing deployment (can't install just SDLC plugin)
- Larger download size
- Harder to maintain (all changes in one plugin)
- Namespace pollution

**Reason for rejection:** Modularity matters. Teams should install only the plugins they need. A workspace orchestrator doesn't need research tools.

---

### Alternative 3: Hybrid (Plugins + Build System)

**Description:** Use plugins for distribution but keep Rust CLI for validation and scaffolding.

**Pros:**
- Best of both worlds (native plugins + tooling)
- CLI could generate new primitives with `agentic-p new`

**Cons:**
- Dual code paths (plugin format + CLI logic)
- Rust dependency for what's essentially file operations
- Maintenance burden

**Reason for rejection:** Simplicity wins. Validation can be done with Python scripts (no Rust needed). Scaffolding is rare enough to do manually.

## Consequences

### Positive Consequences

✅ **Zero build step**
- Edit a `.md` file, it's immediately usable
- No waiting for compilation or transformation
- Faster development iteration

✅ **Claude Code native**
- Plugins work with Claude's marketplace
- Standard installation flow users already know
- Automatic update mechanism via `claude plugin update`

✅ **Self-contained plugins**
- Each plugin is a complete unit (manifest + commands + skills + hooks)
- Can be developed, tested, and versioned independently
- Clear dependency boundaries

✅ **Simplified codebase**
- Removed 10,000+ lines of Rust CLI code
- No more build system maintenance
- No transformer logic to debug

✅ **Better DX (developer experience)**
- Standard markdown files with frontmatter
- Python scripts for hooks (no Rust knowledge needed)
- Clear file layout (`plugins/{name}/.claude-plugin/plugin.json`)

✅ **Docker-ready (ADR-033)**
- Plugins load in-place via `--plugin-dir`
- No tmpfs conflicts
- Environment variables declared in plugin manifests

### Negative Consequences

⚠️ **No automated validation at "build time"**
- Since there's no build, validation happens at runtime (when Claude loads plugin)
- Mitigation: Add `scripts/validate-plugin.py` for CI checks (proposed in ADR-033)

⚠️ **No MCP adapter generation**
- v2 promised auto-generated MCP adapters from `tool.yaml`
- This was never implemented, and manual adapters work fine
- Mitigation: If needed later, can add standalone generator script

⚠️ **Git-only versioning**
- Can't version individual commands independently
- Must tag entire plugin release
- Mitigation: Use branches for WIP, tags for releases (standard git workflow)

⚠️ **Manual coordination for breaking changes**
- No automated dependency checking between plugins
- If plugin A depends on plugin B's command format, must coordinate manually
- Mitigation: Use semantic versioning, clear changelogs, and tests

### Neutral Consequences

🔷 **File format change required**
- Migration from v1/v2 required rewriting all primitives
- One-time cost, now complete
- Historical note: v1→v2 was also a rewrite, so this was inevitable

🔷 **Rust CLI knowledge lost**
- Team members who knew Rust build system no longer needed
- Simpler stack (Python + Markdown only)
- Trade-off: Less language diversity, easier onboarding

## Implementation

### Migration Completed

The v3 migration is **complete** as of version 3.1.2:

**Phase 1: Plugin Structure** ✅
- Created `plugins/` directory with 5 plugins (sdlc, workspace, research, meta, docs)
- Migrated all active primitives to plugin format
- Added `.claude-plugin/plugin.json` manifests

**Phase 2: Remove Build System** ✅
- Deleted Rust CLI (`cli/` directory)
- Removed `primitives/v1/` and `primitives/v2/` directories
- Removed build artifacts and manifests

**Phase 3: Docker Integration** ✅ (ADR-033)
- Updated `providers/workspaces/claude-cli/` to use `--plugin-dir`
- Removed hardcoded `settings.json` generation
- Added `requires_env` to plugin manifests

**Phase 4: Documentation Cleanup** ✅ (This ADR)
- Removed 19 obsolete ADRs describing primitives architecture
- Updated README to reflect plugin count (13 ADRs remain)
- Created this ADR to document the v3 architecture

### Plugin Validation (Future)

ADR-033 proposes `scripts/validate-plugin.py` for CI:

```bash
# Validate structure, self-containment, env vars, hooks
python3 scripts/validate-plugin.py --strict plugins/*/
```

This would catch issues like:
- Missing `plugin.json`
- Broken `hooks.json` references
- Absolute paths in hook commands (breaks `--plugin-dir`)
- Undeclared environment variables

## Related Decisions

- **ADR-020**: Agentic Prompt Taxonomy - conceptual framework still valid
- **ADR-027**: Provider Workspace Images - extended by ADR-033
- **ADR-032**: V2 Simplified Structure - superseded by this ADR
- **ADR-033**: Plugin-Native Workspace Images - Docker integration

## References

- [Claude Code Plugin Documentation](https://docs.anthropic.com/en/docs/agents/claude-code)
- `plugins/` directory - live implementation
- `lib/python/agentic_isolation/` - workspace provider that loads plugins
- `providers/workspaces/claude-cli/` - Docker workspace using `--plugin-dir`
- ADR Audit Report: `ADR_AUDIT_REPORT.md` (2026-02-12)

---

## Summary

The v3 plugin architecture represents a **complete departure** from the primitives-based v1/v2 systems. By embracing Claude Code's native plugin system, we eliminated build complexity, simplified the codebase, and created a more maintainable and extensible foundation.

**Key insight:** The best build system is no build system. When the platform (Claude Code) already has a distribution mechanism (plugins), use it directly rather than layering custom tooling on top.
