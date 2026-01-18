# Agentic Primitives CLI - V1 (Legacy)

**Status:** 🔒 **Maintenance Mode** - Frozen for stability

## Overview

This is the V1 CLI for agentic-primitives. It supports the V1 primitive structure with complex metadata and provider abstractions.

**Binary Name:** `agentic-p-v1`

## Installation

```bash
cd cli/v1
cargo build --release
# Binary: target/release/agentic-p-v1
```

## Usage

```bash
# Build V1 primitives
./target/release/agentic-p-v1 build --provider claude

# Validate V1 primitives
./target/release/agentic-p-v1 validate primitives/v1/
```

## Maintenance Policy

- **✅ Critical bug fixes only**
- **❌ No new features**
- **❌ No breaking changes**
- **→ New development happens in V2** (`cli/v2/`)

## For New Projects

**Use V2 instead:** [`cli/v2/`](../v2/README.md)

V2 offers:
- Simpler structure (50% less nesting)
- Faster authoring (CLI generators)
- Better validation (JSON schemas)
- Modern tooling

## Migration

See [V1 to V2 Migration Guide](../../docs/v2/guides/migrating-from-v1.md)

## Support

V1 CLI will be supported for:
- Existing projects using V1 primitives
- Migration period (6-12 months)
- Critical security/bug fixes only

**Last Updated:** 2026-01-14
