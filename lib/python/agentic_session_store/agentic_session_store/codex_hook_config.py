"""Compose capture hooks with existing Codex configuration without replacing it."""

from __future__ import annotations

import tomllib
from collections.abc import MutableMapping, MutableSequence

import tomlkit

HOOK_COMMAND = "python3 -m agentic_session_store.child_hook"
EVENTS = ("PreToolUse", "PostToolUse")


def merge_capture_hooks(content: str) -> str:
    """Preserve unrelated settings and comments; repeated installation is a no-op.

    tomlkit handles both inline arrays and arrays of tables. Reparse with the
    standard library before returning, so an invalid composition is never saved.
    """
    document = tomlkit.parse(content)
    features = document.get("features", {})
    if not isinstance(features, MutableMapping):
        raise ValueError("Codex features configuration must be a table")
    if features.get("hooks") is False or features.get("codex_hooks") is False:
        raise ValueError("Codex hooks are explicitly disabled")
    hooks = document.setdefault("hooks", tomlkit.table())
    if not isinstance(hooks, MutableMapping):
        raise ValueError("Codex hooks configuration must be a table")
    changed = False
    for event in EVENTS:
        groups = hooks.setdefault(event, tomlkit.array())
        if not isinstance(groups, MutableSequence):
            raise ValueError("Codex hook event must contain matcher groups")
        expected = {
            "matcher": "spawn_agent",
            "hooks": [
                {
                    "type": "command",
                    "command": HOOK_COMMAND,
                    "timeout": 10,
                }
            ],
        }
        if any(group == expected for group in groups):
            continue
        groups.append(expected)
        changed = True
    result = tomlkit.dumps(document) if changed else content
    tomllib.loads(result)
    return result
