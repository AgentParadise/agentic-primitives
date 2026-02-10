"""Bash command validator — thin wrapper around agentic_security.

Delegates to the security package for pattern matching. Provides the
``validate(tool_input, context)`` interface expected by the pre-tool-use handler.
"""

from __future__ import annotations

from typing import Any

from agentic_security.validators.bash import validate_bash


def validate(
    tool_input: dict[str, Any], context: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Validate a bash command for dangerous patterns.

    Args:
        tool_input: {"command": "the shell command"}
        context: Optional context (unused)

    Returns:
        {"safe": bool, "reason": str | None, "metadata": dict | None}
    """
    result = validate_bash(tool_input)
    return {
        "safe": result.safe,
        "reason": result.reason,
        "metadata": result.metadata,
    }
