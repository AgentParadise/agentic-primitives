#!/usr/bin/env python3
"""Generate .env.example from typed Settings classes and sync .env idempotently.

Philosophy:
  - Settings classes are the single source of truth for all env vars
  - .env.example is always generated, never hand-maintained
  - .env sync never overwrites existing user values
  - Startup validation fails fast with a clear error on missing required vars

Usage:
    python scripts/generate_env_example.py
    # or
    just gen-env

Copy this file into your project's scripts/ directory and adapt:
  1. Adjust PROJECT_ROOT / sys.path for your package layout
  2. Import your Settings classes
  3. Call settings_section() for each group of vars
  4. Add any fixed header sections (security warnings, etc.) in generate()
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path
from typing import Any, get_args, get_origin

from pydantic import SecretStr

# ── Path setup ────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent.parent  # adjust to your layout
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# ── Import your settings ──────────────────────────────────────────────────────
# Replace with your actual settings classes:
#
#   from myapp.settings import AppSettings
#   from myapp.settings.github import GitHubSettings
#   from myapp.settings.database import DatabaseSettings
#
# Each class should use pydantic-settings BaseSettings with Field(description=...)
from myapp.settings import AppSettings  # noqa: E402  ← REPLACE THIS


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════

def _default_value(field_info) -> str:
    """Get the default value as a string suitable for .env output."""
    from pydantic_core import PydanticUndefined

    default = field_info.default
    if default is None or default is PydanticUndefined:
        return ""
    if hasattr(default, "value"):       # enum
        return str(default.value)
    if isinstance(default, bool):
        return str(default).lower()
    if isinstance(default, list | tuple):
        return ""                        # complex defaults: leave blank
    return str(default)


def _is_secret(field_type: type[Any]) -> bool:
    """Return True if the field type is or contains SecretStr."""
    if field_type is SecretStr:
        return True
    origin = get_origin(field_type)
    if origin is not None and SecretStr in get_args(field_type):
        return True
    return False


def _is_required(field_info) -> bool:
    """Return True if the field has no default (must be set by user)."""
    return field_info.default is ... or (
        field_info.default is None and field_info.is_required()
    )


def _comment_lines(text: str, width: int = 78) -> list[str]:
    """Wrap text into comment lines: '# wrapped text here'."""
    return [f"# {line}" for line in textwrap.wrap(text, width - 2)]


# ═════════════════════════════════════════════════════════════════════════════
# Section generator
# ═════════════════════════════════════════════════════════════════════════════

def settings_section(
    cls: type,
    section_name: str,
    prefix: str = "",
    description: str | None = None,
    exclude: set[str] | None = None,
) -> list[str]:
    """Generate .env lines for a pydantic-settings class.

    Args:
        cls:          The Settings class to introspect.
        section_name: Heading shown in the section header.
        prefix:       Env var prefix (e.g. "GITHUB_" → GITHUB_APP_ID).
        description:  Optional one-line description shown under the header.
        exclude:      Field names to skip entirely — use for values that are
                      discovered at runtime (webhook payloads, API responses)
                      rather than configured upfront. They won't appear in
                      .env.example, so users aren't confused about them.
    """
    lines: list[str] = [
        "# " + "=" * 76,
        f"# {section_name}",
        "# " + "=" * 76,
    ]
    if description:
        lines.append(f"# {description}")
    lines.append("")

    for field_name, field_info in cls.model_fields.items():
        if exclude and field_name in exclude:
            continue

        field_type = cls.__annotations__.get(field_name, str)
        env_name = f"{prefix}{field_name.upper()}"
        default = _default_value(field_info)
        desc = field_info.description or ""

        # Prepend [REQUIRED] markers
        if _is_required(field_info):
            desc = f"[REQUIRED] {desc}"
        elif _is_secret(field_type) and default == "":
            desc = f"[REQUIRED when using this feature] {desc}"

        if desc:
            lines.extend(_comment_lines(desc))

        # Secrets: always emit KEY= (never expose a default value)
        lines.append(f"{env_name}=" if _is_secret(field_type) else f"{env_name}={default}")
        lines.append("")

    return lines


# ═════════════════════════════════════════════════════════════════════════════
# Main generator
# ═════════════════════════════════════════════════════════════════════════════

def generate() -> str:
    """Build the full .env.example content.

    Edit this function to:
      - Add your settings sections
      - Write fixed header content (security warnings, deployment notes)
        that survives every regeneration because it lives here in code,
        not in the generated file.
    """
    lines: list[str] = []

    # ── File header ───────────────────────────────────────────────────────────
    lines.extend([
        "# " + "=" * 76,
        "# MY APP — ENVIRONMENT CONFIGURATION",
        "# " + "=" * 76,
        "#",
        "# AUTO-GENERATED — do not edit manually.",
        "# Regenerate: just gen-env",
        "#",
        "# Copy to .env and fill in your values.",
        "# [REQUIRED] fields must be set before the app will start.",
        "# " + "=" * 76,
        "",
    ])

    # ── Persistent sections (e.g. security warnings) ─────────────────────────
    # Add any fixed commentary here. It will survive every `just gen-env` run
    # because it's in code, not in the generated file.
    #
    # Example:
    #
    # lines.extend([
    #     "# " + "=" * 76,
    #     "# SECURITY WARNING",
    #     "# " + "=" * 76,
    #     "#",
    #     "# The dashboard has no built-in authentication. Rely on network",
    #     "# isolation or add auth at the reverse-proxy layer before exposing",
    #     "# this service publicly.",
    #     "#",
    #     "",
    # ])

    # ── Settings sections ─────────────────────────────────────────────────────
    # Call settings_section() for each group of related vars.

    lines.extend(settings_section(
        AppSettings,
        "APPLICATION",
        description="Core application settings.",
    ))

    # Example: GitHub App where installation_id is discovered from webhooks,
    # not configured upfront — so we exclude it from the template.
    #
    # lines.extend(settings_section(
    #     GitHubAppSettings,
    #     "GITHUB APP",
    #     prefix="GITHUB_",
    #     description="GitHub App credentials. See docs/github-app-setup.md",
    #     exclude={"installation_id"},   # discovered from webhook payloads
    # ))

    return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════════
# Idempotent .env sync
# ═════════════════════════════════════════════════════════════════════════════

def _parse_env(path: Path) -> dict[str, str]:
    """Parse a .env file into {KEY: value}, skipping comments and blanks."""
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    in_multiline = False
    current_key: str | None = None
    current_lines: list[str] = []

    for line in path.read_text().splitlines():
        if in_multiline:
            current_lines.append(line)
            if line.rstrip().endswith('"') and not line.rstrip().endswith('\\"'):
                if current_key:
                    result[current_key] = "\n".join(current_lines)
                current_key, current_lines, in_multiline = None, [], False
            continue

        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if "=" in line:
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip()
            if v.startswith('"') and not v.endswith('"'):
                in_multiline = True
                current_key = k
                current_lines = [v]
            else:
                result[k] = v

    return result


def sync_env(example_path: Path, env_path: Path) -> None:
    """Sync .env from .env.example without overwriting existing values.

    Behaviour:
      - Existing keys in .env → preserved exactly as-is
      - New keys in .env.example → added with their default value
      - Keys in .env but not in .env.example → kept in EXTERNAL section
    """
    existing = _parse_env(env_path)
    template_keys: set[str] = set()
    out: list[str] = []

    for line in example_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            out.append(line)
            continue

        if "=" in line:
            k, _, default = line.partition("=")
            k = k.strip()
            template_keys.add(k)
            # Use existing value if present, otherwise use template default
            out.append(f"{k}={existing[k]}" if k in existing else f"{k}={default.strip()}")
        else:
            out.append(line)

    # Keys in .env that are not in the template — preserve but flag them
    external = {k: v for k, v in existing.items() if k not in template_keys}
    if external:
        out.extend([
            "",
            "# " + "=" * 76,
            "# EXTERNAL / UNMANAGED VARIABLES",
            "# " + "=" * 76,
            "# These vars are not defined in any Settings class.",
            "# Review periodically — remove if no longer needed.",
            "",
            *[f"{k}={v}" for k, v in sorted(external.items())],
            "",
        ])

    env_path.write_text("\n".join(out))

    new_keys = [k for k in template_keys if k not in existing]
    preserved = len([k for k in existing if k in template_keys])
    print(f"✅ Synced .env  ({preserved} preserved, {len(new_keys)} added)")
    if external:
        print(f"⚠️  {len(external)} unmanaged var(s) preserved → EXTERNAL section")
        for k in sorted(external):
            print(f"   - {k}")


# ═════════════════════════════════════════════════════════════════════════════
# Entry point
# ═════════════════════════════════════════════════════════════════════════════

def main() -> None:
    content = generate()

    example_path = PROJECT_ROOT / ".env.example"
    env_path = PROJECT_ROOT / ".env"

    example_path.write_text(content)
    n_vars = sum(
        1 for line in content.splitlines()
        if "=" in line and not line.strip().startswith("#")
    )
    print(f"✅ Generated .env.example  ({n_vars} variables)")

    if env_path.exists():
        sync_env(example_path, env_path)
    else:
        env_path.write_text(content)
        print("✅ Created .env from template")
        print("   Fill in [REQUIRED] values before starting the app.")


if __name__ == "__main__":
    main()
