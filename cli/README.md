# Agentic Primitives CLI

Command-line interface for managing agentic primitives - atomic building blocks for AI coding systems.

## Building

```bash
# Build debug version
cargo build

# Build release version
cargo build --release

# Run from source
cargo run -- --help
```

## Development

```bash
# Format code
cargo fmt

# Lint code
cargo clippy

# Run tests
cargo test

# Run all QA checks
cd .. && make qa
```

## Installation

```bash
# Install locally
cargo install --path .

# Use directly
agentic --help
```

## Commands

- `init` - Initialize a new primitives repository
- `new` - Create a new primitive (prompt, tool, hook)
- `validate` - Validate primitives structure and content
- `list` - List primitives with filtering
- `inspect` - Inspect a specific primitive
- `version` - Manage primitive versions
- `migrate` - Migrate primitives to latest format
- `build` - Build provider-specific outputs
- `install` - Install to provider directory
- `test-hook` - Test a hook locally

For detailed usage, run `agentic <command> --help`.

## Architecture

The CLI is organized into modules:

- `config` - Load and parse primitives.config.yaml
- `error` - Custom error types
- `models` - Model resolution (provider/model)
- `schema` - JSON schema validation
- `primitives` - Data structures for prompts, tools, hooks
- `commands` - CLI command implementations
- `validation` - Three-layer validation engine
- `providers` - Provider transformers (Claude, OpenAI, Cursor)
- `templates` - Embedded templates for scaffolding

## License

MIT

