# Agentic Primitives CLI - V2

**Status:** ✨ **Active Development** - All new features

## Overview

This is the V2 CLI for agentic-primitives. It supports the simplified V2 primitive structure with:
- Flat directory organization
- Frontmatter-based metadata
- JSON Schema validation
- CLI generators for rapid development
- Auto-generated adapters

**Binary Name:** `agentic-p`

## Installation

```bash
cd cli/v2
cargo build --release
# Binary: target/release/agentic-p
```

## Quick Start

```bash
# Create a new command
./target/release/agentic-p new command qa review \
  --description "Review code quality" \
  --model sonnet

# Validate primitives
./target/release/agentic-p validate primitives/v2/commands/qa/review.md

# Build for Claude
./target/release/agentic-p build --provider claude --primitives-version v2
```

## Features

### CLI Generators
```bash
# Create command
agentic-p new command <category> <name>

# Create skill
agentic-p new skill <category> <name>

# Create tool
agentic-p new tool <category> <name>
```

### Schema Validation
```bash
# Validate single file
agentic-p validate primitives/v2/commands/qa/review.md

# Validate all v2 primitives
agentic-p validate --all
```

### Build System
```bash
# Build v2 primitives
agentic-p build --provider claude --primitives-version v2
```

## Documentation

- [Quick Start Guide](../../docs/v2/quick-start.md)
- [Creating Commands](../../docs/v2/authoring/commands.md)
- [Creating Skills](../../docs/v2/authoring/skills.md)
- [Creating Tools](../../docs/v2/authoring/tools.md)
- [CLI Reference](../../docs/v2/reference/cli.md)

## Development

```bash
# Run tests
cargo test

# Format code
cargo fmt

# Lint
cargo clippy

# Build dev version
cargo build
```

## V1 CLI

For legacy V1 primitive support, use [`cli/v1/`](../v1/README.md)

**Last Updated:** 2026-01-14
