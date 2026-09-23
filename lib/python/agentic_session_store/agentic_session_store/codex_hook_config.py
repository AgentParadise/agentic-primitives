"""Compose capture hooks with existing Codex configuration without replacing it."""

from __future__ import annotations

import tomllib
from collections.abc import MutableMapping, MutableSequence
from pathlib import Path

import tomlkit

HOOK_COMMAND = "python3 -m agentic_session_store.child_hook"
EVENTS = ("PreToolUse", "PostToolUse")


# Normalized identities reported by the pinned Codex 0.150.1 hooks/list API.
# The offline pinned-binary test must pass whenever handler configuration changes.
CAPTURE_HASHES = {
    "PreToolUse": (
        "pre_tool_use",
        "sha256:9a034149e7c29c315ce5c38584cbddee34d8520aea923440a68277636c09c3c6",
    ),
    "PostToolUse": (
        "post_tool_use",
        "sha256:974c902411a510addfa36497c43289977bbbc73d3bd1f32ed99b57846159499b",
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


def merge_capture_hooks(content: str, *, config_path: Path | None = None) -> str:
    """Preserve unrelated settings and comments; repeated installation is a no-op.

    tomlkit handles both inline arrays and arrays of tables. Reparse with the
    standard library before returning, so an invalid composition is never saved.
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
    for event in EVENTS:
        groups = hooks.setdefault(event, tomlkit.array())
        if not isinstance(groups, MutableSequence):
            raise TypeError("Codex hook event must contain matcher groups")
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
        index = next((i for i, group in enumerate(groups) if group == expected), None)
        if index is None:
            index = len(groups)
            groups.append(expected)
            changed = True
        if config_path is not None:
            changed = _trust_capture(hooks, event, index, config_path) or changed
    result = tomlkit.dumps(document) if changed else content
    tomllib.loads(result)
    return result
