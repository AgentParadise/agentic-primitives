"""Shell command utilities for agentic workspaces.

Provides safe shell escaping for running commands in Docker containers,
especially when commands contain multi-line prompts with special characters.

Example:
    >>> from agentic_workspace import build_bash_command
    >>> cmd = ["claude", "--append-system-prompt", "Line 1\\nLine 2", "prompt"]
    >>> bash_cmd = build_bash_command(cmd, merge_stderr=True)
    >>> # Returns: ["bash", "-c", "'claude' '--append-system-prompt' 'Line 1\\nLine 2' 'prompt' 2>&1"]
"""

from __future__ import annotations

import shlex


def escape_for_bash(command: list[str]) -> str:
    """Escape a command list for safe execution in bash -c.

    Uses shlex.quote() to properly escape ALL special characters including:
    - Newlines (\\n)
    - Backticks (`)
    - Shell metacharacters ($, !, &, |, ;, etc.)
    - Quotes (both single and double)
    - Spaces and tabs

    Args:
        command: List of command arguments (e.g., ["claude", "--print", "prompt"])

    Returns:
        A properly escaped command string safe for bash -c execution.

    Example:
        >>> escape_for_bash(["echo", "hello world"])
        "echo 'hello world'"
        >>> escape_for_bash(["claude", "--prompt", "Line 1\\nLine 2"])
        "claude --prompt 'Line 1\\nLine 2'"
    """
    return " ".join(shlex.quote(arg) for arg in command)


def build_bash_command(
    command: list[str],
    *,
    merge_stderr: bool = False,
) -> list[str]:
    """Build a bash-wrapped command with proper escaping.

    Wraps a command in bash -c with proper escaping for special characters.
    Optionally redirects stderr to stdout for capturing all output.

    Args:
        command: The command to wrap (e.g., ["claude", "--print", "prompt"])
        merge_stderr: If True, adds 2>&1 to capture stderr with stdout

    Returns:
        A command list suitable for subprocess/docker exec
        (e.g., ["bash", "-c", "escaped_command 2>&1"])

    Example:
        >>> build_bash_command(["claude", "-p", "test"], merge_stderr=True)
        ['bash', '-c', "claude -p test 2>&1"]

        >>> # With multi-line prompt containing special chars
        >>> prompt = "Line 1\\nLine with `backticks`"
        >>> build_bash_command(["claude", "--append-system-prompt", prompt, "test"])
        ['bash', '-c', "claude --append-system-prompt 'Line 1\\nLine with `backticks`' test"]
    """
    escaped = escape_for_bash(command)

    if merge_stderr:
        return ["bash", "-c", f"{escaped} 2>&1"]
    else:
        return ["bash", "-c", escaped]


__all__ = ["build_bash_command", "escape_for_bash"]
