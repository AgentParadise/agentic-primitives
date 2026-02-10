"""File operations validator — thin wrapper around agentic_security.

Delegates to the security package for path and pattern checking. Provides the
``validate(tool_input, context)`` interface expected by the pre-tool-use handler.
"""

from __future__ import annotations

from typing import Any

from agentic_security.validators.file import validate_file


def validate(
    tool_input: dict[str, Any], context: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Validate a file operation for security issues.

    Args:
        tool_input: {"file_path"|"path"|"target_file": "...", "content": "..."}
        context: Optional context with hook_event_name to detect operation type

    Returns:
        {"safe": bool, "reason": str | None, "metadata": dict | None}
    """
    # Infer operation from context if available
    operation = None
    if context and "hook_event_name" in context:
        # The handler passes tool_name separately, but we can infer from input keys
        pass

    result = validate_file(tool_input, operation=operation)
    return {
        "safe": result.safe,
        "reason": result.reason,
        "metadata": result.metadata,
    }
