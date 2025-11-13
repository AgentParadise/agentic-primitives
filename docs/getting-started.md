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
- **Make** (usually pre-installed on Unix systems)
- **Git** (for version control)

Verify your installations:

```bash
rust --version   # Should be 1.75 or later
python --version # Should be 3.11 or later
uv --version     # Should be installed
make --version   # Should be installed
```

---

## Installation

### Clone and Build

```bash
# Clone the repository
git clone https://github.com/yourusername/agentic-primitives.git
cd agentic-primitives

# Build the CLI
make build

# Or build release version (optimized)
make build-release

# Install the CLI to your PATH
cargo install --path cli

# Verify installation
agentic --version
```

### Quick Setup with Make

The repository includes a `Makefile` with all common operations:

```bash
# See all available commands
make help

# Run full QA suite (format, lint, test)
make qa

# Auto-fix issues and run QA
make qa-fix

# Build debug version
make build

# Build release version
make build-release
```

---

## Initialize a Repository

Create a new agentic-primitives repository:

```bash
# Create a new directory for your primitives
mkdir my-primitives
cd my-primitives

# Initialize the repository
agentic init

# Or initialize in a different directory
agentic init --path ./my-other-primitives
```

This creates the following structure:

```
my-primitives/
├── primitives.config.yaml
├── prompts/
├── tools/
├── hooks/
├── providers/
├── schemas/
└── docs/
```

---

## Create Your First Agent

Agents are personas or roles for AI systems. Let's create a Python expert agent:

### Step 1: Scaffold the Agent

```bash
agentic new prompt agent python/python-pro
```

This creates:

```
prompts/agents/python/python-pro/
├── python-pro.prompt.v1.md
└── python-pro.meta.yaml
```

### Step 2: Fill in the Prompt

Edit `prompts/agents/python/python-pro/python-pro.prompt.v1.md`:

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

Edit `prompts/agents/python/python-pro/python-pro.meta.yaml`:

```yaml
id: python-pro
kind: agent
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
    file: python-pro.prompt.v1.md
    status: active
    hash: blake3:...  # Auto-calculated on validation
    created: "2025-11-13"
    notes: "Initial version"

default_version: 1
```

### Step 4: Validate

```bash
agentic validate prompts/agents/python/python-pro

# Or validate everything
agentic validate
```

---

## Create a Command

Commands are discrete tasks or workflows. Let's create a code review command:

### Scaffold and Fill

```bash
agentic new prompt command review/code-review
```

Edit `prompts/commands/review/code-review/code-review.prompt.v1.md`:

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
agentic new prompt skill testing/pytest-patterns
```

Edit `prompts/skills/testing/pytest-patterns/pytest-patterns.prompt.md`:

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
agentic new tool shell/run-tests
```

### Configure Tool

Edit `tools/shell/run-tests/tool.meta.yaml`:

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

Edit `tools/shell/run-tests/impl.claude.yaml`:

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
agentic new hook lifecycle/pre-tool-use
```

This creates a complete hook structure with middleware examples.

### Configure Hook

Edit `hooks/lifecycle/pre-tool-use/hook.meta.yaml`:

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
agentic validate

# Validate specific primitive
agentic validate prompts/agents/python/python-pro

# Get JSON output for scripting
agentic validate --json
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
agentic build --provider claude

# Output goes to: build/claude/.claude/
```

This transforms:
- Agents → System prompts
- Commands → `.claude/commands/*.md`
- Skills → `.claude/skills/*.md`
- Tools → Tool configurations
- Hooks → `settings.json` entries

### Preview Build Output

```bash
# Build to custom directory
agentic build --provider claude --output ./preview

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
agentic install --provider claude --global
```

### Project Installation

Install to current project:

```bash
# Install to ./.claude/
agentic install --provider claude --project
```

### Custom Installation

```bash
# Build and install to custom location
agentic build --provider claude --output ./my-output
agentic install --provider claude --source ./my-output --target ./my-project/.claude/
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

## Next Steps

### Learn More

- **[Architecture Guide](architecture.md)** - Understand the system design
- **[CLI Reference](cli-reference.md)** - All available commands
- **[Hooks Guide](hooks-guide.md)** - Writing middleware
- **[Contributing](contributing.md)** - How to contribute

### Explore Features

- **Version Management**: Create and manage primitive versions
  ```bash
  agentic version bump python/python-pro --notes "Added async expertise"
  agentic version list python/python-pro
  ```

- **Inspect Primitives**: View detailed information
  ```bash
  agentic inspect python/python-pro
  agentic list prompts --kind agent
  ```

- **Test Hooks Locally**: Test before deploying
  ```bash
  agentic test-hook lifecycle/pre-tool-use --input test-event.json
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
agentic validate --verbose

# Check specific layer
agentic validate --layer structural
```

**Build Fails**:
```bash
# Check provider configuration
cat providers/claude/README.md

# Validate before building
agentic validate
```

**Hooks Don't Execute**:
```bash
# Test hook locally
agentic test-hook lifecycle/pre-tool-use --input test.json

# Check Claude settings.json
cat ~/.claude/settings.json
```

### Get Help

- **Documentation**: [docs/](.)
- **Issues**: [GitHub Issues](https://github.com/yourusername/agentic-primitives/issues)
- **Discussions**: [GitHub Discussions](https://github.com/yourusername/agentic-primitives/discussions)

---

**Congratulations!** You've created your first agentic primitives. Keep building and exploring! 🚀

