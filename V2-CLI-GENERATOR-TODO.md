# V2 CLI Generator Tool

**Status**: Planned for Phase 2
**Priority**: High (needed for consistent v2 primitive creation)

---

## Purpose

Create a v2-native generator command that enforces the simplified v2 structure and validates against `tool-spec.v1.json`.

## V1 Reference

In v1, we have `primitives/v1/commands/meta/create-command/` which generates new commands with proper structure and metadata.

## V2 Generators Needed

### 1. `primitives/v2/commands/meta/create-command.md`
**Purpose**: Generate new v2 commands with correct structure

**Output Structure**:
```
primitives/v2/commands/{category}/{command-name}.md
```

**Generated Content**:
- YAML frontmatter (description, model, allowed-tools)
- Markdown body with standard sections
- No v1 metadata (no "Level X", no .meta.yaml files)

---

### 2. `primitives/v2/commands/meta/create-skill.md`
**Purpose**: Generate new v2 skills with correct structure

**Output Structure**:
```
primitives/v2/skills/{category}/{skill-name}.md
```

**Generated Content**:
- YAML frontmatter
- Skill knowledge content
- No v1 metadata

---

### 3. `primitives/v2/commands/meta/create-tool.md`
**Purpose**: Generate new v2 tools with correct structure

**Output Structure**:
```
primitives/v2/tools/{category}/{tool-name}/
├── tool.yaml          # Validated against tool-spec.v1.json
├── impl.py           # Implementation stub
├── pyproject.toml    # Dependencies
└── README.md         # Documentation
```

**Validation**:
- Validate `tool.yaml` against JSON Schema (`tool-spec.v1.json`)
- Ensure all required fields present
- Check interface/implementation consistency

---

## Key Differences from V1

| Aspect | V1 | V2 |
|--------|----|----|
| File naming | `{id}.prompt.v1.md` | `{id}.md` |
| Metadata | `.meta.yaml` with BLAKE3 | Frontmatter only |
| Structure | Nested directories | Single file (commands/skills) |
| Validation | Custom validators | JSON Schema for tools |
| Versioning | Per-file hashing | Git tags only |

---

## Implementation Checklist

- [ ] Create `primitives/v2/commands/meta/create-command.md`
- [ ] Create `primitives/v2/commands/meta/create-skill.md`
- [ ] Create `primitives/v2/commands/meta/create-tool.md`
- [ ] Add JSON Schema validation for tool.yaml
- [ ] Test generators create valid v2 primitives
- [ ] Update documentation with generator usage

---

## Usage Examples

### Generate a new command
```bash
/create-command qa test-runner "Run all tests with coverage reporting"
```

Creates: `primitives/v2/commands/qa/test-runner.md`

### Generate a new skill
```bash
/create-skill devops kubernetes-expert "Expert knowledge for Kubernetes operations"
```

Creates: `primitives/v2/skills/devops/kubernetes-expert.md`

### Generate a new tool
```bash
/create-tool scrape puppeteer-scraper "Browser-based web scraping with Puppeteer"
```

Creates:
```
primitives/v2/tools/scrape/puppeteer-scraper/
├── tool.yaml
├── impl.py
├── pyproject.toml
└── README.md
```

---

**Note**: These generators will be built after the core v2 build system is working (Phase 2, Milestone 2.x).
