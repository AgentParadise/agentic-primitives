"""File operations validator.

Atomic validator that checks file operations for security issues.
Pure function - no side effects, no analytics, no stdin/stdout handling.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentic_security.constants import (
    BLOCKED_PATHS,
    SENSITIVE_PATHS,
    SENSITIVE_FILE_PATTERNS,
    RiskLevel,
)


@dataclass
class FileValidationResult:
    """Result of file operation validation."""

    safe: bool
    reason: str | None = None
    metadata: dict[str, Any] | None = None


def _hash_content(content: str) -> str:
    """Create a hash of content for logging without exposing the content."""
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _check_path_blocked(
    file_path: str,
    blocked_paths: list[str] | None = None,
) -> tuple[bool, str | None]:
    """Check if a path is in the blocked list."""
    paths_to_check = blocked_paths if blocked_paths is not None else BLOCKED_PATHS

    try:
        normalized = str(Path(file_path).expanduser().resolve())
    except (OSError, ValueError):
        # If we can't normalize the path, allow it but log
        return False, None

    for blocked in paths_to_check:
        if normalized.startswith(blocked) or normalized == blocked.rstrip("/"):
            return True, f"Blocked path: {blocked}"

    return False, None


def _check_path_sensitive(
    file_path: str,
    sensitive_paths: list[str] | None = None,
) -> tuple[bool, str | None]:
    """Check if a path is sensitive (warn but don't block)."""
    paths_to_check = sensitive_paths if sensitive_paths is not None else SENSITIVE_PATHS

    try:
        normalized = str(Path(file_path).expanduser().resolve())
    except (OSError, ValueError):
        return False, None

    for sensitive in paths_to_check:
        try:
            # Resolve both paths to handle symlinks (e.g., /var -> /private/var on macOS)
            expanded = str(Path(sensitive).expanduser())
            try:
                resolved = str(Path(sensitive).expanduser().resolve())
            except (OSError, ValueError):
                resolved = expanded

            # Check against both original and resolved paths
            if normalized.startswith(expanded) or normalized.startswith(resolved):
                return True, f"Sensitive path: {sensitive}"
        except (OSError, ValueError):
            continue

    return False, None


def _check_file_pattern(
    file_path: str,
    sensitive_patterns: list[tuple[str, str]] | None = None,
) -> tuple[bool, str | None]:
    """Check if filename or path matches sensitive patterns."""
    patterns_to_check = (
        sensitive_patterns if sensitive_patterns is not None else SENSITIVE_FILE_PATTERNS
    )

    filename = Path(file_path).name

    for pattern, description in patterns_to_check:
        # Check filename first
        if re.search(pattern, filename, re.IGNORECASE):
            return True, f"Sensitive file type: {description}"
        # Also check full path for directory-based patterns (e.g., .aws/)
        if re.search(pattern, file_path, re.IGNORECASE):
            return True, f"Sensitive file type: {description}"

    return False, None


def validate_file(
    tool_input: dict[str, Any],
    *,
    operation: str | None = None,
    extra_blocked_paths: list[str] | None = None,
    extra_sensitive_patterns: list[tuple[str, str]] | None = None,
    allow_sensitive_read: bool = True,
) -> FileValidationResult:
    """Validate a file operation for security issues.

    Args:
        tool_input: {
            "file_path": "path/to/file",  # or "path" or "target_file"
            "content": "file content",     # optional, for write operations
        }
        operation: Operation type ("Read", "Write", "Edit"). Auto-detected if not provided.
        extra_blocked_paths: Additional paths to block completely
        extra_sensitive_patterns: Additional file patterns to flag
        allow_sensitive_read: Allow reading sensitive files (redact instead of block)

    Returns:
        FileValidationResult with safe=False if operation should be blocked

    Example:
        >>> result = validate_file({"path": "/etc/passwd"}, operation="Write")
        >>> result.safe
        False
        >>> result.reason
        'Blocked path: /etc/passwd'
    """
    # Extract file path from various possible field names
    file_path = tool_input.get(
        "file_path", tool_input.get("path", tool_input.get("target_file", ""))
    )
    content = tool_input.get("content", tool_input.get("new_content", ""))

    if not file_path:
        return FileValidationResult(safe=True)

    metadata: dict[str, Any] = {"file_path": file_path}

    # Build blocked paths list
    blocked_paths = list(BLOCKED_PATHS)
    if extra_blocked_paths:
        blocked_paths.extend(extra_blocked_paths)

    # Check blocked paths (hard block)
    is_blocked, reason = _check_path_blocked(file_path, blocked_paths)
    if is_blocked:
        return FileValidationResult(
            safe=False,
            reason=reason,
            metadata={**metadata, "risk_level": RiskLevel.CRITICAL},
        )

    # Build sensitive patterns list
    sensitive_patterns = list(SENSITIVE_FILE_PATTERNS)
    if extra_sensitive_patterns:
        sensitive_patterns.extend(extra_sensitive_patterns)

    # Check sensitive file patterns
    is_sensitive_file, file_reason = _check_file_pattern(file_path, sensitive_patterns)
    if is_sensitive_file:
        # For read operations on sensitive files, allow but flag for redaction
        if operation in ("Read", "read") and allow_sensitive_read:
            return FileValidationResult(
                safe=True,
                reason=None,
                metadata={
                    **metadata,
                    "redacted": True,
                    "redact_reason": file_reason,
                    "content_hash": _hash_content(content) if content else None,
                },
            )
        # Block writes to sensitive files
        return FileValidationResult(
            safe=False,
            reason=file_reason,
            metadata={**metadata, "risk_level": RiskLevel.HIGH},
        )

    # Check sensitive paths (warn but allow)
    is_sensitive_path, path_reason = _check_path_sensitive(file_path)
    if is_sensitive_path:
        metadata["warning"] = path_reason
        metadata["risk_level"] = RiskLevel.MEDIUM

    return FileValidationResult(safe=True, reason=None, metadata=metadata if metadata else None)


# Backwards compatibility alias
validate = validate_file
