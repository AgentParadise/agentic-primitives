"""Workspace prompts, contracts, and utilities for agentic systems.

This module provides:
- Type-safe access to system prompts that define the contract
  between orchestrators (like AEF) and agents running in containerized workspaces.
- Shell utilities for safe command execution in Docker containers.

Usage:
    from agentic_workspace import Prompt, load_prompt, AEF_WORKSPACE_PROMPT

    # Type-safe loading with enum
    prompt = load_prompt(Prompt.AEF_WORKSPACE)

    # Pre-loaded constant
    print(AEF_WORKSPACE_PROMPT)

    # Shell utilities for Docker execution
    from agentic_workspace import build_bash_command, escape_for_bash

    cmd = build_bash_command(
        ["claude", "--append-system-prompt", AEF_WORKSPACE_PROMPT, "prompt"],
        merge_stderr=True
    )
    # Returns: ["bash", "-c", "claude --append-system-prompt '...' prompt 2>&1"]
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Final

from agentic_workspace.shell import build_bash_command, escape_for_bash

__all__ = [
    "AEF_WORKSPACE_PROMPT",
    # Prompts
    "Prompt",
    # Shell utilities
    "build_bash_command",
    "escape_for_bash",
    "load_prompt",
]

# Prompts directory relative to this module
_PROMPTS_DIR: Final[Path] = Path(__file__).parent / "prompts"


class Prompt(str, Enum):
    """Available workspace prompts.

    Each value corresponds to a markdown file in the prompts/ directory.
    Adding a new prompt requires:
    1. Creating the .md file in prompts/
    2. Adding the enum member here

    Mypy will enforce that only valid prompt names are used.
    """

    AEF_WORKSPACE = "aef-workspace"
    """AEF ephemeral workspace contract with artifact output instructions."""


def load_prompt(name: Prompt) -> str:
    """Load a prompt by name.

    Args:
        name: The prompt to load (type-safe via Prompt enum)

    Returns:
        The prompt content as a string

    Raises:
        FileNotFoundError: If the prompt file doesn't exist
        ValueError: If the prompt file is empty
    """
    path = _PROMPTS_DIR / f"{name.value}.md"

    if not path.exists():
        msg = f"Prompt file not found: {path}"
        raise FileNotFoundError(msg)

    content = path.read_text(encoding="utf-8").strip()

    if not content:
        msg = f"Prompt file is empty: {path}"
        raise ValueError(msg)

    return content


# Pre-loaded prompts for convenience
# These are loaded at import time for fast access
AEF_WORKSPACE_PROMPT: Final[str] = load_prompt(Prompt.AEF_WORKSPACE)
