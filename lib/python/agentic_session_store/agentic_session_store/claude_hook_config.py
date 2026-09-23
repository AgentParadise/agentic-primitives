"""Compose durable capture with existing Claude settings without overriding policy."""

from __future__ import annotations

import json

from agentic_session_store.child_hook import _parse

HOOK_COMMAND = "python3 -m agentic_session_store.child_hook"


def merge_capture_hooks(content: str) -> str:
    document = _parse(content) if content.strip() else {}
    if document.get("disableAllHooks") is True:
        raise ValueError("Claude hooks are explicitly disabled")
    hooks = document.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise TypeError("Claude hooks must be an object")
    changed = False
    for event in ("PreToolUse", "PostToolUse"):
        groups = hooks.setdefault(event, [])
        if not isinstance(groups, list):
            raise TypeError("Claude hook event must contain matcher groups")
        expected = {
            "matcher": "^(Agent|Task)$",
            "hooks": [{"type": "command", "command": HOOK_COMMAND, "timeout": 10}],
        }
        if expected not in groups:
            groups.append(expected)
            changed = True
    context = {
        "matcher": "^Bash$",
        "hooks": [
            {
                "type": "command",
                "command": "python3 -m agentic_session_store.command_context",
                "timeout": 10,
            }
        ],
    }
    if context not in hooks["PreToolUse"]:
        hooks["PreToolUse"].append(context)
        changed = True
    return json.dumps(document, indent=2) + "\n" if changed else content
