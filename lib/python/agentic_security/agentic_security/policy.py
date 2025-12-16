"""Security Policy configuration.

Provides a declarative way to configure security policies that can be
applied across different agent runtimes (CLI, SDK, etc.).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from agentic_security.constants import (
    BLOCKED_PATHS,
    DANGEROUS_BASH_PATTERNS,
    GIT_DANGEROUS_PATTERNS,
    SENSITIVE_CONTENT_PATTERNS,
    SENSITIVE_FILE_PATTERNS,
    ToolName,
)
from agentic_security.validators.bash import validate_bash, BashValidationResult
from agentic_security.validators.file import validate_file, FileValidationResult
from agentic_security.validators.content import validate_content, ContentValidationResult


@dataclass
class ValidationResult:
    """Unified validation result for any tool operation."""

    safe: bool
    reason: str | None = None
    metadata: dict[str, Any] | None = None
    tool_name: str | None = None

    @classmethod
    def from_bash(cls, result: BashValidationResult, tool_name: str = "Bash") -> ValidationResult:
        """Create from bash validation result."""
        return cls(
            safe=result.safe,
            reason=result.reason,
            metadata=result.metadata,
            tool_name=tool_name,
        )

    @classmethod
    def from_file(cls, result: FileValidationResult, tool_name: str = "File") -> ValidationResult:
        """Create from file validation result."""
        return cls(
            safe=result.safe,
            reason=result.reason,
            metadata=result.metadata,
            tool_name=tool_name,
        )

    @classmethod
    def from_content(cls, result: ContentValidationResult, tool_name: str = "Content") -> ValidationResult:
        """Create from content validation result."""
        return cls(
            safe=result.safe,
            reason=result.reason,
            metadata=result.metadata,
            tool_name=tool_name,
        )


@dataclass
class SecurityPolicy:
    """Declarative security policy for agent operations.

    Configures what operations should be blocked or allowed.
    Can be serialized to YAML/JSON for configuration management.

    Example:
        >>> policy = SecurityPolicy(
        ...     blocked_paths=["/etc/passwd", "~/.ssh/"],
        ...     blocked_commands=["rm -rf /"],
        ... )
        >>> result = policy.validate("Bash", {"command": "rm -rf /"})
        >>> result.safe
        False

        >>> # Load from environment
        >>> policy = SecurityPolicy.from_env()

        >>> # Create with defaults
        >>> policy = SecurityPolicy.with_defaults()
    """

    # Path-based blocking
    blocked_paths: list[str] = field(default_factory=list)
    sensitive_paths: list[str] = field(default_factory=list)

    # Command-based blocking (descriptions, not regex)
    blocked_commands: list[str] = field(default_factory=list)

    # Pattern-based blocking (custom regex patterns)
    extra_bash_patterns: list[tuple[str, str]] = field(default_factory=list)
    extra_file_patterns: list[tuple[str, str]] = field(default_factory=list)
    extra_content_patterns: list[tuple[str, str]] = field(default_factory=list)

    # Behavior toggles
    block_git_add_all: bool = True
    allow_sensitive_read: bool = True

    # Use default patterns from constants
    use_default_bash_patterns: bool = True
    use_default_file_patterns: bool = True
    use_default_content_patterns: bool = True
    use_default_blocked_paths: bool = True

    @classmethod
    def with_defaults(cls) -> SecurityPolicy:
        """Create a policy with sensible defaults.

        Uses all default patterns from constants.
        """
        return cls(
            use_default_bash_patterns=True,
            use_default_file_patterns=True,
            use_default_content_patterns=True,
            use_default_blocked_paths=True,
        )

    @classmethod
    def permissive(cls) -> SecurityPolicy:
        """Create a permissive policy (minimal blocking).

        Only blocks the most critical operations.
        """
        return cls(
            use_default_bash_patterns=True,
            use_default_file_patterns=False,
            use_default_content_patterns=False,
            use_default_blocked_paths=True,
            block_git_add_all=False,
            allow_sensitive_read=True,
        )

    @classmethod
    def strict(cls) -> SecurityPolicy:
        """Create a strict policy (maximum blocking).

        Blocks sensitive reads and git add operations.
        """
        return cls(
            use_default_bash_patterns=True,
            use_default_file_patterns=True,
            use_default_content_patterns=True,
            use_default_blocked_paths=True,
            block_git_add_all=True,
            allow_sensitive_read=False,
        )

    @classmethod
    def from_env(cls) -> SecurityPolicy:
        """Create a policy from environment variables.

        Environment variables:
            AGENTIC_SECURITY_LEVEL: "permissive", "default", or "strict"
            AGENTIC_BLOCKED_PATHS: Comma-separated list of paths
            AGENTIC_BLOCK_GIT_ADD_ALL: "true" or "false"
            AGENTIC_ALLOW_SENSITIVE_READ: "true" or "false"
        """
        level = os.environ.get("AGENTIC_SECURITY_LEVEL", "default").lower()

        if level == "permissive":
            policy = cls.permissive()
        elif level == "strict":
            policy = cls.strict()
        else:
            policy = cls.with_defaults()

        # Override with specific env vars
        blocked_paths = os.environ.get("AGENTIC_BLOCKED_PATHS", "")
        if blocked_paths:
            policy.blocked_paths = [p.strip() for p in blocked_paths.split(",") if p.strip()]

        block_git = os.environ.get("AGENTIC_BLOCK_GIT_ADD_ALL", "").lower()
        if block_git == "false":
            policy.block_git_add_all = False
        elif block_git == "true":
            policy.block_git_add_all = True

        allow_read = os.environ.get("AGENTIC_ALLOW_SENSITIVE_READ", "").lower()
        if allow_read == "false":
            policy.allow_sensitive_read = False
        elif allow_read == "true":
            policy.allow_sensitive_read = True

        return policy

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SecurityPolicy:
        """Create a policy from a dictionary (e.g., loaded from YAML)."""
        return cls(
            blocked_paths=data.get("blocked_paths", []),
            sensitive_paths=data.get("sensitive_paths", []),
            blocked_commands=data.get("blocked_commands", []),
            extra_bash_patterns=[
                (p["pattern"], p["description"])
                for p in data.get("extra_bash_patterns", [])
            ],
            extra_file_patterns=[
                (p["pattern"], p["description"])
                for p in data.get("extra_file_patterns", [])
            ],
            extra_content_patterns=[
                (p["pattern"], p["description"])
                for p in data.get("extra_content_patterns", [])
            ],
            block_git_add_all=data.get("block_git_add_all", True),
            allow_sensitive_read=data.get("allow_sensitive_read", True),
            use_default_bash_patterns=data.get("use_default_bash_patterns", True),
            use_default_file_patterns=data.get("use_default_file_patterns", True),
            use_default_content_patterns=data.get("use_default_content_patterns", True),
            use_default_blocked_paths=data.get("use_default_blocked_paths", True),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert policy to a dictionary for serialization."""
        return {
            "blocked_paths": self.blocked_paths,
            "sensitive_paths": self.sensitive_paths,
            "blocked_commands": self.blocked_commands,
            "extra_bash_patterns": [
                {"pattern": p, "description": d} for p, d in self.extra_bash_patterns
            ],
            "extra_file_patterns": [
                {"pattern": p, "description": d} for p, d in self.extra_file_patterns
            ],
            "extra_content_patterns": [
                {"pattern": p, "description": d} for p, d in self.extra_content_patterns
            ],
            "block_git_add_all": self.block_git_add_all,
            "allow_sensitive_read": self.allow_sensitive_read,
            "use_default_bash_patterns": self.use_default_bash_patterns,
            "use_default_file_patterns": self.use_default_file_patterns,
            "use_default_content_patterns": self.use_default_content_patterns,
            "use_default_blocked_paths": self.use_default_blocked_paths,
        }

    def validate(self, tool_name: str, tool_input: dict[str, Any]) -> ValidationResult:
        """Validate a tool call against this policy.

        Args:
            tool_name: Name of the tool (e.g., "Bash", "Write", "Read")
            tool_input: Tool input parameters

        Returns:
            ValidationResult with safe=False if operation should be blocked

        Example:
            >>> policy = SecurityPolicy.with_defaults()
            >>> result = policy.validate("Bash", {"command": "rm -rf /"})
            >>> result.safe
            False
        """
        # Bash validation
        if tool_name in ToolName.BASH_TOOLS:
            result = validate_bash(
                tool_input,
                extra_blocked_patterns=self.extra_bash_patterns,
                block_git_add_all=self.block_git_add_all,
            )
            return ValidationResult.from_bash(result, tool_name)

        # File operation validation
        if tool_name in ToolName.FILE_TOOLS:
            # Determine blocked paths
            blocked_paths = list(self.blocked_paths)
            if self.use_default_blocked_paths:
                blocked_paths.extend(BLOCKED_PATHS)

            result = validate_file(
                tool_input,
                operation=tool_name,
                extra_blocked_paths=blocked_paths if blocked_paths else None,
                extra_sensitive_patterns=self.extra_file_patterns if self.extra_file_patterns else None,
                allow_sensitive_read=self.allow_sensitive_read,
            )

            # Also check content if provided
            content = tool_input.get("content", tool_input.get("new_content", ""))
            if content and result.safe:
                content_result = validate_content(
                    content,
                    extra_patterns=self.extra_content_patterns if self.extra_content_patterns else None,
                )
                if not content_result.safe:
                    return ValidationResult.from_content(content_result, tool_name)

            return ValidationResult.from_file(result, tool_name)

        # Default: allow unknown tools
        return ValidationResult(safe=True, tool_name=tool_name)

    def validate_bash(self, command: str) -> ValidationResult:
        """Convenience method to validate a bash command directly."""
        return self.validate(ToolName.BASH, {"command": command})

    def validate_file_read(self, path: str) -> ValidationResult:
        """Convenience method to validate a file read."""
        return self.validate(ToolName.READ, {"path": path})

    def validate_file_write(self, path: str, content: str = "") -> ValidationResult:
        """Convenience method to validate a file write."""
        return self.validate(ToolName.WRITE, {"path": path, "content": content})
