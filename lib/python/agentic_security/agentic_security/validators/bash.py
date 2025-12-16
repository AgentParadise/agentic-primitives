"""Bash command validator.

Atomic validator that checks shell commands for dangerous patterns.
Pure function - no side effects, no analytics, no stdin/stdout handling.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from agentic_security.constants import (
    DANGEROUS_BASH_PATTERNS,
    GIT_DANGEROUS_PATTERNS,
    SUSPICIOUS_BASH_PATTERNS,
    RiskLevel,
)


@dataclass
class BashValidationResult:
    """Result of bash command validation."""

    safe: bool
    reason: str | None = None
    metadata: dict[str, Any] | None = None


def validate_bash(
    tool_input: dict[str, Any],
    *,
    extra_blocked_patterns: list[tuple[str, str]] | None = None,
    block_git_add_all: bool = True,
) -> BashValidationResult:
    """Validate a bash command for dangerous patterns.

    Args:
        tool_input: {"command": "the shell command"}
        extra_blocked_patterns: Additional patterns to block (regex, description)
        block_git_add_all: Whether to block `git add -A` and `git add .`

    Returns:
        BashValidationResult with safe=False if dangerous pattern detected

    Example:
        >>> result = validate_bash({"command": "rm -rf /"})
        >>> result.safe
        False
        >>> result.reason
        'Dangerous command blocked: rm -rf / (root deletion)'
    """
    command = tool_input.get("command", "")

    if not command:
        return BashValidationResult(safe=True)

    # Build pattern list
    patterns_to_check = list(DANGEROUS_BASH_PATTERNS)

    if block_git_add_all:
        patterns_to_check.extend(GIT_DANGEROUS_PATTERNS)

    if extra_blocked_patterns:
        patterns_to_check.extend(extra_blocked_patterns)

    # Check dangerous patterns
    for pattern, description in patterns_to_check:
        if re.search(pattern, command, re.IGNORECASE):
            return BashValidationResult(
                safe=False,
                reason=f"Dangerous command blocked: {description}",
                metadata={
                    "pattern": pattern,
                    "command_preview": command[:100],
                    "risk_level": RiskLevel.CRITICAL,
                },
            )

    # Check suspicious patterns (don't block, just note in metadata)
    suspicious: list[str] = []
    for pattern, description in SUSPICIOUS_BASH_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            suspicious.append(description)

    if suspicious:
        return BashValidationResult(
            safe=True,
            reason=None,
            metadata={
                "suspicious_patterns": suspicious,
                "risk_level": RiskLevel.LOW,
            },
        )

    return BashValidationResult(safe=True)


# Backwards compatibility alias
validate = validate_bash
