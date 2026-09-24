"""Composition retains user hooks, permissions and unrelated TOML types."""

import tomllib

import pytest

from agentic_session_store.codex_hook_config import HOOK_COMMAND, merge_capture_hooks


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
    for event in ("PreToolUse", "PostToolUse"):
        existing = original.get("hooks", {}).get(event, [])
        assert parsed["hooks"][event][:-1] == existing
        added = parsed["hooks"][event][-1]
        assert added["matcher"] == "^(spawn_agent|collaborationspawn_agent)$"
        assert added["hooks"][0]["command"] == HOOK_COMMAND
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
    }
    assert merge_capture_hooks(merged, config_path=path) == merged


def test_disabled_owned_hook_is_not_reenabled(tmp_path):
    path = tmp_path / "config.toml"
    merged = merge_capture_hooks("", config_path=path)
    # Set an explicit user disable on the capture handler itself.
    import tomlkit

    document = tomlkit.parse(merged)
    document["hooks"]["state"][f"{path}:pre_tool_use:0:0"]["enabled"] = False
    with pytest.raises(ValueError, match="disabled"):
        merge_capture_hooks(tomlkit.dumps(document), config_path=path)
