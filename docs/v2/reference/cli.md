# CLI Reference

Complete reference for the `agentic-p` CLI (V2).

## Installation

```bash
cd cli/v2
cargo build --release

# Binary location
./target/release/agentic-p

# Add to PATH (optional)
export PATH="$PATH:$(pwd)/target/release"
```

## Global Options

```bash
agentic-p [OPTIONS] <COMMAND>

Options:
  --spec-version <VERSION>  Spec version (v1, experimental) [default: v1]
  -h, --help                Print help
  -V, --version             Print version
```

## Commands

### `new` - Create New Primitives

Create a new V2 primitive from templates.

```bash
agentic-p new <TYPE> <CATEGORY> <NAME> [OPTIONS]
```

**Arguments:**
- `<TYPE>`: Primitive type (`command`, `skill`, `tool`)
- `<CATEGORY>`: Category name (kebab-case, e.g., `qa`, `devops`)
- `<NAME>`: Primitive name (kebab-case, e.g., `code-review`)

**Options:**
- `--description <TEXT>`: Description (10-200 chars, required)
- `--model <MODEL>`: Model to use (`haiku`, `sonnet`, `opus`, required)
- `--allowed-tools <TOOLS>`: Comma-separated tool list (optional)
- `--argument-hint <HINT>`: Argument hint for commands (optional)
- `--expertise <AREAS>`: Comma-separated expertise for skills (optional)
- `--tags <TAGS>`: Comma-separated tags (optional)
- `--non-interactive`: Skip prompts (all required fields must be provided)

**Examples:**

```bash
# Interactive command creation
agentic-p new command qa review

# Non-interactive with all options
agentic-p new command qa review \
  --description "Review code for quality and best practices" \
  --model sonnet \
  --allowed-tools "Read, Grep, Bash" \
  --non-interactive

# Create skill with expertise
agentic-p new skill testing test-architect \
  --description "Expert in test architecture and strategy" \
  --model sonnet \
  --expertise "TDD, BDD, Integration Testing" \
  --non-interactive

# Create tool
agentic-p new tool data csv-parser \
  --description "Parse CSV files to JSON with validation" \
  --model sonnet \
  --non-interactive
```

**Output:**
- `primitives/v2/{type}/{category}/{name}.md` (commands/skills)
- `primitives/v2/tools/{category}/{name}/` (tools - full directory)

---

### `validate` - Validate Primitives

Validate primitives against JSON schemas.

```bash
agentic-p validate [PATH] [OPTIONS]
```

**Arguments:**
- `[PATH]`: Path to primitive file or directory (optional)

**Options:**
- `--all`: Validate all v2 primitives
- `--primitives-version <VERSION>`: Version to validate (`v2`) [default: v2]
- `-v, --verbose`: Show detailed output

**Examples:**

```bash
# Validate single primitive
agentic-p validate primitives/v2/commands/qa/review.md

# Validate all v2 primitives
agentic-p validate --all

# Verbose output
agentic-p validate --all --verbose
```

**Output:**
```
Validating All V2 Primitives
══════════════════════════════════════════════════

Validating: primitives/v2/commands/qa/review.md
✓ Primitive is valid!

══════════════════════════════════════════════════
Validation Summary
══════════════════════════════════════════════════
Total:  4
Passed: 4 ✓
Failed: 0 ✓
```

---

### `build` - Build Provider Outputs

Build primitives for specific providers.

```bash
agentic-p build --provider <PROVIDER> [OPTIONS]
```

**Options:**
- `-p, --provider <PROVIDER>`: Provider (`claude`, `openai`) (required)
- `-o, --output <PATH>`: Output directory [default: `./build/<provider>/`]
- `--primitive <PATH>`: Build single primitive only
- `--type-filter <TYPE>`: Filter by type (`command`, `skill`, `tool`, `prompt`)
- `--kind <KIND>`: Filter by kind
- `--only <PATTERNS>`: Only build matching patterns (comma-separated globs)
- `--primitives-version <VERSION>`: Version to build (`v1`, `v2`) [default: v1]
- `--clean`: Clean output directory before build
- `-v, --verbose`: Show detailed output

**Examples:**

```bash
# Build all v2 primitives for Claude
agentic-p build --provider claude --primitives-version v2

# Build with clean output
agentic-p build --provider claude --primitives-version v2 --clean

# Build only QA commands
agentic-p build --provider claude --primitives-version v2 \
  --only "qa/*"

# Build single primitive
agentic-p build --provider claude --primitives-version v2 \
  --primitive primitives/v2/commands/qa/review.md

# Verbose output
agentic-p build --provider claude --primitives-version v2 --verbose
```

**Output:**
```
7 primitives to build
[1/7] Transforming: primitives/v2/commands/devops/commit.md
  ✓ Generated 1 files
...
═══════════════════════════════════════
  Build Summary
═══════════════════════════════════════
  Provider:     claude
  Output:       ./build/claude
  Primitives:   7
  Files:        7

  ✓ Build completed successfully!
═══════════════════════════════════════
```

---

### `install` - Install Built Primitives

Install built primitives to system or project locations.

```bash
agentic-p install --provider <PROVIDER> [OPTIONS]
```

**Options:**
- `-p, --provider <PROVIDER>`: Provider (`claude`, `openai`) (required)
- `-g, --global`: Install globally to user directory [default: project]
- `--build-dir <PATH>`: Build directory [default: `./build/<provider>/`]
- `--only <PATTERNS>`: Only install matching patterns (comma-separated globs)
- `--backup <BOOL>`: Backup existing files [default: true]
- `--dry-run`: Show what would be installed without copying
- `-v, --verbose`: Show detailed output

**Examples:**

```bash
# Install to project (.claude/)
agentic-p install --provider claude

# Install globally (~/.claude/)
agentic-p install --provider claude --global

# Install only QA commands
agentic-p install --provider claude --only "qa/*"

# Dry run (show what would be installed)
agentic-p install --provider claude --dry-run

# No backup
agentic-p install --provider claude --backup false
```

---

### `list` - List Primitives

List primitives with filtering.

```bash
agentic-p list [PATH] [OPTIONS]
```

**Arguments:**
- `[PATH]`: Path to primitives directory (optional)

**Options:**
- `--type-filter <TYPE>`: Filter by type (`prompt`, `tool`, `hook`)
- `--kind <KIND>`: Filter by kind (`agent`, `command`, `skill`, etc.)
- `--category <CATEGORY>`: Filter by category
- `--tag <TAG>`: Filter by tag
- `--all-versions`: Show all versions
- `--format <FORMAT>`: Output format (`table`, `json`, `yaml`) [default: table]

**Examples:**

```bash
# List all primitives
agentic-p list

# List commands only
agentic-p list --kind command

# List by category
agentic-p list --category qa

# JSON output
agentic-p list --format json
```

---

### `inspect` - Inspect Primitive

Inspect a primitive in detail.

```bash
agentic-p inspect <PRIMITIVE> [OPTIONS]
```

**Arguments:**
- `<PRIMITIVE>`: Primitive ID or path

**Options:**
- `--version <VERSION>`: Specific version to inspect
- `--full-content`: Show full content (not just preview)
- `--format <FORMAT>`: Output format (`pretty`, `json`, `yaml`) [default: pretty]

**Examples:**

```bash
# Inspect by path
agentic-p inspect primitives/v2/commands/qa/review.md

# Full content
agentic-p inspect primitives/v2/commands/qa/review.md --full-content

# JSON output
agentic-p inspect primitives/v2/commands/qa/review.md --format json
```

---

### Other Commands

- **`init`**: Initialize a new primitives repository
- **`migrate`**: Migrate primitives between spec versions
- **`test-hook`**: Test a hook locally
- **`config`**: Manage per-project configuration
- **`version`**: Manage primitive versions

See `agentic-p <command> --help` for details.

## Exit Codes

- `0`: Success
- `1`: Error (validation failed, build failed, etc.)

## Environment Variables

- `AGENTIC_LOG_LEVEL`: Log level (`debug`, `info`, `warn`, `error`)
- `AGENTIC_CONFIG`: Path to custom config file

## Configuration Files

### `primitives.config.yaml`

Repository-level configuration:

```yaml
version: "2.0"
primitives_dir: "primitives"
build_dir: "build"
```

### `.agentic-manifest.yaml`

Generated after build, tracks built primitives:

```yaml
version: 2.0
provider: claude
built_at: "2026-01-14T12:00:00Z"
primitives:
  - id: commands/qa/review
    path: commands/qa/review.md
    version: 1.0.0
    hash: abc123...
```

## Tips & Tricks

### 1. Chaining Commands

```bash
# Create, validate, and build in one go
agentic-p new command qa review \
  --description "Review code" \
  --model sonnet \
  --non-interactive && \
agentic-p validate primitives/v2/commands/qa/review.md && \
agentic-p build --provider claude --primitives-version v2
```

### 2. Quick Validation Loop

```bash
# Watch for changes and validate
watch -n 2 agentic-p validate --all
```

### 3. Selective Building

```bash
# Build only changed primitives (using git)
git diff --name-only | grep "primitives/v2/" | while read file; do
  agentic-p build --provider claude --primitives-version v2 --primitive "$file"
done
```

## See Also

- [Quick Start Guide](../quick-start.md)
- [Authoring Commands](../authoring/commands.md)
- [Authoring Skills](../authoring/skills.md)
- [Authoring Tools](../authoring/tools.md)
