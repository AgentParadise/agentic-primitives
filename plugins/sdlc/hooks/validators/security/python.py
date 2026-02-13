#!/usr/bin/env python3
"""
Python Execution Validator

Atomic validator that checks python/python3 commands for dangerous patterns.
Validates both inline code (-c) and script execution for risky operations.
Pure function - no side effects, no analytics, no stdin/stdout handling.
"""

import re
from typing import Any

# Patterns for detecting python invocation in a bash command
PYTHON_INVOKE_RE = re.compile(r"\b(python3?|python3\.\d+)\b")

# Dangerous patterns in python inline code (-c flag)
DANGEROUS_INLINE_PATTERNS: list[tuple[str, str]] = [
    # Destructive OS operations
    (r"\bos\.system\s*\(", "os.system() call (arbitrary shell execution)"),
    (r"\bos\.popen\s*\(", "os.popen() call (arbitrary shell execution)"),
    (r"\bos\.exec[lv]p?e?\s*\(", "os.exec*() call (process replacement)"),
    (r"\bos\.remove\s*\(", "os.remove() (file deletion)"),
    (r"\bos\.unlink\s*\(", "os.unlink() (file deletion)"),
    (r"\bos\.rmdir\s*\(", "os.rmdir() (directory deletion)"),
    (r"\bshutil\.rmtree\s*\(", "shutil.rmtree() (recursive deletion)"),
    (r"\bshutil\.move\s*\(", "shutil.move() (file move)"),
    # Subprocess execution
    (r"\bsubprocess\.(run|call|check_call|check_output|Popen)\s*\(", "subprocess execution"),
    # Code injection / dynamic execution
    (r"\b__import__\s*\(", "__import__() (dynamic import)"),
    (r"\bcompile\s*\(.*exec", "compile() + exec (dynamic code execution)"),
    # Low-level system access
    (r"\bctypes\b", "ctypes (low-level memory access)"),
    # Credential / secret access
    (r"\bopen\s*\(.*\.env", "reading .env file"),
    (r"\bopen\s*\(.*id_rsa", "reading SSH key"),
    (r"\bopen\s*\(.*\.ssh", "reading .ssh directory"),
    (r"\bopen\s*\(.*\.aws", "reading AWS credentials"),
    (r"\bopen\s*\(.*\/etc\/shadow", "reading /etc/shadow"),
    (r"\bopen\s*\(.*\/etc\/passwd", "reading /etc/passwd"),
    # Network exfiltration combined with file reads
    (r"\b(urllib|requests|http\.client|socket)\b.*\bopen\b", "network + file access (potential exfiltration)"),
    (r"\bopen\b.*\b(urllib|requests|http\.client|socket)\b", "file + network access (potential exfiltration)"),
    # Reverse shells
    (r"\bsocket\b.*\bconnect\b.*\b(dup2|subprocess|os\.system)\b", "reverse shell pattern"),
]

# Suspicious but not blocked patterns
SUSPICIOUS_INLINE_PATTERNS: list[tuple[str, str]] = [
    (r"\beval\s*\(", "eval() usage"),
    (r"\bexec\s*\(", "exec() usage"),
    (r"\bglobals\s*\(\s*\)\s*\[", "globals() access"),
    (r"\bgetattr\s*\(", "getattr() (dynamic attribute access)"),
    (r"\bos\.environ", "os.environ access"),
    (r"\bos\.chmod\s*\(", "os.chmod() (permission change)"),
    (r"\bos\.chown\s*\(", "os.chown() (ownership change)"),
]


def _extract_inline_code(command: str) -> str | None:
    """Extract Python inline code from -c flag."""
    # Match: python3 -c "code" or python3 -c 'code' or python3 -c code
    match = re.search(
        r"""\b(?:python3?|python3\.\d+)\s+-c\s+(?:["'](.+?)["']|(\S+))""",
        command,
        re.DOTALL,
    )
    if match:
        return match.group(1) or match.group(2)
    return None


def validate(
    tool_input: dict[str, Any], context: dict[str, Any] | None = None
) -> dict[str, Any]:
    """
    Validate a bash command that invokes python for dangerous patterns.

    Args:
        tool_input: {"command": "the shell command"}
        context: Optional context (unused in this validator)

    Returns:
        {"safe": bool, "reason": str | None, "metadata": dict | None}
    """
    command = tool_input.get("command", "")

    if not command:
        return {"safe": True}

    # Only validate commands that invoke python
    if not PYTHON_INVOKE_RE.search(command):
        return {"safe": True}

    # Extract inline code if present
    inline_code = _extract_inline_code(command)

    # Check the full command and inline code for dangerous patterns
    targets = [command]
    if inline_code:
        targets.append(inline_code)

    for target in targets:
        for pattern, description in DANGEROUS_INLINE_PATTERNS:
            if re.search(pattern, target, re.IGNORECASE | re.DOTALL):
                return {
                    "safe": False,
                    "reason": f"Dangerous Python execution blocked: {description}",
                    "metadata": {
                        "pattern": pattern,
                        "command_preview": command[:100],
                        "risk_level": "critical",
                    },
                }

    # Check for suspicious patterns
    suspicious: list[str] = []
    for target in targets:
        for pattern, description in SUSPICIOUS_INLINE_PATTERNS:
            if re.search(pattern, target, re.IGNORECASE | re.DOTALL):
                suspicious.append(description)

    return {
        "safe": True,
        "reason": None,
        "metadata": {"suspicious_patterns": suspicious, "risk_level": "low"}
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
