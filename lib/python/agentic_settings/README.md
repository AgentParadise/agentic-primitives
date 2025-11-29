# agentic-settings

Centralized settings management for agentic-primitives tools.

## Features

- **Centralized Configuration**: Single source of truth for all API keys and settings
- **Auto-Discovery**: Automatically finds `.env` files and project root
- **Type-Safe**: Pydantic-based validation with SecretStr for API keys
- **Provider Helpers**: Easy `require_provider()` and `has_provider()` methods
- **Safe Logging**: `model_dump_safe()` masks secrets for debugging

## Quick Start

```bash
# Install
cd lib/python/agentic_settings
uv pip install -e .

# Create your config
cp env.example .env
# Edit .env with your API keys
```

## Usage

```python
from agentic_settings import get_settings

# Get the singleton settings instance
settings = get_settings()

# Check if a provider is configured
if settings.has_provider("anthropic"):
    api_key = settings.anthropic_api_key.get_secret_value()

# Require a provider (raises MissingProviderError if not set)
try:
    settings.require_provider("firecrawl")
except MissingProviderError as e:
    print(f"Setup required: {e}")

# Safe debugging (secrets masked)
print(settings.model_dump_safe())
```

## Configuration Options

### AI Provider API Keys

| Variable | Description | Get Key |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | Claude models | [Anthropic Console](https://console.anthropic.com/settings/keys) |
| `OPENAI_API_KEY` | GPT models | [OpenAI Platform](https://platform.openai.com/api-keys) |
| `GOOGLE_API_KEY` | Gemini models | [Google AI Studio](https://makersuite.google.com/app/apikey) |

### Tool Provider API Keys

| Variable | Description | Get Key |
|----------|-------------|---------|
| `FIRECRAWL_API_KEY` | Web scraping | [Firecrawl](https://firecrawl.dev/app/api-keys) |

### Logging

| Variable | Default | Description |
|----------|---------|-------------|
| `LOG_LEVEL` | `INFO` | DEBUG, INFO, WARNING, ERROR, CRITICAL |
| `LOG_FILE` | None | Path to log file |
| `LOG_CONSOLE_FORMAT` | `human` | `human` or `json` |
| `LOG_SESSION_ID` | Auto | Session correlation ID |

### Paths

| Variable | Default | Description |
|----------|---------|-------------|
| `PROJECT_ROOT` | Auto-detected | Project root directory |
| `PRIMITIVES_DIR` | `primitives/v1` | Primitives location |
| `BUILD_DIR` | `build` | Build output |
| `DOCS_DIR` | `docs` | Documentation |

### Feature Flags

| Variable | Default | Description |
|----------|---------|-------------|
| `DEBUG_MODE` | `false` | Verbose output |
| `ANALYTICS_ENABLED` | `true` | Analytics events |

## Integration with agentic_logging

```python
from agentic_settings import get_settings
from agentic_logging import get_logger

settings = get_settings()
logger = get_logger(__name__)

# Configure logger from settings
logger.setLevel(settings.log_level)

# Log with session correlation
logger.info(
    "Tool started",
    extra={"session_id": settings.log_session_id}
)
```

## API Reference

### `get_settings(reload=False)`

Get the global settings instance (singleton pattern).

```python
settings = get_settings()
settings_fresh = get_settings(reload=True)  # Force reload
```

### `settings.require_provider(name)`

Validate that a provider's API key is configured.

```python
api_key = settings.require_provider("anthropic")
# Raises MissingProviderError if not set
```

### `settings.has_provider(name)`

Check if a provider is configured without raising.

```python
if settings.has_provider("firecrawl"):
    # Use firecrawl
```

### `settings.model_dump_safe()`

Get a dict representation with secrets masked.

```python
safe_config = settings.model_dump_safe()
# {"anthropic_api_key": "sk-a...xyz", "log_level": "INFO", ...}
```

## Discovery Functions

```python
from agentic_settings import (
    find_project_root,
    find_env_file,
    get_workspace_root,
    resolve_path,
)

# Find project root by searching for markers (.git, pyproject.toml, etc.)
root = find_project_root()

# Find .env file (searches upward)
env = find_env_file()

# Resolve relative paths
abs_path = resolve_path("src/main.py")
```

## Testing

```bash
cd lib/python/agentic_settings
uv run pytest -v
```

## License

MIT

