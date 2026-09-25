"""Compose durable capture with existing Claude settings without overriding policy."""

from __future__ import annotations

import json

from agentic_session_store.child_hook import _parse
from agentic_session_store.hook_command import (
    HARNESS_TIMEOUT_SECONDS,
    LEGACY_COMMANDS,
    HookHarness,
    guarded_command,
)

TOOL_MATCHER = "^(Agent|Task)$"


def _group(*, deny: bool, matcher: str | None = TOOL_MATCHER) -> dict[str, object]:
    group: dict[str, object] = {
        "hooks": [
            {
                "type": "command",
                "command": guarded_command(HookHarness.CLAUDE, deny=deny),
                "timeout": HARNESS_TIMEOUT_SECONDS,
            }
        ]
    }
    if matcher is not None:
        group = {"matcher": matcher, **group}
    return group


# SubagentStop matches on agent type; no matcher settles every native child.
CAPTURE_GROUPS: dict[str, dict[str, object]] = {
    "PreToolUse": _group(deny=True),
    "PostToolUse": _group(deny=False),
    "PostToolUseFailure": _group(deny=False),
    "SubagentStop": _group(deny=False, matcher=None),
}


def _legacy(group: object) -> bool:
    if not isinstance(group, dict) or group.get("matcher") != TOOL_MATCHER:
        return False
    hooks = group.get("hooks")
    return (
        isinstance(hooks, list)
        and len(hooks) == 1
        and isinstance(hooks[0], dict)
        and hooks[0].get("command") in LEGACY_COMMANDS
    )


def merge_capture_hooks(content: str) -> str:
    document = _parse(content) if content.strip() else {}
    if document.get("disableAllHooks") is True:
        raise ValueError("Claude hooks are explicitly disabled")
    hooks = document.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise TypeError("Claude hooks must be an object")
    changed = False
    for event, expected in CAPTURE_GROUPS.items():
        groups = hooks.setdefault(event, [])
        if not isinstance(groups, list):
            raise TypeError("Claude hook event must contain matcher groups")
        if expected in groups:
            continue
        # An unguarded recorder from an older install fails open; replace it
        # in place rather than running both.
        legacy = next((i for i, group in enumerate(groups) if _legacy(group)), None)
        if legacy is None:
            groups.append(expected)
        else:
            groups[legacy] = expected
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
