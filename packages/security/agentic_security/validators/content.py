"""Content validator.

Atomic validator that checks file content for sensitive data.
Pure function - no side effects, no analytics.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any

from agentic_security.constants import (
    SENSITIVE_CONTENT_PATTERNS,
    RiskLevel,
)


@dataclass
class ContentValidationResult:
    """Result of content validation."""

    safe: bool
    reason: str | None = None
    metadata: dict[str, Any] | None = None


def _hash_content(content: str) -> str:
    """Create a hash of content for logging without exposing the content."""
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def validate_content(
    content: str,
    *,
    extra_patterns: list[tuple[str, str]] | None = None,
) -> ContentValidationResult:
    """Validate content for sensitive data patterns.

    Args:
        content: The content to validate
        extra_patterns: Additional patterns to check (regex, description)

    Returns:
        ContentValidationResult with safe=False if sensitive data detected

    Example:
        >>> result = validate_content("My key is AKIAIOSFODNN7EXAMPLE")
        >>> result.safe
        False
        >>> result.reason
        'Content contains sensitive data: AWS access key'
    """
    if not content:
        return ContentValidationResult(safe=True)

    # Build patterns list
    patterns_to_check = list(SENSITIVE_CONTENT_PATTERNS)
    if extra_patterns:
        patterns_to_check.extend(extra_patterns)

    # Check for sensitive patterns
    for pattern, description in patterns_to_check:
        if re.search(pattern, content):
            return ContentValidationResult(
                safe=False,
                reason=f"Content contains sensitive data: {description}",
                metadata={
                    "pattern_matched": description,
                    "content_hash": _hash_content(content),
                    "risk_level": RiskLevel.HIGH,
                },
            )

    return ContentValidationResult(safe=True)


# Backwards compatibility alias
validate = validate_content
