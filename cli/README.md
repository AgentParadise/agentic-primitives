# Agentic Primitives CLI

**Status:** ✨ **Active Development**

## Overview

The unified CLI for agentic-primitives. Supports both V1 and V2 primitive structures with:
- Flat directory organization (V2) and legacy nested structure (V1)
- Frontmatter-based metadata
- JSON Schema validation
- CLI generators for rapid development
- Auto-generated adapters

**Binary Name:** `agentic-p`

## Installation

```bash
cd cli
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

- [Docs Site](../docs-site-fuma/content/docs/)
- [Migration Guide](../docs-site-fuma/content/docs/guides/migration.mdx)
- [CLI Reference](../docs-site-fuma/content/docs/cli/)
- [Frontmatter Reference](../docs-site-fuma/content/docs/reference/frontmatter.mdx)

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

**Last Updated:** 2026-02-11
