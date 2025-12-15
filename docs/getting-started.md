# Getting Started with Agentic Primitives

Welcome to Agentic Primitives! This guide will walk you through setting up your first repository and creating your first primitives.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
3. [Initialize a Repository](#initialize-a-repository)
4. [Create Your First Agent](#create-your-first-agent)
5. [Create a Command](#create-a-command)
6. [Create a Skill](#create-a-skill)
7. [Create a Tool](#create-a-tool)
8. [Create a Hook](#create-a-hook)
9. [Validation](#validation)
10. [Building for a Provider](#building-for-a-provider)
11. [Installation](#installation-1)
12. [Using with Claude Agent SDK](#using-with-claude-agent-sdk)
13. [Next Steps](#next-steps)

---

## Prerequisites

Before you begin, ensure you have the following installed:

- **Rust** 1.75 or later ([install](https://www.rust-lang.org/tools/install))
- **Python** 3.11 or later (for hooks)
- **uv** ([install](https://github.com/astral-sh/uv#installation))
- **Just** (cross-platform task runner)
- **Git** (for version control)

Verify your installations:

```bash
rust --version   # Should be 1.75 or later
python --version # Should be 3.11 or later
uv --version     # Should be installed
just --version   # Should be 1.37.0 or later
```

### Installing Just

```bash
# macOS
brew install just

# Windows
winget install Casey.Just

# Linux (via cargo)
cargo install just

# Or see https://github.com/casey/just#installation
```

---

## Installation

### Clone and Build

```bash
# Clone the repository
git clone https://github.com/yourusername/agentic-primitives.git
cd agentic-primitives

# Build the CLI
just build

# Or build release version (optimized)
just build-release

# Install the CLI to your PATH
just install

# Verify installation
agentic-p --version
```

### Quick Setup with Just

The repository uses **[Just](https://github.com/casey/just)** for cross-platform task running:

```bash
# See all available commands
just

# Run full QA suite (format, lint, test)
just qa

# Auto-fix issues and run QA
just qa-fix

# Build debug version
just build

# Build release version
just build-release
```

---

## Initialize a Repository

Create a new agentic-primitives repository:

```bash
# Create a new directory for your primitives
mkdir my-primitives
cd my-primitives

# Initialize the repository
agentic-p init

# Or initialize in a different directory
agentic-p init --path ./my-other-primitives
```

This creates the following structure:

```
my-primitives/
├── primitives.config.yaml
├── specs/
│   └── v1/
├── primitives/
│   ├── v1/
│   │   ├── prompts/
│   │   ├── tools/
│   │   └── hooks/
│   └── experimental/
├── providers/
└── docs/
```

---

## Create Your First Agent

Agents are personas or roles for AI systems. Let's create a Python expert agent:

### Step 1: Scaffold the Agent

```bash
agentic-p new prompt agent python/python-pro
```

This creates:

```
primitives/v1/prompts/agents/python/python-pro/
├── prompt.v1.md
└── meta.yaml
```

### Step 2: Fill in the Prompt

Edit `primitives/v1/prompts/agents/python/python-pro/prompt.v1.md`:

```markdown
You are **Python Pro**, a senior Python engineer with expertise in:
- Modern Python (3.11+) best practices
- Async programming and concurrency
- Testing strategies (pytest, coverage)
- Package management (uv, Poetry, pip-tools)
- Type hints and mypy
- Performance optimization

## Your Approach

When working on Python code, you:
1. **Analyze** the problem thoroughly before coding
2. **Design** with testability in mind
3. **Implement** clean, idiomatic Python
4. **Test** comprehensively
5. **Document** clearly

## Guidelines

- Prefer modern idioms (dataclasses, type hints, pattern matching)
- Use async/await for I/O-bound operations
- Write tests alongside code (TDD when appropriate)
- Keep functions small and focused
- Handle errors gracefully with specific exceptions

## Output Format

When suggesting code:
- Provide complete, runnable examples
- Include docstrings for functions/classes
- Add inline comments for complex logic
- Show test examples when relevant
```

### Step 3: Configure Metadata

Edit `primitives/v1/prompts/agents/python/python-pro/meta.yaml`:

```yaml
id: python-pro
kind: agent
spec_version: "v1"
category: python
domain: python
summary: "Expert Python engineer for architecture, debugging, and best practices"

tags:
  - python
  - backend
  - architecture
  - testing

defaults:
  preferred_models:
    - claude/sonnet
    - openai/gpt-codex
  max_iterations: 5

context_usage:
  as_system: true
  as_user: false
  as_overlay: false

tools:
  - run-tests
  - search-code

inputs: []

versions:
  - version: 1
    status: active
    hash: blake3:...  # Auto-calculated on validation
    created: "2025-11-13"
    notes: "Initial version"

default_version: 1
```

### Step 4: Validate

```bash
agentic-p validate primitives/v1/prompts/agents/python/python-pro

# Or validate everything
agentic-p validate
```

---

## Create a Command

Commands are discrete tasks or workflows. Let's create a code review command:

### Scaffold and Fill

```bash
agentic-p new prompt command review/code-review
```

Edit `primitives/v1/prompts/commands/review/code-review/prompt.v1.md`:

```markdown
You are a code reviewer. Given a code diff or file, you will:

## Review Checklist

1. **Correctness**: Does the code do what it's supposed to?
2. **Clarity**: Is the code easy to understand?
3. **Maintainability**: Will this be easy to change later?
4. **Performance**: Are there obvious inefficiencies?
5. **Security**: Are there potential vulnerabilities?
6. **Tests**: Are there adequate tests?

## Output Format

Provide:
- ✅ **Strengths**: What's done well
- ⚠️ **Issues**: Problems to fix (with severity: critical, major, minor)
- 💡 **Suggestions**: Improvements to consider
- 🔧 **Code Examples**: Show specific improvements where helpful

## Tone

Be constructive and specific. Praise good patterns. Explain why changes are needed.
```

Edit the `meta.yaml` similarly to the agent.

---

## Create a Skill

Skills are reusable knowledge patterns. Let's create a pytest patterns skill:

### Scaffold and Fill

```bash
agentic-p new prompt skill testing/pytest-patterns
```

Edit `primitives/v1/prompts/skills/testing/pytest-patterns/prompt.v1.md`:

```markdown
# Pytest Best Practices and Patterns

When writing tests with pytest, follow these patterns:

## Test Structure (Given-When-Then)

```python
def test_user_registration():
    # Given: Setup initial state
    user_data = {"email": "test@example.com", "password": "secure123"}
    
    # When: Perform action
    result = register_user(user_data)
    
    # Then: Assert outcome
    assert result.success is True
    assert result.user.email == "test@example.com"
```

## Fixtures for Reusability

```python
@pytest.fixture
def temp_database():
    """Provide a temporary database for tests"""
    db = create_test_database()
    yield db
    db.cleanup()

def test_with_database(temp_database):
    user = temp_database.create_user("test@example.com")
    assert user.id is not None
```

## Parametrize for Multiple Cases

```python
@pytest.mark.parametrize("input,expected", [
    ("hello", "HELLO"),
    ("World", "WORLD"),
    ("", ""),
])
def test_uppercase(input, expected):
    assert input.upper() == expected
```

## Common Patterns

- Use descriptive test names: `test_user_login_with_invalid_credentials_returns_error`
- One assertion concept per test
- Avoid testing implementation details
- Mock external dependencies
- Use `pytest.raises` for exceptions
```

---

## Create a Tool

Tools define capabilities. Let's create a test runner tool:

### Scaffold

```bash
agentic-p new tool shell/run-tests
```

### Configure Tool

Edit `primitives/v1/tools/shell/run-tests/meta.yaml`:

```yaml
id: run-tests
kind: shell
category: shell
description: "Run the project's test suite and return results"

args:
  - name: command
    type: string
    required: false
    default: "pytest"
    description: "Test command to run"
  
  - name: path
    type: string
    required: false
    default: "."
    description: "Path to run tests in"

safety:
  max_runtime_sec: 600
  working_dir: "."
  allow_write: false

providers:
  - claude
  - openai
  - local
```

### Add Provider Implementations

Edit `primitives/v1/tools/shell/run-tests/impl.claude.yaml`:

```yaml
tool: run-tests
type: bash
command_template: "cd {{path}} && {{command}}"
allowed_patterns:
  - "pytest"
  - "pytest *"
  - "python -m pytest"
notes: "Runs pytest in the specified directory"
```

---

## Create a Hook

Hooks handle lifecycle events. Let's create a safety hook:

### Scaffold

```bash
agentic-p new hook lifecycle/pre-tool-use
```

This creates a complete hook structure with middleware examples.

### Configure Hook

Edit `primitives/v1/hooks/lifecycle/pre-tool-use/meta.yaml`:

```yaml
id: pre-tool-use
kind: hook
category: lifecycle
event: PreToolUse
summary: "Safety checks and observability for tool execution"

execution: pipeline

middleware:
  - id: block-dangerous-commands
    path: middleware/safety/block-dangerous-commands.py
    type: safety
    enabled: true
    config:
      dangerous_patterns:
        - "rm -rf"
        - "sudo rm"
  
  - id: log-operations
    path: middleware/observability/log-operations.py
    type: observability
    enabled: true
    config:
      log_file: "~/.claude/logs/operations.jsonl"

default_decision: "allow"
```

The scaffolded middleware files already include working implementations.

---

## Validation

Validate your primitives to ensure they're correct:

```bash
# Validate everything
agentic-p validate

# Validate specific primitive
agentic-p validate primitives/v1/prompts/agents/python/python-pro

# Get JSON output for scripting
agentic-p validate --json
```

The validator checks:
- ✅ **Layer 1 (Structural)**: Directory structure, file naming
- ✅ **Layer 2 (Schema)**: YAML/JSON correctness
- ✅ **Layer 3 (Semantic)**: Cross-references, hashes

---

## Building for a Provider

Generate provider-specific outputs (e.g., for Claude Agent SDK):

```bash
# Build for Claude
agentic-p build --provider claude

# Output goes to: build/claude/.claude/
```

This transforms:
- Agents → System prompts
- Commands → `.claude/commands/*.md`
- Skills → `.claude/skills/*.md`
- Tools → Tool configurations
- Hooks → `settings.json` entries

### Selective Build (--only)

Build only specific primitives using glob patterns:

```bash
# Build only QA-related primitives
agentic-p build --provider claude --only "qa/*"

# Build specific primitives (comma-separated)
agentic-p build --provider claude --only "qa/review,devops/commit"

# Build all commands in a category
agentic-p build --provider claude --only "devops/*,meta/*"
```

**Pattern Syntax:**
| Pattern | Matches |
|---------|---------|
| `qa/*` | All primitives in `qa/` category |
| `qa/review` | Exact match |
| `*/commit` | Any primitive ending in `commit` |

### Preview Build Output

```bash
# Build to custom directory
agentic-p build --provider claude --output ./preview

# Inspect generated files
ls -R ./preview
```

---

## Installation

Install generated files to a target directory:

### Global Installation

Install to your home directory:

```bash
# Install to ~/.claude/
agentic-p install --provider claude --global
```

### Project Installation

Install to current project:

```bash
# Install to ./.claude/
agentic-p install --provider claude
```

### Selective Installation (--only)

Install only specific primitives:

```bash
# Install only QA commands
agentic-p install --provider claude --only "qa/*"

# Install specific primitives
agentic-p install --provider claude --only "qa/review,devops/commit,hooks/*"

# Dry-run to preview what would be installed
agentic-p install --provider claude --only "qa/*" --dry-run
```

### Custom Build Directory

```bash
# Install from custom build location
agentic-p install --provider claude --build-dir ./my-build/claude
```

---

## Using with Claude Agent SDK

Once installed, use your primitives with Claude:

### Use an Agent

```bash
claude --agent python-pro "Review my FastAPI code for performance issues"
```

### Use a Command

```bash
claude /code-review app.py
```

### Use a Skill

Skills are automatically available as context when relevant, or you can reference them explicitly in your prompts.

### Hooks in Action

Hooks run automatically during agent execution:
- **PreToolUse**: Blocks dangerous commands, logs operations
- **PostToolUse**: Formats code, verifies changes
- **SessionStart**: Loads context, sets up environment

---

## Understanding Versioning

The repository uses two layers of versioning:

1. **System-Level Versioning**: Architectural versions (v1, v2, experimental)
   - Current version: v1
   - Directory: `/primitives/v1/`
   - Schemas: `/specs/v1/`

2. **Prompt-Level Versioning**: Content versions (prompt.v1.md, prompt.v2.md)
   - Tracks refinements to individual primitives
   - BLAKE3 hash verification
   - Status lifecycle: draft → active → deprecated

For complete details, see `docs/versioning-guide.md`.

---

## Next Steps

### Learn More

- **[Architecture Guide](architecture.md)** - Understand the system design
- **[Versioning Guide](versioning-guide.md)** - Complete versioning documentation
- **[CLI Reference](cli-reference.md)** - All available commands
- **[Hooks Guide](hooks-guide.md)** - Writing middleware
- **[Contributing](contributing.md)** - How to contribute

### Explore Features

- **Version Management**: Create and manage primitive versions
  ```bash
  agentic-p version bump python/python-pro --notes "Added async expertise"
  agentic-p version list python/python-pro
  ```

- **Inspect Primitives**: View detailed information
  ```bash
  agentic-p inspect python/python-pro
  agentic-p list prompts --kind agent
  ```

- **Test Hooks Locally**: Test before deploying
  ```bash
  agentic-p test-hook lifecycle/pre-tool-use --input test-event.json
  ```

### Build Your Library

1. Create domain-specific agents (JavaScript, DevOps, etc.)
2. Build command libraries for your workflow
3. Collect reusable skill patterns
4. Implement custom safety hooks
5. Add observability for your team's metrics

### Share and Collaborate

- Publish your primitives repository
- Contribute to the community
- Share meta-prompts for generating primitives
- Report issues and suggest improvements

---

## Troubleshooting

### Common Issues

**Validation Fails**:
```bash
# See detailed errors
agentic-p validate --verbose

# Check specific layer
agentic-p validate --layer structural
```

**Build Fails**:
```bash
# Check provider configuration
cat providers/claude/README.md

# Validate before building
agentic-p validate
```

**Hooks Don't Execute**:
```bash
# Test hook locally
agentic-p test-hook lifecycle/pre-tool-use --input test.json

# Check Claude settings.json
cat ~/.claude/settings.json
```

### Get Help

- **Documentation**: [docs/](.)
- **Issues**: [GitHub Issues](https://github.com/yourusername/agentic-primitives/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/agentic-primitives/discussions)

---

**Congratulations!** You've created your first agentic primitives. Keep building and exploring! 🚀

