"""Claude composition preserves unrelated handlers and explicit policy."""

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from agentic_session_store.install_child_hooks import install


def test_concurrent_claude_install_preserves_settings(tmp_path):
    path = tmp_path / "settings.json"
    existing = {
        "matcher": "Bash",
        "hooks": [{"type": "command", "command": "custom-hook"}],
    }
    path.write_text(
        json.dumps(
            {
                "enabledPlugins": {"observability@agentic": True},
                "hooks": {"PreToolUse": [existing]},
            }
        )
    )
    with ThreadPoolExecutor(max_workers=4) as pool:
        changes = list(pool.map(lambda _: install(path, harness="claude"), range(8)))
    assert changes.count(True) == 1
    document = json.loads(path.read_text())
    assert document["enabledPlugins"] == {"observability@agentic": True}
    assert document["hooks"]["PreToolUse"][0] == existing
    assert len(document["hooks"]["PreToolUse"]) == 3
    assert len(document["hooks"]["PostToolUse"]) == 1
    before = path.stat()
    assert not install(path, harness="claude")
    assert path.stat().st_mtime_ns == before.st_mtime_ns


@pytest.mark.parametrize(
    "content",
    [
        '{"disableAllHooks":true}',
        '{"hooks":[]}',
        '{"hooks":{"PreToolUse":{}}}',
        '{"hooks":{},"hooks":{}}',
        "invalid",
    ],
)
def test_invalid_or_disabled_config_remains_unchanged(tmp_path, content):
    path = tmp_path / "settings.json"
    path.write_text(content)
    with pytest.raises((TypeError, ValueError)):
        install(path, harness="claude")
    assert path.read_text() == content
