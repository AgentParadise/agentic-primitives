# Provider JSON Schemas

This directory contains JSON Schema definitions for validating provider configurations.

## Schemas

### model-config.schema.json
Validates model provider configuration files (e.g., `claude-3-opus.yaml`).

**Required fields:**
- `id`: Model identifier
- `name`: Human-readable name
- `family`: Model family
- `provider`: Provider identifier
- `context_window`: Context window size
- `pricing`: Pricing information
- `api`: API configuration

### agent-config.schema.json
Validates agent provider configuration files (e.g., `config.yaml`).

**Required fields:**
- `id`: Agent identifier
- `name`: Human-readable name
- `type`: Must be "agent"
- `vendor`: Vendor name
- `hooks`: Hooks configuration

### hooks-supported.schema.json
Validates hooks-supported.yaml files that define which hook events an agent supports.

**Required fields:**
- `agent`: Agent identifier
- `version`: Configuration version
- `supported_events`: Array of supported events

## Usage

These schemas are used by:
1. `agentic-p providers validate` command
2. IDE validation (if configured)
3. CI/CD validation pipelines

## Validation

Validate your provider configurations:

```bash
# Validate all providers
agentic-p providers validate

# Validate specific provider
agentic-p providers validate --provider anthropic

# Validate only models
agentic-p providers validate --models-only

# Validate only agents
agentic-p providers validate --agents-only
```

## Schema Versioning

Schemas follow semantic versioning:
- Major version: Breaking changes
- Minor version: New optional fields
- Patch version: Documentation/clarifications

Current version: 1.0.0



