#!/usr/bin/env python3
"""
Bash Command Validator

Atomic validator that checks shell commands for dangerous patterns.
Pure function - no side effects, no analytics, no stdin/stdout handling.

Patterns are loaded from patterns/bash.patterns.yaml for easier maintenance.
"""

import re
from pathlib import Path
from typing import Any

# Load patterns from YAML file
PATTERNS_FILE = Path(__file__).parent / "patterns" / "bash.patterns.yaml"

# Try to load from YAML, fall back to hardcoded patterns if file not found
try:
    from ..pattern_loader import load_all_patterns

    DANGEROUS_PATTERNS, SUSPICIOUS_PATTERNS = load_all_patterns(PATTERNS_FILE)
except (ImportError, FileNotFoundError):
    # Fallback to hardcoded patterns (for standalone usage or missing YAML)
    _DANGEROUS_RAW: list[tuple[str, str]] = [
        (r"\brm\s+-rf\s+/(?!\w)", "rm -rf / (root deletion)"),
        (r"\brm\s+-rf\s+~", "rm -rf ~ (home deletion)"),
        (r"\brm\s+-rf\s+\*", "rm -rf * (wildcard deletion)"),
        (r"\brm\s+-rf\s+\.\.(?:\s|$)", "rm -rf .. (parent deletion)"),
        (r"\brm\s+-rf\s+\.(?:\s|$)", "rm -rf . (current dir deletion)"),
        (r"\bdd\s+if=.*of=/dev/(sd|hd|nvme)", "disk overwrite"),
        (r"\bmkfs\.", "filesystem format"),
        (r">\s*/dev/(sd|hd|nvme)", "direct disk write"),
        (r":\(\)\s*\{.*:\|:&.*\}", "fork bomb"),
        (r"\bkill\s+-9\s+-1", "kill all processes"),
        (r"\bkillall\s+-9", "killall -9"),
        (r"\bchmod\s+-R\s+777\s+/(?!\w)", "chmod 777 / (insecure permissions)"),
        (r"\bchmod\s+-R\s+000\s+/(?!\w)", "chmod 000 / (lockout)"),
        (r"\bchown\s+-R.*:.*\s+/(?!\w)", "chown -R / (ownership change)"),
        (r"\bcurl.*\|\s*(ba)?sh", "curl pipe to shell"),
        (r"\bwget.*\|\s*(ba)?sh", "wget pipe to shell"),
        (r"\bcurl.*\|\s*python", "curl pipe to python"),
        (r"\bgit\s+push\s+.*--force", "force push"),
        (r"\bgit\s+reset\s+--hard\s+origin", "hard reset to origin"),
        (r"\bgit\s+clean\s+-fdx", "git clean all"),
        (r"\bgit\s+add\s+-A(?:\s|$)", "git add -A (adds all files including secrets)"),
        (r"\bgit\s+add\s+\.(?:\s|$)", "git add . (adds all files including secrets)"),
        (r"\bnc\s+-l.*-e\s*/bin/(ba)?sh", "netcat shell"),
        (r"\biptables\s+-F", "flush firewall"),
    ]
    _SUSPICIOUS_RAW: list[tuple[str, str]] = [
        (r"\bsudo\s+", "sudo usage"),
        (r"\bsu\s+-", "switch user"),
        (r"\beval\s+", "eval usage"),
        (r"\bexec\s+", "exec usage"),
        (r">\s*/etc/", "write to /etc"),
        (r"\bsystemctl\s+(stop|disable|mask)", "systemctl stop/disable"),
        (r"\bservice\s+.*stop", "service stop"),
        (r"\benv\s+.*=.*\s+(ba)?sh", "env injection"),
    ]

    # Convert to compiled patterns with metadata
    DANGEROUS_PATTERNS = [
        (re.compile(p, re.IGNORECASE), d, "critical", f"fallback-{i}")
        for i, (p, d) in enumerate(_DANGEROUS_RAW)
    ]
    SUSPICIOUS_PATTERNS = [
        (re.compile(p, re.IGNORECASE), d, "medium", f"fallback-{i}")
        for i, (p, d) in enumerate(_SUSPICIOUS_RAW)
    ]


def validate(
    tool_input: dict[str, Any], context: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Validate a bash command for dangerous patterns.

    Args:
        tool_input: {"command": "the shell command"}
        context: Optional context (unused in this validator)

    Returns:
        {"safe": bool, "reason": str | None, "metadata": dict | None}
    """
    command = tool_input.get("command", "")

    if not command:
        return {"safe": True}

    # Check dangerous patterns (block)
    for pattern, description, risk_level, pattern_id in DANGEROUS_PATTERNS:
        if pattern.search(command):
            return {
                "safe": False,
                "reason": f"Dangerous command blocked: {description}",
                "metadata": {
                    "pattern_id": pattern_id,
                    "pattern": pattern.pattern,
                    "command_preview": command[:100],
                    "risk_level": risk_level,
                },
            }

    # Check suspicious patterns (warn but don't block)
    suspicious: list[dict[str, str]] = []
    for pattern, description, risk_level, pattern_id in SUSPICIOUS_PATTERNS:
        if pattern.search(command):
            suspicious.append({
                "pattern_id": pattern_id,
                "description": description,
                "risk_level": risk_level,
            })

    return {
        "safe": True,
        "reason": None,
        "metadata": {
            "suspicious_patterns": [s["description"] for s in suspicious],
            "suspicious_details": suspicious,
            "risk_level": "low" if not suspicious else "medium",
        }
        if suspicious
        else None,
    }


# Standalone testing
if __name__ == "__main__":
    import json
    import sys

    input_data = ""
    if not sys.stdin.isatty():
        input_data = sys.stdin.read()

    if input_data:
        tool_input = json.loads(input_data)
        result = validate(tool_input)
        print(json.dumps(result))
    else:
        # Interactive test mode
        print(json.dumps({"safe": True, "message": "No input provided"}))
