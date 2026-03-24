#!/usr/bin/env python3
"""Generate .env.example and sync .env idempotently.

This script:
1. Introspects settings classes to generate .env.example
2. Syncs .env preserving existing values
3. Adds new variables from settings
4. Detects and preserves external variables

Usage:
    python scripts/generate_env.py
    # or add to justfile:
    # gen-env:
    #     uv run python scripts/generate_env.py
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, Any, get_args, get_origin

from pydantic import SecretStr

if TYPE_CHECKING:
    from pydantic.fields import FieldInfo

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))  # Adjust path as needed


def get_default_value(field_info: FieldInfo) -> str:
    """Get default value as string for .env file."""
    from pydantic_core import PydanticUndefined

    default = field_info.default

    if default is None or default is PydanticUndefined:
        return ""

    # Handle enums
    if hasattr(default, "value"):
        return str(default.value)

    # Handle booleans
    if isinstance(default, bool):
        return str(default).lower()

    # Handle lists/tuples (skip complex defaults)
    if isinstance(default, list | tuple):
        return ""

    return str(default)


def is_secret_type(field_type: type[Any]) -> bool:
    """Check if field is a secret (shouldn't show defaults)."""
    if field_type is SecretStr:
        return True

    origin = get_origin(field_type)
    if origin is not None:
        return SecretStr in get_args(field_type)

    return False


def generate_section(
    settings_class: type,
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
    from config.github import GitHubSettings
    from config.settings import Settings

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

    # GitHub settings (GITHUB_* prefix)
    lines.extend(
        generate_section(
            GitHubSettings,
            "GITHUB",
            prefix="GITHUB_",
            description="GitHub App authentication",
        )
    )

    # Add more settings classes as needed...

    return "\n".join(lines)


def _is_multiline_end(line: str) -> bool:
    return line.rstrip().endswith('"') and not line.rstrip().endswith('\\"')


def _is_multiline_start(value: str) -> bool:
    return value.startswith('"') and not value.endswith('"')


def _handle_multiline_line(
    line: str,
    current_key: str | None,
    current_value_lines: list[str],
    env_vars: dict[str, str],
) -> tuple[str | None, list[str], bool]:
    current_value_lines.append(line)
    if _is_multiline_end(line):
        full_value = "\n".join(current_value_lines)
        if current_key:
            env_vars[current_key] = full_value
        return None, [], False
    return current_key, current_value_lines, True


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse existing .env into key=value dict.

    Handles multi-line values in quotes.
    """
    if not path.exists():
        return {}

    env_vars: dict[str, str] = {}
    current_key: str | None = None
    current_value_lines: list[str] = []
    in_multiline = False

    for line in path.read_text().split("\n"):
        if in_multiline:
            current_key, current_value_lines, in_multiline = _handle_multiline_line(
                line, current_key, current_value_lines, env_vars,
            )
            continue

        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if "=" in line:
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()

            if _is_multiline_start(value):
                in_multiline = True
                current_key = key
                current_value_lines = [value]
            else:
                env_vars[key] = value

    return env_vars


def _process_template_line(
    line: str,
    existing_vars: dict[str, str],
    template_keys: set[str],
    new_vars: list[str],
) -> str:
    key, _, default_value = line.partition("=")
    key = key.strip()
    default_value = default_value.strip()
    template_keys.add(key)

    if key in existing_vars:
        return f"{key}={existing_vars[key]}"
    new_vars.append(key)
    return f"{key}={default_value}"


def _build_external_vars_section(
    extra_vars: list[str], existing_vars: dict[str, str],
) -> list[str]:
    lines: list[str] = [
        "",
        "# " + "=" * 76,
        "# EXTERNAL / UNKNOWN VARIABLES",
        "# " + "=" * 76,
        "# These variables are not defined in settings classes.",
        "# They may come from external tools or plugins.",
        "# Review periodically - remove if no longer needed.",
        "",
    ]
    for key in sorted(extra_vars):
        lines.append(f"{key}={existing_vars[key]}")
    lines.append("")
    return lines


def sync_env_file(
    example_path: Path,
    env_path: Path,
) -> tuple[int, int, int, list[str]]:
    """Sync .env with .env.example idempotently.

    - Preserves existing values in .env
    - Adds new variables from .env.example
    - Preserves external variables with warning

    Returns:
        (existing_count, new_count, total_count, extra_vars)
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
        elif "=" in line:
            output_lines.append(
                _process_template_line(line, existing_vars, template_keys, new_vars)
            )
        else:
            output_lines.append(line)

    extra_vars = [k for k in existing_vars if k not in template_keys]
    if extra_vars:
        output_lines.extend(_build_external_vars_section(extra_vars, existing_vars))

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
        1 for line in content.split("\n") if "=" in line and not line.strip().startswith("#")
    )
    print(f"   {total_vars} environment variables documented")

    # Sync .env
    if env_path.exists():
        existing, new, _total, extra = sync_env_file(example_path, env_path)

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
