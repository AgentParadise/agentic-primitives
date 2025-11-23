# ADR-003: Non-Interactive Scaffolding

```yaml
---
status: accepted
created: 2025-11-13
updated: 2025-11-13
deciders: System Architect
consulted: Development Team
informed: All Stakeholders
---
```

## Context

The `agentic-p new` command creates new primitives by generating directory structures and template files. We need to decide how much interactivity this command should have:

- **Fully interactive**: Prompt for all fields (id, summary, domain, tools, models, etc.)
- **Partially interactive**: Prompt for essentials, use defaults for rest
- **Non-interactive**: Accept arguments, generate scaffold with TODOs

### Use Cases

1. **Manual Creation**: Human developer runs CLI, fills in content
2. **Agentic Creation**: AI agent (or meta-prompt) generates primitive
3. **Batch Creation**: Script generates multiple primitives at once
4. **CI/CD Integration**: Automated pipeline creates primitives

### The Core Question

**Should the CLI be responsible for generating complete, production-ready primitives, or just providing valid scaffolds for AI/humans to fill?**

### Alternative Approaches Considered

1. **Fully Interactive CLI**
   ```bash
   $ agentic-p new prompt agent
   Enter ID: python-pro
   Enter domain: python
   Enter summary: Expert Python engineer
   Enter preferred models (comma-separated): claude-3.5-sonnet, gpt-4
   Select tools (multi-select): run-tests, search-code
   Context usage - as_system? [y/n]: y
   ```
   - Pros: User-friendly, complete primitives
   - Cons: Not scriptable, blocks automation, complex Rust code

2. **Hybrid Approach**
   ```bash
   $ agentic-p new prompt agent python/python-pro \
       --domain python \
       --summary "Expert Python engineer" \
       --models claude/sonnet,openai/gpt-codex
   ```
   - Pros: Flexible, can be interactive or not
   - Cons: Complex flag parsing, unclear when to prompt vs use defaults

3. **Non-Interactive Scaffold** (CHOSEN)
   ```bash
   $ agentic-p new prompt agent python/python-pro
   Created prompts/agents/python/python-pro/
   ├── python-pro.prompt.v1.md  (TODO: Fill in prompt content)
   ├── python-pro.meta.yaml     (Generated with templates)
   
   Next: Edit the files to complete the primitive
   ```
   - Pros: Simple, scriptable, AI-friendly, separates concerns
   - Cons: Requires manual editing, two-step process

## Decision

We will implement **non-interactive scaffolding** where the CLI:

1. **Creates Structure Only**
   - Generates correct directory paths (`<type>/<category>/<id>/`)
   - Creates required files (`.prompt.v1.md`, `.meta.yaml`)
   - Populates templates with minimal required fields

2. **AI/Human Fills Content**
   - Prompt files contain TODO comments and instructions
   - Meta.yaml has template values with examples
   - Content generation is delegated to:
     - Human developers (manual editing)
     - AI agents (using meta-prompts)
     - External scripts

3. **Separation of Concerns**
   - **CLI responsibility**: Structure, naming, validation
   - **AI/Human responsibility**: Content, quality, domain expertise

### Template Structure

**Generated `<id>.prompt.v1.md`**:
```markdown
<!-- TODO: Fill in this prompt with your agent/command/skill content -->

# Role

TODO: Define the role or purpose of this primitive

# Goal

TODO: Explain what this primitive should accomplish

# Inputs

TODO: List expected inputs or context

# Outputs

TODO: Describe expected outputs or behavior

# Examples

TODO: Provide examples if helpful

# Constraints

TODO: Note any constraints or limitations
```

**Generated `<id>.meta.yaml`**:
```yaml
id: python-pro
kind: agent
category: python
domain: python  # TODO: Adjust if needed
summary: "TODO: One-line summary of this agent"

tags:
  - python  # TODO: Add relevant tags

defaults:
  preferred_models:
    - claude/sonnet  # TODO: Choose appropriate models
  max_iterations: 4

context_usage:
  as_system: true    # Typical for agents
  as_user: false
  as_overlay: false

tools: []  # TODO: Add tool IDs this primitive uses

inputs: []  # TODO: Define structured inputs if needed

# Version management (auto-generated)
versions:
  - version: 1
    file: python-pro.prompt.v1.md
    status: draft
    hash: blake3:...  # Auto-calculated
    created: "2025-11-13"
    notes: "Initial version"

default_version: 1
```

## Consequences

### Positive

✅ **Simplicity**: CLI code is straightforward, no complex prompting logic

✅ **Scriptable**: Can generate multiple primitives in batch
   ```bash
   for agent in python-pro web-architect devops-sensei; do
     agentic-p new prompt agent python/$agent
   done
   ```

✅ **AI-Friendly**: Perfect for meta-prompt workflows
   - Meta-prompt generates content
   - Human/AI fills in scaffold

✅ **Separation of Concerns**: 
   - CLI handles structure (what it's good at)
   - AI handles content (what it's good at)

✅ **Consistent**: Every primitive starts from same template

✅ **Fast**: No waiting for user input

✅ **Testable**: Easy to test scaffold generation in unit tests

### Negative

⚠️ **Two-Step Process**: Create scaffold, then fill content

⚠️ **Manual Editing Required**: Can't generate complete primitive in one command

⚠️ **Less User-Friendly**: No guided prompts for beginners

⚠️ **Template Maintenance**: Templates must stay in sync with schemas

### Mitigations

1. **Excellent Templates**: Provide clear TODO comments and examples

2. **Meta-Prompts**: Use `generate-primitive` meta-prompt to fill scaffolds
   ```bash
   agentic-p new prompt agent python/python-pro
   # Use meta-prompt to generate content based on requirements
   claude --meta-prompt generate-primitive \
     "Create an expert Python agent for architecture and debugging"
   ```

3. **Documentation**: Clear guides showing the two-step workflow

4. **Editor Integration**: VS Code extension could auto-open generated files

5. **Validation Feedback**: Run `agentic-p validate` to check if TODOs are filled

6. **Future Enhancement**: Optional `--fill` flag using embedded AI
   ```bash
   agentic-p new prompt agent python/python-pro \
     --fill "Expert Python engineer for architecture and debugging"
   ```

## Implementation Details

### Command Syntax

```bash
# Prompts
agentic-p new prompt <kind> <category>/<id>
agentic-p new prompt agent python/python-pro
agentic-p new command review/code-review
agentic-p new skill testing/pytest-patterns
agentic-p new meta-prompt generation/generate-agent

# Tools
agentic-p new tool <category>/<id>
agentic-p new tool shell/run-tests

# Hooks
agentic-p new hook <category>/<id>
agentic-p new hook lifecycle/pre-tool-use
```

### What Gets Generated

**For all primitives**:
- Directory structure with correct nesting
- Meta.yaml with template and required fields
- Appropriate content files (versioned or not)
- BLAKE3 hash calculation
- TODO comments where content needed

**Versioned primitives** (agents, commands, meta-prompts):
- `<id>.prompt.v1.md` with version 1
- `versions` array in meta.yaml
- `default_version: 1`

**Unversioned primitives** (skills):
- `<id>.prompt.md` (without version number)
- Optional versioning if user wants it later

### Template Embedding

Templates are embedded in Rust binary:
```rust
// src/templates/embedded.rs
pub const AGENT_META_TEMPLATE: &str = r#"
id: {{id}}
kind: agent
category: {{category}}
# ... etc
"#;

pub const PROMPT_TEMPLATE: &str = r#"
<!-- TODO: Fill in this prompt -->
# ... etc
"#;
```

Using Handlebars for substitution:
```rust
let rendered = handlebars.render("agent-meta", &data)?;
```

## Success Criteria

Non-interactive scaffolding is successful when:

1. ✅ `agentic-p new` generates valid directory structure in <1 second
2. ✅ Generated scaffolds pass Layer 1 (structural) validation
3. ✅ Generated scaffolds pass Layer 2 (schema) validation
4. ✅ Templates clearly indicate where content is needed
5. ✅ Meta-prompts can fill scaffolds programmatically
6. ✅ Batch generation works reliably
7. ✅ Generated files are immediately editable

## Related Decisions

- **ADR-001: Staged Bootstrap** - Meta-prompts fill scaffolds
- **ADR-002: Strict Validation** - Templates must generate valid scaffolds
- **ADR-009: Versioned Primitives** - Scaffolds include version structure

## References

- [Yeoman](https://yeoman.io/) - Interactive scaffolding tool
- [cargo generate](https://github.com/cargo-generate/cargo-generate) - Rust template tool
- [cookiecutter](https://github.com/cookiecutter/cookiecutter) - Python project templates

## Notes

**Why not interactive?**

Interactive CLIs are great for humans but terrible for automation. Since our goal is to build an **agentic system** where AI can generate primitives, we optimize for machine-readability over human convenience.

**Workflow Example**:

```bash
# 1. Generate scaffold
$ agentic-p new prompt agent python/python-pro

# 2. Fill with AI (using meta-prompt)
$ claude --system-prompt "$(agentic inspect meta-prompts/generation/generate-primitive)" \
    "Create an expert Python agent for architecture and debugging" \
    > prompts/agents/python/python-pro/python-pro.prompt.v1.md

# 3. Validate
$ agentic-p validate prompts/agents/python/python-pro

# 4. Build
$ agentic-p build --provider claude
```

**Future: AI Integration**

Could add optional AI integration:
```bash
agentic-p new prompt agent python/python-pro \
  --fill-with-ai \
  --description "Expert Python engineer specializing in async patterns and debugging"
```

This would internally use a meta-prompt to generate complete content, but it's not required for v1.

---

**Status**: Accepted  
**Last Updated**: 2025-11-13

