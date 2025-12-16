"""Security constants for agent operations.

This module defines canonical patterns for detecting dangerous operations,
sensitive paths, and content that should be blocked or flagged.

These constants are the source of truth for security policies across
all agentic-primitives integrations (CLI, SDK, etc.).
"""

from __future__ import annotations

# =============================================================================
# DANGEROUS BASH PATTERNS
# Operations that should be blocked in all contexts
# =============================================================================

DANGEROUS_BASH_PATTERNS: list[tuple[str, str]] = [
    # Destructive file operations
    (r"\brm\s+-rf\s+/(?!\w)", "rm -rf / (root deletion)"),
    (r"\brm\s+-rf\s+~", "rm -rf ~ (home deletion)"),
    (r"\brm\s+-rf\s+\*", "rm -rf * (wildcard deletion)"),
    (r"\brm\s+-rf\s+\.\.(?:\s|$)", "rm -rf .. (parent deletion)"),
    (r"\brm\s+-rf\s+\.(?:\s|$)", "rm -rf . (current dir deletion)"),
    # Disk operations
    (r"\bdd\s+if=.*of=/dev/(sd|hd|nvme)", "disk overwrite"),
    (r"\bmkfs\.", "filesystem format"),
    (r">\s*/dev/(sd|hd|nvme)", "direct disk write"),
    # System destruction
    (r":\(\)\s*\{.*:\|:&.*\}", "fork bomb"),
    (r"\bkill\s+-9\s+-1", "kill all processes"),
    (r"\bkillall\s+-9", "killall -9"),
    # Permission chaos
    (r"\bchmod\s+-R\s+777\s+/(?!\w)", "chmod 777 / (insecure permissions)"),
    (r"\bchmod\s+-R\s+000\s+/(?!\w)", "chmod 000 / (lockout)"),
    (r"\bchown\s+-R.*:.*\s+/(?!\w)", "chown -R / (ownership change)"),
    # Remote code execution
    (r"\bcurl.*\|\s*(ba)?sh", "curl pipe to shell"),
    (r"\bwget.*\|\s*(ba)?sh", "wget pipe to shell"),
    (r"\bcurl.*\|\s*python", "curl pipe to python"),
    # Git dangers
    (r"\bgit\s+push\s+.*--force", "force push"),
    (r"\bgit\s+reset\s+--hard\s+origin", "hard reset to origin"),
    (r"\bgit\s+clean\s+-fdx", "git clean all"),
    # Network dangers
    (r"\bnc\s+-l.*-e\s*/bin/(ba)?sh", "netcat shell"),
    (r"\biptables\s+-F", "flush firewall"),
]

# Git-specific dangerous patterns
GIT_DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    (r"\bgit\s+add\s+-A(?:\s|$)", "git add -A (adds all files including secrets)"),
    (r"\bgit\s+add\s+\.(?:\s|$)", "git add . (adds all files including secrets)"),
]

# Patterns that warrant a warning but aren't blocked
SUSPICIOUS_BASH_PATTERNS: list[tuple[str, str]] = [
    (r"\bsudo\s+", "sudo usage"),
    (r"\bsu\s+-", "switch user"),
    (r"\beval\s+", "eval usage"),
    (r"\bexec\s+", "exec usage"),
    (r">\s*/etc/", "write to /etc"),
    (r"\bsystemctl\s+(stop|disable|mask)", "systemctl stop/disable"),
    (r"\bservice\s+.*stop", "service stop"),
    (r"\benv\s+.*=.*\s+(ba)?sh", "env injection"),
]

# =============================================================================
# BLOCKED FILE PATHS
# Paths that should never be written to
# =============================================================================

BLOCKED_PATHS: list[str] = [
    # System files (Linux)
    "/etc/passwd",
    "/etc/shadow",
    "/etc/sudoers",
    "/etc/hosts",
    # System files (macOS - /private/etc is the real path)
    "/private/etc/passwd",
    "/private/etc/shadow",
    "/private/etc/sudoers",
    "/private/etc/hosts",
    # System directories
    "/boot/",
    "/proc/",
    "/sys/",
    "/dev/",
]

# =============================================================================
# SENSITIVE FILE PATHS
# Paths that require extra scrutiny (warn but don't block by default)
# =============================================================================

SENSITIVE_PATHS: list[str] = [
    "/etc/",
    "/var/log/",
    "/tmp/",
    "/usr/",
    "/opt/",
    "~/.ssh/",
    "~/.gnupg/",
    "~/.aws/",
    "~/.config/",
]

# =============================================================================
# SENSITIVE FILE PATTERNS
# File patterns that should never be read/written by AI
# =============================================================================

SENSITIVE_FILE_PATTERNS: list[tuple[str, str]] = [
    (r"\.env(?:\.local|\.production|\.staging)?$", "environment file"),
    (r"\.pem$", "PEM certificate/key"),
    (r"\.key$", "private key"),
    (r"id_rsa(?:\.pub)?$", "SSH key"),
    (r"id_ed25519(?:\.pub)?$", "SSH key"),
    (r"\.p12$", "PKCS12 certificate"),
    (r"\.pfx$", "PFX certificate"),
    (r"credentials(?:\.json)?$", "credentials file"),
    (r"secrets\.ya?ml$", "secrets file"),
    (r"\.htpasswd$", "htpasswd file"),
    (r"\.netrc$", "netrc file"),
    (r"\.npmrc$", "npm config (may contain tokens)"),
    (r"\.pypirc$", "pypi config (may contain tokens)"),
    (r"\.aws/", "AWS config directory"),
]

# =============================================================================
# SENSITIVE CONTENT PATTERNS
# Patterns in file content that indicate sensitive data
# =============================================================================

SENSITIVE_CONTENT_PATTERNS: list[tuple[str, str]] = [
    (r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----", "private key"),
    (r"AKIA[0-9A-Z]{16}", "AWS access key"),
    (r"(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36}", "GitHub token"),
    (r"sk-[A-Za-z0-9]{48}", "OpenAI API key"),
    (r"xox[baprs]-[0-9A-Za-z-]+", "Slack token"),
    (r"sk-ant-api[0-9A-Za-z-]+", "Anthropic API key"),
]

# =============================================================================
# TOOL NAMES
# Canonical tool names used by Claude and other agents
# =============================================================================

class ToolName:
    """Canonical tool names for agent operations."""

    BASH = "Bash"
    READ = "Read"
    WRITE = "Write"
    EDIT = "Edit"
    MULTI_EDIT = "MultiEdit"
    GLOB = "Glob"
    GREP = "Grep"
    LS = "LS"
    TODO_READ = "TodoRead"
    TODO_WRITE = "TodoWrite"

    # All file operation tools
    FILE_TOOLS = frozenset({READ, WRITE, EDIT, MULTI_EDIT})

    # Tools that need bash validation
    BASH_TOOLS = frozenset({BASH})


# =============================================================================
# RISK LEVELS
# =============================================================================

class RiskLevel:
    """Risk levels for security findings."""

    CRITICAL = "critical"  # Must block, immediate danger
    HIGH = "high"  # Should block, significant risk
    MEDIUM = "medium"  # Warn, potential risk
    LOW = "low"  # Note, minor concern
