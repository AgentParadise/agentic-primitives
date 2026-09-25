"""Compose capture hooks with existing Codex configuration without replacing it."""

from __future__ import annotations

import tomllib
from collections.abc import MutableMapping, MutableSequence
from pathlib import Path

import tomlkit

from agentic_session_store.hook_command import (
    HARNESS_TIMEOUT_SECONDS,
    LEGACY_COMMANDS,
    HookHarness,
    guarded_command,
)

TOOL_MATCHER = "^(spawn_agent|collaborationspawn_agent)$"
PRE_COMMAND = guarded_command(HookHarness.CODEX, deny=True)
REPORT_COMMAND = guarded_command(HookHarness.CODEX, deny=False)
# Kept for callers that look up the installed pre-launch command.
HOOK_COMMAND = PRE_COMMAND


def _group(command: str, matcher: str | None) -> dict[str, object]:
    group: dict[str, object] = {
        "hooks": [
            {
                "type": "command",
                "command": command,
                "timeout": HARNESS_TIMEOUT_SECONDS,
            }
        ]
    }
    if matcher is not None:
        group = {"matcher": matcher, **group}
    return group


# Codex has no PostToolUseFailure: a failed spawn fires no post hook at all.
# SubagentStop matches on agent type; no matcher settles every native child.
CAPTURE_GROUPS = {
    "PreToolUse": _group(PRE_COMMAND, TOOL_MATCHER),
    "PostToolUse": _group(REPORT_COMMAND, TOOL_MATCHER),
    "SubagentStop": _group(REPORT_COMMAND, None),
}
EVENTS = tuple(CAPTURE_GROUPS)


# Normalized identities reported by the pinned Codex 0.156.1 hooks/list API
# for exactly the handlers in CAPTURE_GROUPS (recomputed 2026-09-25).
# The offline pinned-binary test must pass whenever handler configuration changes.
CAPTURE_HASHES = {
    "PreToolUse": (
        "pre_tool_use",
        "sha256:3b7b6eb817dc719e4a294da45a6a6c615aae418dc898b0d992fda15be4089000",
    ),
    "PostToolUse": (
        "post_tool_use",
        "sha256:eb0425bbd4fce50fdc4873568117a971188f4e085964b68ddccddb5aada926a5",
    ),
    "SubagentStop": (
        "subagent_stop",
        "sha256:355a2a04f5df279bab0c798b4ea69c97d7a532f349fb62ea5b46a032ea64051f",
    ),
}


def _trust_capture(hooks: MutableMapping, event: str, index: int, path: Path) -> bool:
    state = hooks.setdefault("state", tomlkit.table())
    if not isinstance(state, MutableMapping):
        raise TypeError("Codex hook state must be a table")
    label, digest = CAPTURE_HASHES[event]
    key = f"{path.resolve()}:{label}:{index}:0"
    entry = state.setdefault(key, tomlkit.table())
    if not isinstance(entry, MutableMapping):
        raise TypeError("Codex hook state entry must be a table")
    if entry.get("enabled") is False:
        raise ValueError("Capture hook is explicitly disabled")
    if entry.get("trusted_hash") == digest:
        return False
    entry["trusted_hash"] = digest
    return True


def _legacy(group: object) -> bool:
    if not isinstance(group, MutableMapping) or group.get("matcher") != TOOL_MATCHER:
        return False
    handlers = group.get("hooks")
    return (
        isinstance(handlers, MutableSequence)
        and len(handlers) == 1
        and isinstance(handlers[0], MutableMapping)
        and handlers[0].get("command") in LEGACY_COMMANDS
    )


def merge_capture_hooks(content: str, *, config_path: Path | None = None) -> str:
    """Preserve unrelated settings and comments; repeated installation is a no-op.

    tomlkit handles both inline arrays and arrays of tables. Reparse with the
    standard library before returning, so an invalid composition is never saved.
    An unguarded capture group from an older install is replaced at its own
    index, so its trust entry is updated rather than left for a stale handler.
    """
    document = tomlkit.parse(content)
    features = document.get("features", {})
    if not isinstance(features, MutableMapping):
        raise TypeError("Codex features configuration must be a table")
    if features.get("hooks") is False or features.get("codex_hooks") is False:
        raise ValueError("Codex hooks are explicitly disabled")
    hooks = document.setdefault("hooks", tomlkit.table())
    if not isinstance(hooks, MutableMapping):
        raise TypeError("Codex hooks configuration must be a table")
    changed = False
    for event, expected in CAPTURE_GROUPS.items():
        groups = hooks.setdefault(event, tomlkit.array())
        if not isinstance(groups, MutableSequence):
            raise TypeError("Codex hook event must contain matcher groups")
        index = next((i for i, group in enumerate(groups) if group == expected), None)
        if index is None:
            index = next((i for i, group in enumerate(groups) if _legacy(group)), None)
            if index is None:
                index = len(groups)
                groups.append(expected)
            else:
                groups[index] = expected
            changed = True
        if config_path is not None:
            changed = _trust_capture(hooks, event, index, config_path) or changed
    result = tomlkit.dumps(document) if changed else content
    tomllib.loads(result)
    return result
