"""Composition retains user hooks, permissions and unrelated TOML types."""

import tomllib

import pytest
import tomlkit

from agentic_session_store.codex_hook_config import (
    CAPTURE_GROUPS,
    CAPTURE_HASHES,
    PRE_COMMAND,
    REPORT_COMMAND,
    TOOL_MATCHER,
    merge_capture_hooks,
)


@pytest.mark.parametrize(
    "content",
    [
        "",
        '# Preserve this comment\nmodel="example"\n[hooks]\nPreToolUse=[]\n',
        'hooks={PreToolUse=[{matcher="Bash",hooks=[{type="command",command="user-hook"}]}]}\n',
        '[[hooks.PreToolUse]]\nmatcher="Bash"\n[[hooks.PreToolUse.hooks]]\ntype="command"\ncommand="user-hook"\n',
    ],
)
def test_merge_retains_user_configuration_and_is_idempotent(content: str) -> None:
    original = tomllib.loads(content)
    merged = merge_capture_hooks(content)
    parsed = tomllib.loads(merged)
    for event in CAPTURE_GROUPS:
        existing = original.get("hooks", {}).get(event, [])
        assert parsed["hooks"][event][:-1] == existing
        added = parsed["hooks"][event][-1]
        if event == "SubagentStop":
            assert "matcher" not in added
        else:
            assert added["matcher"] == TOOL_MATCHER
        assert added["hooks"][0]["command"] == (
            PRE_COMMAND if event == "PreToolUse" else REPORT_COMMAND
        )
        assert added["hooks"][0]["timeout"] == 30
        assert "async" not in added["hooks"][0]
    if content.startswith("#"):
        assert "# Preserve this comment" in merged
    if "model" in original:
        assert parsed["model"] == original["model"]
    assert merge_capture_hooks(merged) == merged


@pytest.mark.parametrize(
    "content", ['hooks="invalid"', "[hooks]\nPreToolUse=1", "invalid={"]
)
def test_invalid_configuration_is_not_replaced(content: str) -> None:
    with pytest.raises((ValueError, TypeError)):
        merge_capture_hooks(content)


@pytest.mark.parametrize("name", ["hooks", "codex_hooks"])
def test_explicit_disabled_hooks_are_not_silently_overridden(name: str) -> None:
    with pytest.raises(ValueError, match="disabled"):
        merge_capture_hooks(f"[features]\n{name}=false\n")


def test_trust_is_limited_to_owned_handlers_and_uses_actual_group_index(tmp_path):
    path = tmp_path / "config.toml"
    content = '[[hooks.PreToolUse]]\nmatcher="Bash"\n[[hooks.PreToolUse.hooks]]\ntype="command"\ncommand="user-hook"\n[hooks.state.user]\nenabled=false\ntrusted_hash="unchanged"\n'
    merged = merge_capture_hooks(content, config_path=path)
    state = tomllib.loads(merged)["hooks"]["state"]
    assert state["user"] == {"enabled": False, "trusted_hash": "unchanged"}
    assert set(state) == {
        "user",
        f"{path}:pre_tool_use:1:0",
        f"{path}:post_tool_use:0:0",
        f"{path}:subagent_stop:0:0",
    }
    assert merge_capture_hooks(merged, config_path=path) == merged


def test_disabled_owned_hook_is_not_reenabled(tmp_path):
    path = tmp_path / "config.toml"
    merged = merge_capture_hooks("", config_path=path)
    # Set an explicit user disable on the capture handler itself.
    document = tomlkit.parse(merged)
    document["hooks"]["state"][f"{path}:pre_tool_use:0:0"]["enabled"] = False
    with pytest.raises(ValueError, match="disabled"):
        merge_capture_hooks(tomlkit.dumps(document), config_path=path)


def test_unguarded_legacy_group_is_replaced_in_place_with_its_trust(tmp_path):
    """An older install's fail-open recorder must not keep running beside the guard."""
    path = tmp_path / "config.toml"
    legacy = (
        '[[hooks.PreToolUse]]\nmatcher="Bash"\n[[hooks.PreToolUse.hooks]]\n'
        'type="command"\ncommand="user-hook"\n'
    )
    for event in ("PreToolUse", "PostToolUse"):
        legacy += (
            f'[[hooks.{event}]]\nmatcher="{TOOL_MATCHER}"\n'
            f'[[hooks.{event}.hooks]]\ntype="command"\n'
            'command="python3 -m agentic_session_store.child_hook"\ntimeout=10\n'
        )
    legacy += f'[hooks.state."{path}:pre_tool_use:1:0"]\ntrusted_hash="sha256:old"\n'
    merged = tomllib.loads(merge_capture_hooks(legacy, config_path=path))
    hooks = merged["hooks"]
    assert hooks["PreToolUse"][0]["hooks"][0]["command"] == "user-hook"
    assert hooks["PreToolUse"][1] == CAPTURE_GROUPS["PreToolUse"]
    assert hooks["PostToolUse"] == [CAPTURE_GROUPS["PostToolUse"]]
    commands = [
        handler["command"]
        for groups in (hooks["PreToolUse"], hooks["PostToolUse"])
        for group in groups
        for handler in group["hooks"]
    ]
    assert "python3 -m agentic_session_store.child_hook" not in commands
    state = hooks["state"]
    assert (
        state[f"{path}:pre_tool_use:1:0"]["trusted_hash"]
        == (CAPTURE_HASHES["PreToolUse"][1])
    )


def test_guard_never_uses_blocking_status_after_launch():
    """Exit 2 on PostToolUse hides a running child; on SubagentStop it forces
    the child to continue. Only the pre-launch guard may deny."""
    assert PRE_COMMAND.endswith("exit 2")
    assert REPORT_COMMAND.endswith("exit 1")
    for event, group in CAPTURE_GROUPS.items():
        command = group["hooks"][0]["command"]
        assert command == (PRE_COMMAND if event == "PreToolUse" else REPORT_COMMAND)
