---
description: Set up auto-generated .env.example with idempotent .env sync from typed settings
argument-hint: "[language] - python (default), typescript, go"
model: sonnet
allowed-tools: Read, Write, Bash, Glob, Grep
---

# Env Management

Implement a **code-as-source-of-truth** environment variable system: typed settings classes
auto-generate a documented `.env.example`, which then idempotently syncs into `.env` —
preserving existing values, adding new ones, and flagging unknown vars.

```
Settings classes (typed, documented)
        │  just gen-env
        ▼
   .env.example  ← always fresh, committed to git
        │  idempotent sync
        ▼
     .env  ← gitignored, user secrets
      ├── existing values  → preserved exactly
      ├── new variables    → added with defaults
      └── unknown vars     → flagged, preserved in separate section
```

This is the implementation companion to `sdlc/centralized-configuration`,
which covers the philosophy. This skill does the wiring.

---

## Variables

LANGUAGE: $1 || "python"   # python, typescript, go

---

## Workflow

### 1. Audit the Current State

Read the project to understand what exists:

```bash
# Check for existing env management
ls .env.example .env 2>/dev/null || echo "No .env files found"
ls scripts/generate_env* scripts/gen_env* 2>/dev/null || echo "No generator found"
grep -r "BaseSettings\|pydantic_settings\|dotenv\|z.env\|env(" --include="*.py" --include="*.ts" -l | head -10
```

Identify:
- Whether a generator script already exists (extend it, don't replace it)
- Where settings classes are defined
- What prefix conventions are in use (`APP_`, `SYN_`, etc.)
- Any existing `.env.example` structure to preserve

### 2. Implement the Generator

#### Python (pydantic-settings)

Create `scripts/generate_env_example.py`:

```python
#!/usr/bin/env python3
"""Generate .env.example from Settings classes.

Auto-generated — run: just gen-env (or: python scripts/generate_env_example.py)
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path
from typing import Any, get_args, get_origin

from pydantic import SecretStr

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))  # adjust to your package layout

# Import your settings classes
from myapp.settings import AppSettings  # noqa: E402


# ── Helpers ──────────────────────────────────────────────────────────────────

def _default(field_info) -> str:
    from pydantic_core import PydanticUndefined
    d = field_info.default
    if d is None or d is PydanticUndefined:
        return ""
    if hasattr(d, "value"):          # enum
        return str(d.value)
    if isinstance(d, bool):
        return str(d).lower()
    if isinstance(d, list | tuple):  # complex — omit
        return ""
    return str(d)


def _is_secret(field_type) -> bool:
    if field_type is SecretStr:
        return True
    origin = get_origin(field_type)
    if origin is not None and SecretStr in get_args(field_type):
        return True
    return False


def _is_required(field_info) -> bool:
    return field_info.default is ... or (
        field_info.default is None and field_info.is_required()
    )


def _wrap(description: str, width: int = 78) -> list[str]:
    return [f"# {line}" for line in textwrap.wrap(description, width - 2)]


# ── Section generator ─────────────────────────────────────────────────────────

def settings_section(
    cls,
    section_name: str,
    prefix: str = "",
    description: str | None = None,
    exclude: set[str] | None = None,  # fields to omit (dynamic, per-request, etc.)
) -> list[str]:
    lines: list[str] = [
        "# " + "=" * 76,
        f"# {section_name}",
        "# " + "=" * 76,
    ]
    if description:
        lines.append(f"# {description}")
    lines.append("")

    for name, info in cls.model_fields.items():
        if exclude and name in exclude:
            continue

        field_type = cls.__annotations__.get(name, str)
        env_name = f"{prefix}{name.upper()}"
        description = info.description or ""
        marker = ""
        if _is_required(info):
            marker = "[REQUIRED] "
        elif _is_secret(field_type) and _default(info) == "":
            marker = "[REQUIRED when using this feature] "

        if description:
            lines.extend(_wrap(marker + description))

        lines.append(f"{env_name}=" if _is_secret(field_type) else f"{env_name}={_default(info)}")
        lines.append("")

    return lines


# ── Main generator ────────────────────────────────────────────────────────────

def generate() -> str:
    lines: list[str] = []

    # ── File header (always preserved — add fixed warnings here) ─────────────
    lines.extend([
        "# " + "=" * 76,
        "# MY APP — ENVIRONMENT CONFIGURATION",
        "# " + "=" * 76,
        "#",
        "# AUTO-GENERATED from Settings classes. Do not edit manually.",
        "# Regenerate: just gen-env",
        "#",
        "# Copy to .env and fill in your values.",
        "# Required variables are marked [REQUIRED].",
        "# " + "=" * 76,
        "",
        # Add persistent warnings here — they survive regeneration
        "# " + "=" * 76,
        "# SECURITY WARNING",
        "# " + "=" * 76,
        "#",
        "# <Add any deployment/security warnings here — they stay across regenerations>",
        "#",
        "",
    ])

    # ── Settings sections ─────────────────────────────────────────────────────
    lines.extend(settings_section(
        AppSettings,
        "APPLICATION",
        description="Core application settings.",
    ))

    # Example: exclude a field that's discovered at runtime, not configured upfront
    # lines.extend(settings_section(
    #     GitHubAppSettings,
    #     "GITHUB APP",
    #     prefix="GITHUB_",
    #     description="GitHub App credentials. See docs/github-app-setup.md",
    #     exclude={"installation_id"},  # discovered from webhook payloads
    # ))

    return "\n".join(lines)


# ── Idempotent .env sync ──────────────────────────────────────────────────────

def parse_env(path: Path) -> dict[str, str]:
    """Parse .env into {KEY: value}, skipping comments."""
    if not path.exists():
        return {}
    vars: dict[str, str] = {}
    for line in path.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            vars[k.strip()] = v.strip()
    return vars


def sync_env(example: Path, env: Path) -> None:
    """Sync .env from .env.example — preserves existing values, adds new."""
    existing = parse_env(env)
    template_keys: set[str] = set()
    out: list[str] = []

    for line in example.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            out.append(line)
            continue
        if "=" in line:
            k, _, default = line.partition("=")
            k = k.strip()
            template_keys.add(k)
            out.append(f"{k}={existing[k]}" if k in existing else f"{k}={default.strip()}")
        else:
            out.append(line)

    # Preserve vars that exist in .env but not in the template
    extra = {k: v for k, v in existing.items() if k not in template_keys}
    if extra:
        out += [
            "",
            "# " + "=" * 76,
            "# EXTERNAL / UNMANAGED VARIABLES",
            "# " + "=" * 76,
            "# Not defined in settings classes. Review periodically.",
            "",
            *[f"{k}={v}" for k, v in sorted(extra.items())],
            "",
        ]

    env.write_text("\n".join(out))
    new_keys = [k for k in template_keys if k not in existing]
    print(f"✅ Synced .env  ({len(existing)} preserved, {len(new_keys)} added)")
    if extra:
        print(f"⚠️  {len(extra)} unmanaged vars preserved: {', '.join(sorted(extra))}")


def main() -> None:
    content = generate()
    example = PROJECT_ROOT / ".env.example"
    env = PROJECT_ROOT / ".env"

    example.write_text(content)
    n = sum(1 for l in content.splitlines() if "=" in l and not l.strip().startswith("#"))
    print(f"✅ Generated .env.example  ({n} variables)")

    if env.exists():
        sync_env(example, env)
    else:
        env.write_text(content)
        print("✅ Created .env from template — fill in secret values")


if __name__ == "__main__":
    main()
```

#### TypeScript (zod / t3-env)

For TypeScript projects, put validation in `src/env.ts`:

```typescript
import { createEnv } from "@t3-oss/env-nextjs"; // or env-core
import { z } from "zod";

export const env = createEnv({
  server: {
    DATABASE_URL: z.string().url(),
    API_SECRET: z.string().min(1),
    // optional with default:
    LOG_LEVEL: z.enum(["debug", "info", "warn", "error"]).default("info"),
  },
  runtimeEnv: process.env,
});
```

Generate `.env.example` by walking the schema:

```typescript
// scripts/gen-env.ts
import { env } from "../src/env";
// introspect zod schema shape and emit KEY= lines with descriptions from .describe()
```

#### Go (envconfig / kelseyhightower)

```go
type Config struct {
    DatabaseURL string `envconfig:"DATABASE_URL" required:"true" desc:"PostgreSQL connection string"`
    LogLevel    string `envconfig:"LOG_LEVEL"    default:"info"  desc:"debug|info|warn|error"`
}
```

Use `envconfig.Usage()` to dump the schema, then pipe to a generator script.

---

### 3. Wire up the just/make recipe

```makefile
# justfile
# Regenerate .env.example and sync .env idempotently
gen-env:
    uv run python scripts/generate_env_example.py
```

Or Makefile:
```makefile
gen-env:
	python scripts/generate_env_example.py
```

### 4. Add to gitignore and git

```bash
# .gitignore — .env must be gitignored
echo ".env" >> .gitignore

# .env.example MUST be committed
git add .env.example scripts/generate_env_example.py justfile
git commit -m "chore: add auto-generated env management"
```

### 5. Field Design Patterns

**Dynamic / per-request fields — exclude from .env.example:**

Some values aren't configured upfront but discovered at runtime (e.g., a GitHub App
`installation_id` comes from webhook payloads, not a fixed deployment secret).
Use the `exclude` parameter to hide these from the template:

```python
settings_section(
    GitHubAppSettings,
    prefix="GITHUB_",
    exclude={"installation_id"},  # discovered from webhooks
)
```

**Secrets vs non-secrets:**

```python
# Secret — always emitted as KEY= (never show default)
api_key: SecretStr = Field(description="...")

# Non-secret — emitted as KEY=default_value
log_level: str = Field(default="info", description="...")
```

**Required marker:**

Fields with no default get `[REQUIRED]` prepended to their description automatically.
Fields with `SecretStr` and no default get `[REQUIRED when using this feature]`.

### 6. Persistent Header Sections

Content added directly to the `generate()` header (security warnings, usage notes) survives
every regeneration because it's in code, not in the generated file:

```python
lines.extend([
    "# " + "=" * 76,
    "# SECURITY WARNING",
    "# " + "=" * 76,
    "#",
    "# Dashboard has no built-in auth — rely on network isolation.",
    "#",
    "",
])
```

---

## Key Properties

| Property | Behaviour |
|----------|-----------|
| Existing `.env` values | **Never overwritten** — always preserved |
| New variables in template | Added with defaults |
| Variables removed from template | **Kept** in `EXTERNAL / UNMANAGED` section |
| Secret fields (`SecretStr`) | Always emitted as `KEY=` (no default exposed) |
| Excluded fields | Silently omitted from template |
| Header warnings/comments | Live in code — survive every regeneration |

---

## Report

After implementing:

```markdown
## Env Management Setup

**Generator:** `scripts/generate_env_example.py`
**Recipe:** `just gen-env`
**Variables documented:** <N>

**Sections:**
- <Section name> (<N> vars, prefix: PREFIX_)
- ...

**Excluded fields (dynamic):**
- <FIELD_NAME> — reason

**Next steps:**
- Run `just gen-env` after adding any new settings field
- Commit `.env.example` to git — it is the canonical reference
- Never commit `.env` — it is gitignored
```

---

## Related Skills

- `sdlc/centralized-configuration` — Philosophy and cross-language patterns
- `sdlc/macos-keychain-secrets` — Securely storing secrets on macOS
