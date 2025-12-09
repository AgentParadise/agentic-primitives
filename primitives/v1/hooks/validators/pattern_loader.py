#!/usr/bin/env python3
"""
Pattern Loader Utility

Loads security patterns from YAML files for use by validators.
Pure Python with optional PyYAML support.
"""

import re
from pathlib import Path
from typing import Any

# Try to import PyYAML, fall back to basic parser
try:
    import yaml

    def load_yaml(path: Path) -> dict[str, Any]:
        """Load YAML file using PyYAML."""
        return yaml.safe_load(path.read_text())

except ImportError:
    # Basic YAML parser for simple pattern files
    # This is a fallback - production should use PyYAML
    def load_yaml(path: Path) -> dict[str, Any]:
        """
        Basic YAML parser for pattern files.
        Only handles the specific structure of our pattern files.
        """
        content = path.read_text()
        result: dict[str, Any] = {}
        current_section: str | None = None
        current_list: list[dict[str, Any]] = []
        current_item: dict[str, Any] = {}

        for line in content.split("\n"):
            stripped = line.strip()

            # Skip comments and empty lines
            if not stripped or stripped.startswith("#"):
                continue

            # Top-level key (no indentation)
            if not line.startswith(" ") and stripped.endswith(":"):
                if current_section and current_list:
                    result[current_section] = current_list
                current_section = stripped[:-1]
                current_list = []
                current_item = {}
                continue

            # List item start
            if stripped.startswith("- "):
                if current_item:
                    current_list.append(current_item)
                current_item = {}
                # Handle inline key: value after -
                rest = stripped[2:].strip()
                if ":" in rest:
                    key, value = rest.split(":", 1)
                    current_item[key.strip()] = _parse_value(value.strip())
                continue

            # Key: value in item
            if ":" in stripped and current_item is not None:
                key, value = stripped.split(":", 1)
                current_item[key.strip()] = _parse_value(value.strip())

        # Don't forget last item and section
        if current_item:
            current_list.append(current_item)
        if current_section and current_list:
            result[current_section] = current_list

        return result

    def _parse_value(value: str) -> Any:
        """Parse a YAML value."""
        if not value:
            return None
        # Remove quotes
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            return value[1:-1]
        # Boolean
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False
        # Try number
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            return value


def load_blocked_patterns(
    patterns_file: Path,
) -> list[tuple[re.Pattern[str], str, str, str]]:
    """
    Load blocked patterns from YAML file.

    Returns:
        List of (compiled_regex, description, risk_level, id)
    """
    data = load_yaml(patterns_file)

    patterns = []
    for p in data.get("blocked", []):
        try:
            compiled = re.compile(p["pattern"], re.IGNORECASE)
            patterns.append(
                (
                    compiled,
                    p.get("description", ""),
                    p.get("risk_level", "critical"),
                    p.get("id", "unknown"),
                )
            )
        except re.error as e:
            # Log but don't fail on invalid patterns
            print(f"Warning: Invalid pattern '{p.get('id', 'unknown')}': {e}")

    return patterns


def load_suspicious_patterns(
    patterns_file: Path,
) -> list[tuple[re.Pattern[str], str, str, str]]:
    """
    Load suspicious patterns from YAML file.

    Returns:
        List of (compiled_regex, description, risk_level, id)
    """
    data = load_yaml(patterns_file)

    patterns = []
    for p in data.get("suspicious", []):
        try:
            compiled = re.compile(p["pattern"], re.IGNORECASE)
            patterns.append(
                (
                    compiled,
                    p.get("description", ""),
                    p.get("risk_level", "medium"),
                    p.get("id", "unknown"),
                )
            )
        except re.error as e:
            print(f"Warning: Invalid pattern '{p.get('id', 'unknown')}': {e}")

    return patterns


def load_all_patterns(
    patterns_file: Path,
) -> tuple[
    list[tuple[re.Pattern[str], str, str, str]],
    list[tuple[re.Pattern[str], str, str, str]],
]:
    """
    Load both blocked and suspicious patterns.

    Returns:
        Tuple of (blocked_patterns, suspicious_patterns)
    """
    return load_blocked_patterns(patterns_file), load_suspicious_patterns(patterns_file)


def load_file_patterns(
    patterns_file: Path,
) -> dict[str, Any]:
    """
    Load file validation patterns (blocked paths, sensitive patterns, content patterns).

    Returns:
        Dict with 'blocked_paths', 'sensitive_paths', 'sensitive_file_patterns',
        'sensitive_content_patterns' keys.
    """
    data = load_yaml(patterns_file)

    result: dict[str, Any] = {
        "blocked_paths": [],
        "sensitive_paths": [],
        "sensitive_file_patterns": [],
        "sensitive_content_patterns": [],
    }

    # Blocked paths
    for p in data.get("blocked_paths", []):
        result["blocked_paths"].append(p.get("path", ""))

    # Sensitive paths
    for p in data.get("sensitive_paths", []):
        result["sensitive_paths"].append(p.get("path", ""))

    # Sensitive file patterns
    for p in data.get("sensitive_file_patterns", []):
        try:
            compiled = re.compile(p["pattern"], re.IGNORECASE)
            result["sensitive_file_patterns"].append(
                (compiled, p.get("description", ""))
            )
        except re.error as e:
            print(f"Warning: Invalid file pattern '{p.get('id', 'unknown')}': {e}")

    # Sensitive content patterns
    for p in data.get("sensitive_content_patterns", []):
        try:
            compiled = re.compile(p["pattern"])
            result["sensitive_content_patterns"].append(
                (compiled, p.get("description", ""))
            )
        except re.error as e:
            print(f"Warning: Invalid content pattern '{p.get('id', 'unknown')}': {e}")

    return result


def load_pii_patterns(
    patterns_file: Path,
) -> tuple[
    list[tuple[re.Pattern[str], str, str]],
    list[tuple[re.Pattern[str], str]],
]:
    """
    Load PII detection patterns.

    Returns:
        Tuple of (pii_patterns, context_patterns)
        pii_patterns: List of (compiled_regex, pii_type, risk_level)
        context_patterns: List of (compiled_regex, context_type)
    """
    data = load_yaml(patterns_file)

    pii_patterns = []
    for p in data.get("pii_patterns", []):
        try:
            compiled = re.compile(p["pattern"], re.IGNORECASE)
            pii_patterns.append(
                (
                    compiled,
                    p.get("description", ""),
                    p.get("risk_level", "medium"),
                )
            )
        except re.error as e:
            print(f"Warning: Invalid PII pattern '{p.get('id', 'unknown')}': {e}")

    context_patterns = []
    for p in data.get("context_patterns", []):
        try:
            compiled = re.compile(p["pattern"], re.IGNORECASE)
            context_patterns.append(
                (compiled, p.get("description", ""))
            )
        except re.error as e:
            print(f"Warning: Invalid context pattern '{p.get('id', 'unknown')}': {e}")

    return pii_patterns, context_patterns


# Module self-test
if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("Usage: pattern_loader.py <patterns_file.yaml>")
        sys.exit(1)

    patterns_file = Path(sys.argv[1])
    if not patterns_file.exists():
        print(f"File not found: {patterns_file}")
        sys.exit(1)

    data = load_yaml(patterns_file)
    print(json.dumps(data, indent=2, default=str))
