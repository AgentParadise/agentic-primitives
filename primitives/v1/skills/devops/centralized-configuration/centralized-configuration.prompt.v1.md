---
description: Type-safe, self-documenting environment configuration with idempotent sync
model: sonnet
allowed-tools: Read, Write, Shell
---

# Centralized Configuration

A cross-cutting pattern for managing environment variables across polyglot repositories with type safety, self-documentation, and idempotent synchronization.

## Philosophy

### The Problem

Environment configuration is often an afterthought, leading to:

- **Documentation drift** - `.env.example` doesn't match actual requirements
- **Runtime surprises** - Missing vars cause crashes in production
- **Secret leaks** - Sensitive values accidentally logged
- **Onboarding friction** - New team members don't know what to configure
- **Sync anxiety** - Fear of overwriting existing values when updating

### The Solution

**Code is the source of truth.** Environment variables are defined in typed configuration classes, and everything else is generated from that single source.

```
┌─────────────────────────┐
│   Configuration Code    │  ← Single source of truth
│   (typed, documented)   │
└───────────┬─────────────┘
            │ generate
            ▼
┌─────────────────────────┐
│     .env.example        │  ← Always fresh, committed
└───────────┬─────────────┘
            │ idempotent sync
            ▼
┌─────────────────────────┐
│        .env             │  ← User secrets, gitignored
├─────────────────────────┤
│ ✓ Existing values       │  ← Never overwritten
│ + New variables         │  ← Added with defaults
│ ⚠️ External vars         │  ← Detected & preserved
└─────────────────────────┘
```

---

## Core Principles

### 1. Code as Source of Truth

Configuration is defined in code, not in `.env` files:

```
# Instead of this:
.env.example → manually maintained → gets outdated

# Do this:
ConfigClass → generates → .env.example → syncs → .env
```

### 2. Type Safety

Validate environment variables at startup, not at usage:

- **Fail fast** - Missing required vars crash immediately with clear errors
- **Type coercion** - Strings become bools, ints, URLs automatically
- **Validation** - Check formats, ranges, allowed values

### 3. Self-Documentation

Every variable includes its purpose and where to get it:

```python
api_key: str = Field(
    description="API key for ExampleService. Get from: https://example.com/keys"
)
```

This description becomes a comment in `.env.example`:

```bash
# API key for ExampleService. Get from: https://example.com/keys
API_KEY=
```

### 4. Secret Protection

Sensitive values are:

- **Typed as secrets** - Masked in logs and repr()
- **Never defaulted** - Must be explicitly set
- **Separate from config** - Clear which vars are sensitive

### 5. Idempotent Sync

Running the generator is always safe:

| Scenario | Behavior |
|----------|----------|
| Variable exists in `.env` | **Preserved** - never overwritten |
| New variable in config | **Added** with default value |
| Secret field | **Added** with empty value |
| Removed from config | **Moved** to "External" section |
| Unknown variable | **Preserved** with warning |

### 6. Modular Namespacing

Related variables share a prefix:

| Module | Prefix | Example |
|--------|--------|---------|
| Database | `DB_` | `DB_HOST`, `DB_PORT` |
| GitHub App | `GITHUB_` | `GITHUB_APP_ID` |
| AWS | `AWS_` | `AWS_ACCESS_KEY_ID` |
| Logging | `LOG_` | `LOG_LEVEL`, `LOG_FORMAT` |

This prevents collisions and makes grouping obvious.

---

## Strategies

### Strategy 1: Structured Settings Classes

Define configuration in typed classes with:

- **Fields** - Name, type, default, description
- **Validation** - Custom validators for complex rules
- **Computed properties** - Derived values from other fields
- **Nested modules** - Group related settings

### Strategy 2: Generator Script

A script that:

1. **Introspects** configuration classes
2. **Generates** `.env.example` with comments
3. **Parses** existing `.env`
4. **Merges** preserving user values
5. **Detects** external variables

### Strategy 3: Startup Validation

Load and validate all settings at application startup:

```python
# main.py - validate immediately
settings = get_settings()  # Crashes here if invalid
app = create_app(settings)
```

Not lazily at usage:

```python
# ❌ Bad - crashes at runtime when accessed
def some_function():
    api_key = os.getenv("API_KEY")  # Might be None!
```

---

## Project Structure

```
project/
├── config/                    # or settings/, src/config/
│   ├── __init__.py           # Exports get_settings()
│   ├── settings.py           # Main Settings class
│   ├── database.py           # DatabaseSettings (DB_*)
│   ├── github.py             # GitHubSettings (GITHUB_*)
│   └── logging.py            # LoggingSettings (LOG_*)
├── scripts/
│   └── generate_env.py       # Generator script
├── .env.example              # Generated, committed
├── .env                      # User secrets, gitignored
└── justfile / Makefile       # gen-env command
```

---

## Language Implementations

### Python (Pydantic Settings)

The gold standard for Python configuration.

**Dependencies:**

```toml
# pyproject.toml
dependencies = [
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
]
```

**Main Settings Class:**

```python
# config/settings.py
from functools import lru_cache
from typing import TYPE_CHECKING

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    from config.github import GitHubSettings

class Settings(BaseSettings):
    """Application settings - validated on startup."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = Field(
        default="my-app",
        description="Application name for logging",
    )

    debug: bool = Field(
        default=False,
        description="Enable debug mode. Never in production.",
    )

    # Database
    database_url: str | None = Field(
        default=None,
        description=(
            "PostgreSQL connection URL. "
            "Format: postgresql://user:pass@host:port/db"
        ),
    )

    # Secrets
    api_key: SecretStr | None = Field(
        default=None,
        description="External API key. Get from: https://example.com/keys",
    )

    # Nested settings via property
    @property
    def github(self) -> "GitHubSettings":
        from config.github import GitHubSettings
        return GitHubSettings()


@lru_cache
def get_settings() -> Settings:
    """Cached settings - validates on first access."""
    return Settings()


def reset_settings() -> None:
    """Clear cache for testing."""
    get_settings.cache_clear()
```

**Modular Settings with Prefix:**

```python
# config/github.py
from typing import Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class GitHubSettings(BaseSettings):
    """GitHub App settings with GITHUB_ prefix."""

    model_config = SettingsConfigDict(
        env_prefix="GITHUB_",  # All vars become GITHUB_*
        env_file=".env",
        extra="ignore",
    )

    app_id: str | None = Field(
        default=None,
        description="GitHub App ID from app settings page",
    )

    app_name: str | None = Field(
        default=None,
        description="App slug for commit attribution",
    )

    installation_id: str | None = Field(
        default=None,
        description="Installation ID per organization",
    )

    private_key: SecretStr | None = Field(
        default=None,
        description="RSA private key (PEM format)",
    )

    @property
    def is_configured(self) -> bool:
        return bool(self.app_id and self.installation_id and self.private_key)

    @property
    def bot_username(self) -> str | None:
        return f"{self.app_name}[bot]" if self.app_name else None

    @model_validator(mode="after")
    def validate_complete(self) -> Self:
        """Ensure all-or-nothing configuration."""
        required = [self.app_id, self.installation_id, self.private_key]
        provided = sum(1 for f in required if f is not None)

        if 0 < provided < 3:
            missing = [
                "GITHUB_APP_ID" if not self.app_id else None,
                "GITHUB_INSTALLATION_ID" if not self.installation_id else None,
                "GITHUB_PRIVATE_KEY" if not self.private_key else None,
            ]
            raise ValueError(f"Incomplete config: {[m for m in missing if m]}")
        return self
```

**Generator Script:**

```python
#!/usr/bin/env python3
# scripts/generate_env.py
"""Generate .env.example and sync .env idempotently."""

from pathlib import Path
from pydantic import SecretStr
from pydantic_settings import BaseSettings

PROJECT_ROOT = Path(__file__).parent.parent


def get_default(field_info) -> str:
    from pydantic_core import PydanticUndefined
    d = field_info.default
    if d is None or d is PydanticUndefined:
        return ""
    if isinstance(d, bool):
        return str(d).lower()
    if hasattr(d, "value"):
        return str(d.value)
    return str(d)


def is_secret(field_type) -> bool:
    from typing import get_args, get_origin
    if field_type is SecretStr:
        return True
    origin = get_origin(field_type)
    return origin and SecretStr in get_args(field_type)


def generate_section(cls: type[BaseSettings], name: str, prefix: str = "") -> list[str]:
    import textwrap
    lines = ["", "# " + "=" * 70, f"# {name}", "# " + "=" * 70, ""]

    for fname, finfo in cls.model_fields.items():
        ftype = cls.__annotations__.get(fname, str)
        env_name = f"{prefix}{fname.upper()}"

        if finfo.description:
            for line in textwrap.wrap(finfo.description, 70):
                lines.append(f"# {line}")

        lines.append(f"{env_name}={'' if is_secret(ftype) else get_default(finfo)}")
        lines.append("")

    return lines


def generate() -> str:
    from config.settings import Settings
    from config.github import GitHubSettings

    lines = [
        "# " + "=" * 70,
        "# ENVIRONMENT CONFIGURATION",
        "# " + "=" * 70,
        "# AUTO-GENERATED - run: just gen-env",
        "# " + "=" * 70,
    ]
    lines.extend(generate_section(Settings, "APPLICATION"))
    lines.extend(generate_section(GitHubSettings, "GITHUB", "GITHUB_"))
    return "\n".join(lines)


def parse_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    env = {}
    for line in path.read_text().split("\n"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


def sync(example: Path, env: Path) -> tuple[int, int, list[str]]:
    existing = parse_env(env)
    content = example.read_text()

    template_keys = set()
    new_vars = []
    out = []

    for line in content.split("\n"):
        s = line.strip()
        if not s or s.startswith("#"):
            out.append(line)
            continue
        if "=" in line:
            k, _, default = line.partition("=")
            k = k.strip()
            template_keys.add(k)
            out.append(f"{k}={existing.get(k, default.strip())}")
            if k not in existing:
                new_vars.append(k)
        else:
            out.append(line)

    extra = [k for k in existing if k not in template_keys]
    if extra:
        out.extend(["", "# " + "=" * 70, "# EXTERNAL VARIABLES", "# " + "=" * 70, ""])
        for k in sorted(extra):
            out.append(f"{k}={existing[k]}")

    env.write_text("\n".join(out))
    return len(new_vars), len(extra), extra


def main():
    content = generate()
    example = PROJECT_ROOT / ".env.example"
    env = PROJECT_ROOT / ".env"

    example.write_text(content)
    print(f"✅ Generated {example.name}")

    if env.exists():
        new, ext, ext_vars = sync(example, env)
        print(f"✅ Synced .env ({new} new)" if new else "✅ .env up to date")
        if ext_vars:
            print(f"⚠️  {ext} external: {', '.join(ext_vars)}")
    else:
        env.write_text(content)
        print("✅ Created .env")


if __name__ == "__main__":
    main()
```

**Usage:**

```python
from config import get_settings

settings = get_settings()

# Direct access
print(settings.app_name)

# Nested with prefix
if settings.github.is_configured:
    print(settings.github.bot_username)

# Secrets require explicit access
if settings.api_key:
    key = settings.api_key.get_secret_value()
```

---

### TypeScript (Zod + dotenv)

*(Future implementation)*

```typescript
// config/settings.ts
import { z } from 'zod';
import { config } from 'dotenv';

config();

const SettingsSchema = z.object({
  APP_NAME: z.string().default('my-app'),
  DEBUG: z.coerce.boolean().default(false),
  DATABASE_URL: z.string().url().optional(),
  API_KEY: z.string().optional(),
});

export const settings = SettingsSchema.parse(process.env);
```

---

### Go (envconfig)

*(Future implementation)*

```go
// config/config.go
package config

import "github.com/kelseyhightower/envconfig"

type Settings struct {
    AppName     string `envconfig:"APP_NAME" default:"my-app"`
    Debug       bool   `envconfig:"DEBUG" default:"false"`
    DatabaseURL string `envconfig:"DATABASE_URL"`
    APIKey      string `envconfig:"API_KEY"`
}

func Load() (*Settings, error) {
    var s Settings
    err := envconfig.Process("", &s)
    return &s, err
}
```

---

## Best Practices Checklist

- [ ] **Single source of truth** - Config classes define all variables
- [ ] **Type safety** - All variables have explicit types
- [ ] **Secrets masked** - Use SecretStr/secret types for sensitive values
- [ ] **Descriptions** - Every field has description with "where to get"
- [ ] **Prefixes** - Modular settings use unique prefixes
- [ ] **Validation** - Custom validators for complex rules
- [ ] **Startup check** - Load settings at app start, not lazily
- [ ] **Generator script** - One command to sync everything
- [ ] **Justfile/Makefile** - `gen-env` command documented
- [ ] **Gitignore** - `.env` ignored, `.env.example` committed

---

## Related Skills

- `devops/logging` - Structured logging configuration
- `devops/secrets-management` - Vault, AWS Secrets Manager integration
- `devops/docker-compose` - Container environment configuration
