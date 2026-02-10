"""PII validator — thin wrapper around agentic_security.

Delegates to the security package for content pattern matching. Provides the
``validate(tool_input, context)`` interface expected by the pre-tool-use handler.
"""

from __future__ import annotations

from typing import Any

from agentic_security.validators.content import validate_content


def validate(
    tool_input: dict[str, Any], context: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Validate user prompt content for PII patterns.

    Args:
        tool_input: {"content": "text to check"} or {"user_prompt": "..."}
        context: Optional context (unused)

    Returns:
        {"safe": bool, "reason": str | None, "metadata": dict | None}
    """
    content = tool_input.get("content", tool_input.get("user_prompt", ""))
    if not content:
        return {"safe": True, "reason": None, "metadata": None}

    result = validate_content(content)
    return {
        "safe": result.safe,
        "reason": result.reason,
        "metadata": result.metadata,
    }
