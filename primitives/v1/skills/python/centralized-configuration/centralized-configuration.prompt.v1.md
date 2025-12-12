---
description: Type-safe environment configuration with Pydantic Settings
model: sonnet
allowed-tools: Read, Write, Shell
---

# Centralized Configuration Pattern

Create type-safe, self-documenting environment configuration that auto-generates `.env.example` and idempotently syncs `.env`.

## Purpose

*Level 1 (Core Pattern)*

Establish a single source of truth for environment variables using Pydantic Settings, with automatic synchronization that never loses existing values.

## Core Principles

1. **Settings classes are the source of truth** - not `.env` files
2. **Generate, don't duplicate** - `.env.example` is always generated from code
3. **Idempotent sync** - running the generator multiple times is safe
4. **Preserve user values** - never overwrite what the user configured
5. **Detect external vars** - warn about variables not in settings classes

## Architecture

```
┌─────────────────────────┐
│   Settings Classes      │  ← Source of truth (code)
│   (Pydantic BaseSettings)│
└───────────┬─────────────┘
            │ generate
            ▼
┌─────────────────────────┐
│     .env.example        │  ← Always fresh (gitignore: NO)
└───────────┬─────────────┘
            │ idempotent sync
            ▼
┌─────────────────────────┐
│        .env             │  ← User's secrets (gitignore: YES)
├─────────────────────────┤
│ ✓ Existing values       │  ← Preserved
│ + New variables         │  ← Added with defaults
│ ⚠️ External vars         │  ← Detected & preserved
└─────────────────────────┘
```

## Implementation Guide

### Step 1: Project Structure

```
project/
├── settings/
│   ├── __init__.py      # Exports get_settings()
│   ├── config.py        # Main Settings class
│   ├── github.py        # GitHubAppSettings (AEF_GITHUB_*)
│   └── workspace.py     # WorkspaceSettings (AEF_WORKSPACE_*)
├── scripts/
│   └── generate_env_example.py
├── .env.example         # Generated (commit this)
├── .env                 # User secrets (gitignored)
└── justfile             # just gen-env
```

### Step 2: Main Settings Class

```python
# settings/config.py
from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    from settings.github import GitHubAppSettings

class Settings(BaseSettings):
    """Application settings with validation and documentation.
    
    All settings loaded from environment variables.
    Required variables fail fast on startup with clear errors.
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore unknown env vars
    )
    
    # =========================================================================
    # APPLICATION
    # =========================================================================
    
    app_name: str = Field(
        default="my-app",
        description="Application name for logging and identification",
    )
    
    debug: bool = Field(
        default=False,
        description=(
            "Enable debug mode. Shows detailed errors and enables debug logging. "
            "Never enable in production."
        ),
    )
    
    # =========================================================================
    # DATABASE
    # =========================================================================
    
    database_url: str | None = Field(
        default=None,
        description=(
            "PostgreSQL connection URL. "
            "Format: postgresql://user:password@host:port/database "
            "Required for production."
        ),
    )
    
    # =========================================================================
    # SECRETS (use SecretStr)
    # =========================================================================
    
    api_key: SecretStr | None = Field(
        default=None,
        description=(
            "API key for external service. "
            "Get from: https://example.com/keys"
        ),
    )
    
    # =========================================================================
    # NESTED SETTINGS (via properties)
    # =========================================================================
    
    @property
    def github(self) -> GitHubAppSettings:
        """Get GitHub App settings (AEF_GITHUB_* prefix)."""
        from settings.github import GitHubAppSettings
        return GitHubAppSettings()
    
    # =========================================================================
    # COMPUTED PROPERTIES
    # =========================================================================
    
    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return not self.debug


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings.
    
    Settings loaded once and cached. Validates all env vars immediately.
    """
    return Settings()


def reset_settings() -> None:
    """Clear settings cache (for testing)."""
    get_settings.cache_clear()
```

### Step 3: Modular Settings with Prefixes

```python
# settings/github.py
from typing import Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class GitHubAppSettings(BaseSettings):
    """GitHub App authentication settings.
    
    All variables use AEF_GITHUB_* prefix.
    Example: app_id → AEF_GITHUB_APP_ID
    """
    
    model_config = SettingsConfigDict(
        env_prefix="AEF_GITHUB_",  # ← Key: adds prefix to all vars
        env_file=".env",
        extra="ignore",
    )
    
    app_id: str | None = Field(
        default=None,
        description=(
            "GitHub App ID (numeric). "
            "Find at: https://github.com/settings/apps/<app-name> → General"
        ),
    )
    
    app_name: str | None = Field(
        default=None,
        description=(
            "GitHub App slug for commit attribution. "
            "Example: 'my-bot' → commits as 'my-bot[bot]'"
        ),
    )
    
    installation_id: str | None = Field(
        default=None,
        description="Installation ID per organization/account",
    )
    
    private_key: SecretStr | None = Field(
        default=None,
        description=(
            "RSA private key in PEM format for JWT signing. "
            "Generate at: GitHub App settings → Private keys"
        ),
    )
    
    webhook_secret: SecretStr | None = Field(
        default=None,
        description=(
            "HMAC secret for webhook verification. "
            "Generate with: openssl rand -hex 32"
        ),
    )
    
    # =========================================================================
    # COMPUTED PROPERTIES
    # =========================================================================
    
    @property
    def is_configured(self) -> bool:
        """Check if fully configured for API access."""
        return bool(self.app_id and self.installation_id and self.private_key)
    
    @property
    def bot_username(self) -> str | None:
        """Get bot username for commit attribution."""
        return f"{self.app_name}[bot]" if self.app_name else None
    
    @property
    def bot_email(self) -> str | None:
        """Get bot email in GitHub noreply format."""
        if self.app_id and self.app_name:
            return f"{self.app_id}+{self.app_name}[bot]@users.noreply.github.com"
        return None
    
    # =========================================================================
    # VALIDATION
    # =========================================================================
    
    @model_validator(mode="after")
    def validate_complete(self) -> Self:
        """Ensure all-or-nothing configuration."""
        required = [self.app_id, self.installation_id, self.private_key]
        provided = sum(1 for f in required if f is not None)
        
        if 0 < provided < 3:
            missing = []
            if not self.app_id:
                missing.append("AEF_GITHUB_APP_ID")
            if not self.installation_id:
                missing.append("AEF_GITHUB_INSTALLATION_ID")
            if not self.private_key:
                missing.append("AEF_GITHUB_PRIVATE_KEY")
            raise ValueError(f"Incomplete config. Missing: {', '.join(missing)}")
        
        return self
```

### Step 4: Generator Script

```python
#!/usr/bin/env python3
# scripts/generate_env_example.py
"""Generate .env.example and sync .env idempotently.

Usage:
    python scripts/generate_env_example.py
    # or
    just gen-env
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import SecretStr
from pydantic_settings import BaseSettings

PROJECT_ROOT = Path(__file__).parent.parent


def get_default_value(field_info) -> str:
    """Get default value as string for .env file."""
    from pydantic_core import PydanticUndefined
    
    default = field_info.default
    
    if default is None or default is PydanticUndefined:
        return ""
    if isinstance(default, bool):
        return str(default).lower()
    if hasattr(default, "value"):  # Enums
        return str(default.value)
    if isinstance(default, list | tuple):
        return ""  # Skip complex defaults
    
    return str(default)


def is_secret_type(field_type: type[Any]) -> bool:
    """Check if field is a secret (shouldn't show defaults)."""
    from typing import get_args, get_origin
    
    if field_type is SecretStr:
        return True
    origin = get_origin(field_type)
    if origin is not None:
        return SecretStr in get_args(field_type)
    return False


def generate_section(
    settings_class: type[BaseSettings],
    section_name: str,
    prefix: str = "",
    description: str | None = None,
) -> list[str]:
    """Generate env vars for a settings class."""
    lines = [
        "",
        "# " + "=" * 76,
        f"# {section_name}",
        "# " + "=" * 76,
    ]
    
    if description:
        lines.append(f"# {description}")
    
    lines.append("")
    
    for field_name, field_info in settings_class.model_fields.items():
        field_type = settings_class.__annotations__.get(field_name, str)
        env_name = f"{prefix}{field_name.upper()}"
        default = get_default_value(field_info)
        
        # Add description as comment
        if field_info.description:
            # Wrap long descriptions
            import textwrap
            for line in textwrap.wrap(field_info.description, width=76):
                lines.append(f"# {line}")
        
        # Add variable (empty for secrets)
        if is_secret_type(field_type):
            lines.append(f"{env_name}=")
        else:
            lines.append(f"{env_name}={default}")
        
        lines.append("")
    
    return lines


def generate_env_example() -> str:
    """Generate .env.example from all settings classes."""
    # Import your settings classes here
    from settings.config import Settings
    from settings.github import GitHubAppSettings
    
    lines = [
        "# " + "=" * 76,
        "# ENVIRONMENT CONFIGURATION",
        "# " + "=" * 76,
        "#",
        "# AUTO-GENERATED from settings classes.",
        "# Do not edit manually - run: just gen-env",
        "#",
        "# Copy to .env and fill in your values.",
        "# " + "=" * 76,
    ]
    
    # Main settings (no prefix)
    lines.extend(generate_section(Settings, "APPLICATION"))
    
    # GitHub settings (AEF_GITHUB_* prefix)
    lines.extend(generate_section(
        GitHubAppSettings,
        "GITHUB APP",
        prefix="AEF_GITHUB_",
        description="Secure GitHub authentication. See docs/github-app-setup.md",
    ))
    
    # Add more settings classes as needed...
    
    return "\n".join(lines)


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse existing .env into key=value dict.
    
    Handles multi-line values in quotes.
    """
    if not path.exists():
        return {}
    
    env_vars: dict[str, str] = {}
    content = path.read_text()
    
    current_key: str | None = None
    current_value_lines: list[str] = []
    in_multiline = False
    
    for line in content.split("\n"):
        if not in_multiline:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
        
        if in_multiline:
            current_value_lines.append(line)
            if line.rstrip().endswith('"') and not line.rstrip().endswith('\\"'):
                full_value = "\n".join(current_value_lines)
                if current_key:
                    env_vars[current_key] = full_value
                current_key = None
                current_value_lines = []
                in_multiline = False
            continue
        
        if "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            
            if value.startswith('"') and not value.endswith('"'):
                in_multiline = True
                current_key = key
                current_value_lines = [value]
            else:
                env_vars[key] = value
    
    return env_vars


def sync_env_file(
    example_path: Path,
    env_path: Path,
) -> tuple[int, int, int, list[str]]:
    """Sync .env with .env.example idempotently.
    
    - Preserves existing values
    - Adds new variables with defaults
    - Preserves external variables with warning
    
    Returns: (existing_count, new_count, total_count, extra_vars)
    """
    existing_vars = parse_env_file(env_path)
    example_content = example_path.read_text()
    
    template_keys: set[str] = set()
    new_vars: list[str] = []
    output_lines: list[str] = []
    
    for line in example_content.split("\n"):
        stripped = line.strip()
        
        if not stripped or stripped.startswith("#"):
            output_lines.append(line)
            continue
        
        if "=" in line:
            key, _, default_value = line.partition("=")
            key = key.strip()
            default_value = default_value.strip()
            template_keys.add(key)
            
            if key in existing_vars:
                output_lines.append(f"{key}={existing_vars[key]}")
            else:
                output_lines.append(f"{key}={default_value}")
                new_vars.append(key)
        else:
            output_lines.append(line)
    
    # Preserve external variables
    extra_vars = [k for k in existing_vars if k not in template_keys]
    
    if extra_vars:
        output_lines.extend([
            "",
            "# " + "=" * 76,
            "# EXTERNAL / UNKNOWN VARIABLES",
            "# " + "=" * 76,
            "# These variables are not defined in settings classes.",
            "# They may come from external tools or plugins.",
            "# Review periodically - remove if no longer needed.",
            "",
        ])
        for key in sorted(extra_vars):
            output_lines.append(f"{key}={existing_vars[key]}")
        output_lines.append("")
    
    env_path.write_text("\n".join(output_lines))
    
    existing_count = len([k for k in existing_vars if k in template_keys])
    new_count = len(new_vars)
    total_count = len(template_keys)
    
    return existing_count, new_count, total_count, extra_vars


def main() -> None:
    """Generate .env.example and sync .env."""
    content = generate_env_example()
    
    example_path = PROJECT_ROOT / ".env.example"
    env_path = PROJECT_ROOT / ".env"
    
    # Generate .env.example
    example_path.write_text(content)
    print(f"✅ Generated {example_path}")
    
    # Count variables
    total_vars = sum(
        1 for line in content.split("\n")
        if "=" in line and not line.strip().startswith("#")
    )
    print(f"   {total_vars} environment variables documented")
    
    # Sync .env
    if env_path.exists():
        existing, new, total, extra = sync_env_file(example_path, env_path)
        
        if new > 0:
            print(f"✅ Synced {env_path}")
            print(f"   {existing} existing values preserved")
            print(f"   {new} new variables added")
        else:
            print(f"✅ {env_path} is up to date ({existing} variables)")
        
        if extra:
            print(f"⚠️  {len(extra)} external variables found:")
            for var in sorted(extra):
                print(f"   - {var}")
            print("   Preserved in 'EXTERNAL / UNKNOWN VARIABLES' section.")
    else:
        env_path.write_text(content)
        print(f"✅ Created {env_path} from template")
        print("   ⚠️  Fill in secret values (API keys, etc.)")


if __name__ == "__main__":
    main()
```

### Step 5: Justfile Recipe

```just
# Generate .env.example and sync .env
gen-env:
    uv run python scripts/generate_env_example.py
```

## Usage Patterns

### Access Settings in Code

```python
from settings import get_settings

settings = get_settings()

# Direct access
print(f"App: {settings.app_name}")

# Nested settings with prefix
github = settings.github
if github.is_configured:
    print(f"Bot: {github.bot_username}")

# Secrets require explicit access
if settings.api_key:
    key = settings.api_key.get_secret_value()
```

### Testing with Overrides

```python
import os
from unittest.mock import patch

def test_settings():
    env = {
        "APP_NAME": "test",
        "AEF_GITHUB_APP_ID": "12345",
        "AEF_GITHUB_INSTALLATION_ID": "67890",
        "AEF_GITHUB_PRIVATE_KEY": "test-key",
    }
    
    with patch.dict(os.environ, env, clear=True):
        from settings import reset_settings, get_settings
        reset_settings()
        
        settings = get_settings()
        assert settings.app_name == "test"
        assert settings.github.is_configured
```

### Run Generator

```bash
$ just gen-env

✅ Generated .env.example
   64 environment variables documented
✅ Synced .env
   51 existing values preserved
   3 new variables added
⚠️  2 external variables found:
   - FIRECRAWL_API_KEY
   - UI_FEEDBACK_DATABASE_URL
   Preserved in 'EXTERNAL / UNKNOWN VARIABLES' section.
```

## Best Practices

### 1. Use Prefixes for Modular Settings

Each settings class gets a unique prefix to avoid collisions:

| Class | Prefix | Example Variable |
|-------|--------|------------------|
| Settings | (none) | `APP_NAME` |
| GitHubAppSettings | `AEF_GITHUB_` | `AEF_GITHUB_APP_ID` |
| WorkspaceSettings | `AEF_WORKSPACE_` | `AEF_WORKSPACE_POOL_SIZE` |

### 2. Always Use SecretStr for Sensitive Values

```python
# ❌ Bad - secrets can leak in logs
api_key: str | None = Field(...)

# ✅ Good - secrets are masked
api_key: SecretStr | None = Field(...)

# Accessing:
if settings.api_key:
    key = settings.api_key.get_secret_value()
```

### 3. Write Detailed Descriptions

Descriptions become comments in `.env.example`:

```python
database_url: str | None = Field(
    default=None,
    description=(
        "PostgreSQL connection URL. "
        "Format: postgresql://user:password@host:port/database "
        "For local dev: postgresql://postgres:postgres@localhost:5432/mydb"
    ),
)
```

### 4. Validate Early, Fail Fast

```python
# main.py
from settings import get_settings

# This validates all settings immediately
settings = get_settings()

# If any required var is missing, you get a clear error:
# pydantic_core.ValidationError: 1 validation error for Settings
# database_url
#   Field required [type=missing]
```

### 5. Use Computed Properties

Don't duplicate logic - compute derived values:

```python
@property
def bot_email(self) -> str | None:
    """GitHub noreply email for bot."""
    if self.app_id and self.app_name:
        return f"{self.app_id}+{self.app_name}[bot]@users.noreply.github.com"
    return None
```

## Sync Behavior Reference

| Scenario | Action |
|----------|--------|
| Variable exists in `.env` | **Preserved** (never overwritten) |
| New variable in settings | **Added** with default value |
| Secret field | **Added** with empty value |
| Variable removed from settings | **Moved** to EXTERNAL section |
| External tool adds variable | **Preserved** with warning |

## Dependencies

```toml
# pyproject.toml
[project]
dependencies = [
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
]
```
