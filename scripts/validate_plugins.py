#!/usr/bin/env python3
"""Validate plugin structure and metadata.

Usage:
    python scripts/validate_plugins.py [plugin_path]
    python scripts/validate_plugins.py  # validates all plugins in plugins/
"""

import json
import sys
from pathlib import Path


REQUIRED_FIELDS = ["name", "version", "description"]


def validate_plugin_json(plugin_json_path: Path) -> tuple[bool, list[str]]:
    """Validate a plugin.json file."""
    errors = []

    if not plugin_json_path.exists():
        return False, [f"Missing {plugin_json_path}"]

    try:
        with open(plugin_json_path) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return False, [f"Invalid JSON: {e}"]

    # Check required fields
    for field in REQUIRED_FIELDS:
        if field not in data:
            errors.append(f"Missing required field: {field}")

    # Validate version is SemVer
    version = data.get("version", "")
    if version and len(version.split(".")) != 3:
        errors.append(f"Version must be SemVer (X.Y.Z), got: {version}")

    return len(errors) == 0, errors


def validate_plugin_structure(plugin_path: Path) -> tuple[bool, list[str]]:
    """Validate plugin directory structure."""
    errors = []

    # Check for plugin.json
    plugin_json = plugin_path / ".claude-plugin" / "plugin.json"
    ok, json_errors = validate_plugin_json(plugin_json)
    errors.extend(json_errors)

    # Check for CHANGELOG.md
    changelog = plugin_path / "CHANGELOG.md"
    if not changelog.exists():
        errors.append(f"Missing CHANGELOG.md")
    elif changelog.stat().st_size == 0:
        errors.append(f"CHANGELOG.md is empty")

    return len(errors) == 0, errors


def validate_all_plugins(base_path: Path = None) -> bool:
    """Validate all plugins in the repository."""
    if base_path is None:
        base_path = Path("plugins")

    if not base_path.exists():
        print(f"❌ Plugin directory not found: {base_path}")
        return False

    plugin_jsons = list(base_path.glob("**/.claude-plugin/plugin.json"))

    if not plugin_jsons:
        print(f"✓ No plugins found in {base_path}")
        return True

    all_valid = True

    for plugin_json in plugin_jsons:
        plugin_path = plugin_json.parent.parent
        ok, errors = validate_plugin_structure(plugin_path)

        if not ok:
            all_valid = False
            print(f"❌ {plugin_path}:")
            for error in errors:
                print(f"   {error}")
        else:
            print(f"✓ {plugin_path}")

    return all_valid


def main():
    """Main entry point."""
    if len(sys.argv) > 1:
        # Validate specific plugin
        plugin_path = Path(sys.argv[1])
        ok, errors = validate_plugin_structure(plugin_path)

        if not ok:
            print(f"❌ Validation failed:")
            for error in errors:
                print(f"   {error}")
            sys.exit(1)
        else:
            print(f"✓ {plugin_path} is valid")
            sys.exit(0)
    else:
        # Validate all plugins
        if validate_all_plugins():
            print("\n✓ All plugins valid")
            sys.exit(0)
        else:
            print("\n❌ Plugin validation failed")
            sys.exit(1)


if __name__ == "__main__":
    main()
