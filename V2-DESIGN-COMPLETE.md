# ✅ V2 Design Complete

**Date**: 2026-01-13  
**Status**: Ready for Implementation  

---

## What We Built

### 🎯 Core Design Documents

1. **ADR-031: Tool Primitives with Auto-Generated Adapters**
   - Location: `docs/adrs/031-tool-primitives-auto-generated-adapters.md`
   - Complete architectural decision record
   - 5 alternatives evaluated
   - Implementation roadmap (3 phases, 6 weeks)
   - Migration strategy from v1

2. **V2 Architecture Design**
   - Location: `docs/v2-architecture-design.md`
   - Complete system design
   - Directory structure
   - Tool specification format
   - Plugin format (Claude Code standard)
   - Workflows and CLI commands
   - Design principles

3. **Tool Specification Schema**
   - Location: `schemas/tool-spec.v1.json`
   - JSON Schema Draft 7 compliant
   - Complete validation rules
   - Generator hints (MCP, LangChain, OpenAI)
   - Ready for implementation

4. **Implementation Status Tracker**
   - Location: `docs/v2-implementation-status.md`
   - 3-phase roadmap
   - Success criteria
   - Open questions
   - Risk mitigation

---

## Key Architectural Decisions

### ✨ Standard Tool Specification
```yaml
# tools/<tool-name>/tool.yaml
id: example-tool
version: "1.0.0"
interface:
  function: main
  parameters: {...}
  returns: {...}
implementation:
  language: python
  runtime: uv
  entry_point: impl.py
generators:
  mcp:
    framework: fastmcp
  langchain:
    tool_type: StructuredTool
  openai:
    function_name: example_tool
```

### ✨ Auto-Generated Adapters
- **No committed adapter code** - generated on demand
- **FastMCP for Python** - clean decorator pattern
- **Multi-framework** - MCP, LangChain, OpenAI, extensible

### ✨ Claude Code Native
- Plugins use `.claude-plugin/plugin.json`
- Standard directory structure
- Works with `claude --plugin-dir` (no build step)

### ✨ Tool vs MCP Philosophy
- **Tools = Pure functions** (lightweight, portable)
- **MCP = Optional adapter** (only when context-heavy)
- **No forced protocol overhead**

---

## V2 Structure

```
agentic-primitives/
├── tools/              # Pure implementations + tool.yaml
├── plugins/            # Claude Code plugins (standard format)
├── schemas/            # JSON Schema specs ✅
├── cli/                # Rust CLI with generators
├── build/              # Generated adapters (gitignored)
└── docs/
    ├── adrs/031-*.md           ✅
    ├── v2-architecture-design.md    ✅
    └── v2-implementation-status.md  ✅
```

---

## What Changed from V1

| Aspect | V1 | V2 |
|--------|----|----|
| **Structure** | `primitives/v1/<type>/<category>/<id>/` | `tools/` + `plugins/` |
| **Metadata** | `.meta.yaml` (custom, complex) | `tool.yaml` (standard) |
| **Versioning** | BLAKE3 hashes, status tracking | Semantic versioning only |
| **Adapters** | Hand-written, committed | Auto-generated, ephemeral |
| **Build Step** | Always required | Optional (plugins work directly) |
| **Claude Compat** | Requires build | Native (`.claude-plugin/`) |
| **Framework** | Claude-focused | Multi-framework (MCP, LangChain, OpenAI) |

---

## Implementation Roadmap

### Phase 1: Foundation (Weeks 1-2)
- JSON Schema validation
- Generator framework (Rust)
- FastMCP generator
- Basic CLI commands

### Phase 2: Multi-Framework (Weeks 3-4)
- LangChain generator
- OpenAI generator
- Plugin scaffolding
- Integration tests

### Phase 3: Migration (Weeks 5-6)
- V1 → V2 migration tool
- Documentation updates
- Example tools/plugins
- Release prep

---

## Next Steps

### 1. Review & Approve
- [ ] Review ADR-031 with team
- [ ] Approve v2 architecture
- [ ] Confirm implementation timeline

### 2. Start Phase 1
```bash
# Create v2 branch
git checkout -b v2-architecture

# Begin implementation
# - JSON Schema validator
# - Generator framework
# - FastMCP generator
```

### 3. Track Progress
- Use `docs/v2-implementation-status.md` for tracking
- Update phase completion status
- Document learnings and adjustments

---

## Success Criteria

**Phase 1 Complete When**:
- ✅ Can create tool: `agentic-p new tool web/scraper`
- ✅ Can validate: `agentic-p validate tool scraper`
- ✅ Can generate MCP: `agentic-p gen-adapter scraper --target mcp`
- ✅ Generated server runs successfully

**V2 Release Ready When**:
- ✅ All 3 generators working (MCP, LangChain, OpenAI)
- ✅ Plugin system functional
- ✅ V1 → V2 migration automated
- ✅ Documentation complete
- ✅ Example tools/plugins provided

---

## Documentation

All design documents are complete and ready:

- 📄 [ADR-031](docs/adrs/031-tool-primitives-auto-generated-adapters.md) - Architecture decision
- 📄 [V2 Architecture](docs/v2-architecture-design.md) - Complete system design
- 📄 [Implementation Status](docs/v2-implementation-status.md) - Roadmap & tracking
- 📄 [Tool Spec Schema](schemas/tool-spec.v1.json) - JSON Schema

Supporting documentation:
- 📄 [Claude Code Plugins](docs/deps/unknown/claude-code@latest-20260113.md)
- 📄 [FastMCP Quickstart](docs/deps/python/fastmcp@latest-20260113.md)

---

## Design Principles

1. **Standard over Custom** - Use existing formats
2. **Generate over Maintain** - Auto-generate adapters
3. **Simple over Clever** - Obvious structure
4. **Agnostic over Locked** - Support all frameworks
5. **Pure over Wrapped** - Tools are functions, MCP is optional
6. **Explicit over Magic** - Clear specifications

---

## Questions?

See open questions in `docs/v2-implementation-status.md`:
- Generator implementation language (Rust vs Python)
- Community generator registry approach
- Schema versioning strategy
- Testing approach for generated code

---

**Status**: 🎉 **Design Phase Complete** - Ready to begin implementation!

**Next Action**: Review ADR-031, approve design, start Phase 1.
