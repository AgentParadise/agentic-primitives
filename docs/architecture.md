# Agentic Primitives Architecture

This document provides a comprehensive overview of the agentic-primitives system architecture, design decisions, and data flows.

## Table of Contents

1. [System Overview](#system-overview)
2. [Core Concepts](#core-concepts)
3. [Repository Structure](#repository-structure)
4. [Data Structures](#data-structures)
5. [Validation System](#validation-system)
6. [Versioning System](#versioning-system)
7. [Provider System](#provider-system)
8. [Hook System](#hook-system)
9. [CLI Architecture](#cli-architecture)
10. [Data Flows](#data-flows)

---

## System Overview

Agentic Primitives is a **primitive-to-provider compiler** for AI agent systems. It provides:

- **Source**: Provider-agnostic primitives (prompts, tools, hooks)
- **Validation**: Three-layer validation (structural, schema, semantic)
- **Transformation**: Provider-specific adapters (Claude, OpenAI, Cursor)
- **Output**: Provider-native formats ready for deployment

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      User / Developer                        │
└────────────┬───────────────────────────────┬────────────────┘
             │                               │
             ▼                               ▼
    ┌────────────────┐            ┌────────────────────┐
    │   Meta-Prompts │            │   CLI Commands     │
    │  (Generate AI) │            │  (Human-Driven)    │
    └────────┬───────┘            └──────────┬─────────┘
             │                               │
             └───────────┬───────────────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │   Primitives Repo    │
              │  (Source of Truth)   │
              │                      │
              │  - prompts/          │
              │  - tools/            │
              │  - hooks/            │
              │  - providers/        │
              └──────────┬───────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │   Validation Engine  │
              │  (3-Layer System)    │
              │                      │
              │  1. Structural       │
              │  2. Schema           │
              │  3. Semantic         │
              └──────────┬───────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │  Provider Adapters   │
              │  (Transformers)      │
              │                      │
              │  - Claude            │
              │  - OpenAI            │
              │  - Cursor            │
              └──────────┬───────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │  Provider Outputs    │
              │  (Generated Files)   │
              │                      │
              │  build/claude/       │
              │  build/openai/       │
              │  build/cursor/       │
              └──────────┬───────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │    Installation      │
              │  (Deploy to Target)  │
              │                      │
              │  ~/.claude/          │
              │  ~/.openai/          │
              │  ./.claude/          │
              └──────────────────────┘
```

---

## Core Concepts

### Primitives

**Atomic, reusable building blocks** for AI systems:

```
Primitives
├── Prompt Primitives
│   ├── Agents      (personas/roles)
│   ├── Commands    (tasks/workflows)
│   ├── Skills      (knowledge patterns)
│   └── Meta-Prompts (prompt generators)
│
├── Tool Primitives  (capabilities)
│
└── Hook Primitives  (lifecycle events)
```

### Provider Agnosticism

Primitives are **provider-agnostic**:
- Describe **intent**, not implementation
- Use **generic formats** (Markdown, YAML)
- **Compiled** to provider-specific formats

### Single Source of Truth

```
Primitives (committed)
    ↓
Build (transform)
    ↓
Provider Files (generated, not committed)
```

Only primitives are version-controlled. Provider files are build artifacts.

---

## Repository Structure

### Directory Organization

```
agentic-primitives/
│
├── prompts/                    # Prompt primitives
│   ├── agents/                 # Router structure:
│   │   └── <category>/         # /agents/<category>/<id>
│   │       └── <id>/
│   │           ├── <id>.prompt.v1.md
│   │           └── <id>.meta.yaml
│   ├── commands/
│   │   └── <category>/         # /commands/<category>/<id>
│   ├── skills/
│   │   └── <category>/         # /skills/<category>/<id>
│   └── meta-prompts/
│       └── <category>/         # /meta-prompts/<category>/<id>
│
├── tools/                      # Tool primitives
│   └── <category>/             # /tools/<category>/<id>
│       └── <id>/
│           ├── tool.meta.yaml
│           └── impl.*
│
├── hooks/                      # Hook primitives
│   └── <category>/             # /hooks/<category>/<id>
│       └── <id>/
│           ├── hook.meta.yaml
│           ├── impl.python.py
│           └── middleware/
│
├── providers/                  # Provider adapters
│   ├── <provider>/
│   │   ├── models/             # Model configs
│   │   ├── templates/          # Handlebars templates
│   │   └── transformer/        # Transformation logic
│
├── schemas/                    # JSON Schemas
│   ├── prompt-meta.schema.json
│   ├── tool-meta.schema.json
│   └── hook-meta.schema.json
│
├── cli/                        # Rust CLI
│   ├── src/
│   └── tests/
│
└── docs/                       # Documentation
    ├── adrs/                   # Architecture Decision Records
    ├── getting-started.md
    └── architecture.md
```

### Router Structure

Primitives use a **router-like** nested structure:

```
/<type>/<category>/<id>
```

Examples:
- `/prompts/agents/python/python-pro`
- `/prompts/commands/review/code-review`
- `/tools/shell/run-tests`
- `/hooks/lifecycle/pre-tool-use`

Benefits:
- 🧭 Easy navigation for AI agents
- 📁 Logical grouping by domain
- 🔍 Clear primitive discovery
- 🎯 Precise referencing

---

## Data Structures

### Prompt Primitive

```rust
pub struct PromptPrimitive {
    id: String,              // Unique identifier
    kind: PromptKind,        // Agent, Command, Skill, MetaPrompt
    category: String,        // Domain category (e.g., "python", "review")
    domain: String,          // High-level domain
    summary: String,         // One-line description
    
    content: String,         // Loaded from .prompt.vN.md
    
    versions: Vec<VersionEntry>,  // Version history
    default_version: u32,         // Active version
    
    preferred_models: Vec<ModelRef>,  // Model preferences
    tools: Vec<String>,               // Tool dependencies
    
    context_usage: ContextUsage,  // How to use in context
}

pub enum PromptKind {
    Agent,
    Command,
    Skill,
    MetaPrompt,
}

pub struct VersionEntry {
    version: u32,
    file: String,            // e.g., "python-pro.prompt.v1.md"
    status: VersionStatus,   // Draft, Active, Deprecated, Archived
    hash: String,            // BLAKE3 hash for immutability
    created: String,         // ISO 8601 date
    deprecated: Option<String>,
    notes: String,
}
```

### Tool Primitive

```rust
pub struct ToolPrimitive {
    id: String,
    kind: String,            // shell, fs, http, db, etc.
    category: String,
    description: String,
    
    args: Vec<ToolArg>,      // Input parameters
    safety: SafetyConfig,    // Execution constraints
    
    providers: Vec<String>,  // Supported providers
    
    implementations: HashMap<String, ToolImpl>,
    // "claude" → impl.claude.yaml
    // "openai" → impl.openai.json
    // "local" → impl.local.{rs|py|ts}
}

pub struct ToolArg {
    name: String,
    arg_type: String,
    required: bool,
    default: Option<serde_json::Value>,
    description: String,
}
```

### Hook Primitive

```rust
pub struct HookPrimitive {
    id: String,
    kind: String,
    category: String,
    event: HookEvent,        // PreToolUse, PostToolUse, etc.
    summary: String,
    
    execution: ExecutionStrategy,  // Pipeline or Parallel
    middleware: Vec<MiddlewareConfig>,
    
    default_decision: String,  // "allow" or "block"
}

pub enum HookEvent {
    PreToolUse,
    PostToolUse,
    UserPromptSubmit,
    Stop,
    SubagentStop,
    SessionStart,
    SessionEnd,
    PreCompact,
    Notification,
}

pub enum ExecutionStrategy {
    Pipeline,    // Sequential, fail-fast
    Parallel,    // Concurrent, aggregate
}

pub struct MiddlewareConfig {
    id: String,
    path: String,            // Relative to hook directory
    middleware_type: String, // "safety" or "observability"
    enabled: bool,
    config: HashMap<String, serde_json::Value>,
}
```

---

## Validation System

### Three-Layer Validation

```
┌────────────────────────────────────────────┐
│         Layer 1: Structural                │
│  - Directory structure correct             │
│  - Required files exist                    │
│  - Naming conventions followed             │
│  - No orphaned files                       │
└────────────┬───────────────────────────────┘
             │ PASS
             ▼
┌────────────────────────────────────────────┐
│         Layer 2: Schema                    │
│  - YAML/JSON parses successfully           │
│  - Required fields present                 │
│  - Field types correct                     │
│  - Enum values valid                       │
└────────────┬───────────────────────────────┘
             │ PASS
             ▼
┌────────────────────────────────────────────┐
│         Layer 3: Semantic                  │
│  - Tool references resolve                 │
│  - Model references resolve                │
│  - No duplicate IDs                        │
│  - Version entries valid                   │
│  - Hashes match content                    │
└────────────┬───────────────────────────────┘
             │ PASS
             ▼
         ✅ VALID
```

### Validation Flow

```rust
pub fn validate_repository(repo_path: &Path) -> ValidationResult {
    let mut errors = Vec::new();
    
    // Layer 1: Structural
    let structural = StructuralValidator::new(repo_path);
    errors.extend(structural.validate()?);
    
    if !errors.is_empty() {
        return ValidationResult::Failed(errors);
    }
    
    // Layer 2: Schema
    let schema = SchemaValidator::new(repo_path);
    errors.extend(schema.validate()?);
    
    if !errors.is_empty() {
        return ValidationResult::Failed(errors);
    }
    
    // Layer 3: Semantic
    let semantic = SemanticValidator::new(repo_path);
    errors.extend(semantic.validate()?);
    
    if !errors.is_empty() {
        return ValidationResult::Failed(errors);
    }
    
    ValidationResult::Success
}
```

---

## Versioning System

### Version Management

```
Primitive
├── v1 (active)     ← default_version
├── v2 (draft)
└── v3 (deprecated)
```

### Version Lifecycle

```
draft → active → deprecated → archived
  ↓       ↓         ↓           ↓
  NEW     PROD      OLD         HIST
```

### Hash Validation

```
┌──────────────────┐
│ prompt.v1.md     │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Calculate       │
│  BLAKE3 Hash     │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Store in         │
│ meta.yaml        │
│ versions[].hash  │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ On Validation:   │
│ Recalculate &    │
│ Compare          │
└──────────────────┘
```

If hash mismatches: **IMMUTABILITY VIOLATION** → error

---

## Provider System

### Transformation Pipeline

```
Primitive (generic)
      ↓
┌─────────────────┐
│ Load primitive  │
│ + metadata      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Provider        │
│ Transformer     │
│ (Rust code)     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Apply           │
│ Handlebars      │
│ Templates       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Write to        │
│ build/<provider>│
└────────┬────────┘
         │
         ▼
Provider Output (specific)
```

### Provider Trait

```rust
pub trait Provider {
    fn name(&self) -> &str;
    
    fn transform_prompts(
        &self,
        primitives: &[PromptPrimitive]
    ) -> Result<Vec<ProviderFile>>;
    
    fn transform_tools(
        &self,
        tools: &[ToolPrimitive]
    ) -> Result<Vec<ProviderFile>>;
    
    fn transform_hooks(
        &self,
        hooks: &[HookPrimitive]
    ) -> Result<Vec<ProviderFile>>;
    
    fn build(
        &self,
        output_dir: &Path
    ) -> Result<()>;
}
```

### Example: Claude Transformer

```rust
pub struct ClaudeProvider {
    templates: HandlebarsRegistry,
}

impl Provider for ClaudeProvider {
    fn transform_prompts(&self, primitives: &[PromptPrimitive]) 
        -> Result<Vec<ProviderFile>> 
    {
        let mut files = Vec::new();
        
        for primitive in primitives {
            match primitive.kind {
                PromptKind::Agent => {
                    // System prompt
                    let file = self.render_template(
                        "system.md.hbs",
                        primitive
                    )?;
                    files.push(file);
                }
                PromptKind::Command => {
                    // .claude/commands/<id>.md
                    let file = self.render_template(
                        "command.md.hbs",
                        primitive
                    )?;
                    files.push(file);
                }
                // ... etc
            }
        }
        
        Ok(files)
    }
}
```

---

## Hook System

### Hook Architecture

```
Hook Event (JSON via stdin)
         ↓
┌─────────────────────┐
│ Hook Orchestrator   │
│ (impl.python.py)    │
│                     │
│ 1. Load config      │
│ 2. Parse input      │
│ 3. Run middleware   │
│ 4. Aggregate        │
│ 5. Output decision  │
└──────────┬──────────┘
           │
           ▼
┌──────────────────────────────┐
│   Middleware Pipeline        │
│                              │
│  Safety (sequential)         │
│  ├─ block-dangerous-commands │
│  ├─ protect-sensitive-files  │
│  └─ validate-tool-inputs     │
│        ↓ (fail-fast)         │
│                              │
│  Observability (parallel)    │
│  ├─ log-operations           │
│  ├─ emit-metrics             │
│  └─ track-token-usage        │
│        ↓ (best-effort)       │
└──────────┬───────────────────┘
           │
           ▼
Decision + Metrics (JSON to stdout)
```

### Middleware Interface

```python
from dataclasses import dataclass
from typing import Dict, Any, List

@dataclass
class MiddlewareResult:
    decision: str     # "allow" | "block" | "continue"
    reason: str
    metrics: Dict[str, Any]

def process(
    hook_input: Dict[str, Any],
    config: Dict[str, Any],
    previous_results: List[MiddlewareResult],
) -> MiddlewareResult:
    """Standard middleware interface"""
    pass
```

---

## CLI Architecture

### Command Structure

```
agentic (main binary)
├── init          # Bootstrap repository
├── new           # Scaffold primitives
├── validate      # Run validation
├── list          # List primitives
├── inspect       # View primitive details
├── version       # Version management
│   ├── bump
│   ├── list
│   ├── promote
│   └── deprecate
├── migrate       # Migrate to versioned format
├── build         # Generate provider files
├── install       # Deploy to target
└── test-hook     # Test hooks locally
```

### Module Organization

```
cli/src/
├── main.rs           # CLI entry point
├── lib.rs            # Public API
├── error.rs          # Error types
├── config.rs         # Config loading
├── models.rs         # Model resolution
├── schema.rs         # JSON schema validation
│
├── primitives/       # Data structures
│   ├── mod.rs
│   ├── prompt.rs
│   ├── tool.rs
│   └── hook.rs
│
├── commands/         # CLI commands
│   ├── mod.rs
│   ├── init.rs
│   ├── new.rs
│   ├── validate.rs
│   ├── list.rs
│   ├── inspect.rs
│   ├── build.rs
│   ├── install.rs
│   └── test_hook.rs
│
├── validation/       # Validation layers
│   ├── mod.rs
│   ├── structural.rs
│   ├── schema.rs
│   └── semantic.rs
│
├── providers/        # Provider adapters
│   ├── mod.rs
│   ├── traits.rs
│   ├── claude.rs
│   ├── openai.rs
│   └── cursor.rs
│
└── templates/        # Embedded templates
    ├── mod.rs
    └── embedded.rs
```

---

## Data Flows

### Create Primitive Flow

```
User
  │
  ├─ agentic new prompt agent python/python-pro
  │
  ▼
CLI (new command)
  │
  ├─ Parse arguments
  ├─ Create directory: prompts/agents/python/python-pro/
  ├─ Generate meta.yaml from template
  ├─ Generate python-pro.prompt.v1.md from template
  ├─ Calculate BLAKE3 hash
  ├─ Add version entry to meta.yaml
  │
  ▼
Files Created
  │
  └─ User edits files → agentic validate
```

### Build & Install Flow

```
User
  │
  ├─ agentic build --provider claude
  │
  ▼
CLI (build command)
  │
  ├─ Run validation (all layers)
  ├─ Load all primitives
  ├─ Instantiate ClaudeProvider
  ├─ Transform prompts → .claude/commands/, .claude/skills/
  ├─ Transform tools → tool configs
  ├─ Transform hooks → settings.json entries
  ├─ Write to build/claude/.claude/
  │
  ▼
Build Artifacts
  │
  ├─ agentic install --provider claude --global
  │
  ▼
CLI (install command)
  │
  ├─ Copy build/claude/.claude/ → ~/.claude/
  ├─ Merge with existing files (if present)
  ├─ Update settings.json with hooks
  │
  ▼
Installed
  │
  └─ Ready to use with Claude Agent SDK
```

### Validation Flow

```
User
  │
  ├─ agentic validate
  │
  ▼
CLI (validate command)
  │
  ├─ Layer 1: Structural
  │   ├─ Check directory structure
  │   ├─ Verify file naming
  │   └─ Find all primitives
  │
  ├─ Layer 2: Schema
  │   ├─ Parse YAML/JSON
  │   ├─ Load JSON schemas
  │   └─ Validate against schemas
  │
  ├─ Layer 3: Semantic
  │   ├─ Resolve tool references
  │   ├─ Resolve model references
  │   ├─ Check for duplicates
  │   └─ Verify hashes
  │
  ▼
Results
  │
  ├─ If valid: ✅ Exit 0
  └─ If invalid: ❌ Show errors, Exit 1
```

---

## Performance Considerations

### Validation

- **Caching**: Cache parsed primitives, revalidate only changed files
- **Parallel**: Validate primitives in parallel where possible
- **Incremental**: Support partial validation (specific paths)

### Build

- **Hashing**: Hash primitives to detect changes
- **Incremental**: Rebuild only changed primitives
- **Cache**: Store build artifacts with metadata

### Installation

- **Smart Merge**: Only update changed files
- **Backup**: Keep backups before overwriting
- **Verification**: Verify installed files

---

## Security Considerations

### Hash Validation

- **BLAKE3**: Fast, cryptographically secure
- **Immutability**: Hashes prevent tampering with active versions
- **Verification**: Always verify hashes during validation

### Hook Safety

- **Sandboxing**: Hooks run in controlled environment
- **Timeout**: Execution time limits
- **Rate Limiting**: Prevent runaway hooks
- **Fail-Safe**: Errors don't break agent execution

### Tool Safety

- **Input Validation**: Sanitize tool inputs
- **Path Traversal**: Block `../` patterns
- **Dangerous Commands**: Block rm -rf, etc.
- **Permissions**: Minimal required permissions

---

## Future Enhancements

### Planned Features

1. **Registry**: Central registry of community primitives
2. **Dependency Management**: Primitives depending on other primitives
3. **Testing Framework**: Automated testing of primitives
4. **Metrics Dashboard**: Visualize primitive usage and performance
5. **IDE Integration**: VS Code extension for primitives
6. **CI/CD Templates**: GitHub Actions workflows
7. **Multi-Language Support**: Localization of prompts

### Research Areas

- **Automatic Optimization**: ML-driven primitive improvement
- **A/B Testing**: Compare primitive versions
- **Behavioral Analysis**: Analyze agent behavior patterns
- **Safety Formal Verification**: Prove safety properties

---

## Conclusion

Agentic Primitives provides a **robust, scalable, and extensible** foundation for building AI agent systems. The architecture emphasizes:

- ✅ **Single Source of Truth**: Primitives are canonical
- ✅ **Provider Agnosticism**: Support multiple providers
- ✅ **Strict Validation**: Ensure quality from the start
- ✅ **Versioning**: Track evolution and benchmark improvements
- ✅ **Safety First**: Critical safety checks built-in
- ✅ **Composability**: Mix and match primitives freely
- ✅ **Testability**: Comprehensive testing at all layers

For more details, see:
- [Getting Started Guide](getting-started.md)
- [ADRs](adrs/)
- [API Documentation](../cli/docs/)

---

**Questions or Feedback?** Open an issue or discussion on GitHub!

