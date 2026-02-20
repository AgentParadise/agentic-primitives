#!/usr/bin/env python3
"""Generate .env.example from typed Settings classes and sync .env idempotently.

Philosophy:
  - Settings classes are the single source of truth for all env vars
  - .env.example is always generated, never hand-maintained
  - .env sync never overwrites existing user values
  - Startup validation fails fast with a clear error on missing required vars

Works in both contexts:
  - Human-in-loop (terminal): run `just gen-env`, review output, commit
  - Headless workspace: runs as part of project init, no interaction needed

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
#
from myapp.settings import AppSettings  # noqa: E402  ← REPLACE THIS


# ═════════════════════════════════════════════════════════════════════════════
# Helpers
# ═════════════════════════════════════════════════════════════════════════════

def _default_value(field_info) -> str:
    from pydantic_core import PydanticUndefined
    default = field_info.default
    if default is None or default is PydanticUndefined:
        return ""
    if hasattr(default, "value"):       # enum
        return str(default.value)
    if isinstance(default, bool):
        return str(default).lower()
    if isinstance(default, list | tuple):
        return ""
    return str(default)


def _is_secret(field_type: type[Any]) -> bool:
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


def _comment_lines(text: str, width: int = 78) -> list[str]:
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
        exclude:      Field names to skip — use for values discovered at runtime
                      (webhook payloads, API responses, per-request values).
                      Excluded fields won't appear in .env.example.
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

        if _is_required(field_info):
            desc = f"[REQUIRED] {desc}"
        elif _is_secret(field_type) and default == "":
            desc = f"[REQUIRED when using this feature] {desc}"

        if desc:
            lines.extend(_comment_lines(desc))

        lines.append(f"{env_name}=" if _is_secret(field_type) else f"{env_name}={default}")
        lines.append("")

    return lines


# ═════════════════════════════════════════════════════════════════════════════
# Main generator — edit this for your project
# ═════════════════════════════════════════════════════════════════════════════

def generate() -> str:
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

    # ── Persistent sections ───────────────────────────────────────────────────
    # Add security warnings or deployment notes here — they survive every
    # `just gen-env` because they live in code, not in the generated file.
    #
    # lines.extend([
    #     "# " + "=" * 76,
    #     "# SECURITY WARNING",
    #     "# " + "=" * 76,
    #     "#",
    #     "# <warning text>",
    #     "#",
    #     "",
    # ])

    # ── Settings sections ─────────────────────────────────────────────────────
    lines.extend(settings_section(
        AppSettings,
        "APPLICATION",
        description="Core application settings.",
    ))

    # Example with excluded dynamic field:
    #
    # lines.extend(settings_section(
    #     GitHubAppSettings,
    #     "GITHUB APP",
    #     prefix="GITHUB_",
    #     description="GitHub App credentials. See docs/github-app-setup.md",
    #     exclude={"installation_id"},  # discovered from webhook payloads
    # ))

    return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════════
# Idempotent .env sync
# ═════════════════════════════════════════════════════════════════════════════

def _parse_env(path: Path) -> dict[str, str]:
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
    """Sync .env from .env.example — preserves existing values, adds new."""
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
            out.append(f"{k}={existing[k]}" if k in existing else f"{k}={default.strip()}")
        else:
            out.append(line)

    # Preserve vars in .env that aren't in the template
    external = {k: v for k, v in existing.items() if k not in template_keys}
    if external:
        out.extend([
            "",
            "# " + "=" * 76,
            "# EXTERNAL / UNMANAGED VARIABLES",
            "# " + "=" * 76,
            "# Not defined in any Settings class. Review periodically.",
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
