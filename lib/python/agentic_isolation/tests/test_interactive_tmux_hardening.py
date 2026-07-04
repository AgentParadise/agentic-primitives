"""Driver hardening tests (Codex review of PR #202).

Covers three control-plane edges in the interactive-tmux driver:

  * workspace names become registry filenames and reach `docker rm -f` /
    rmtree via the stored record, so they must be validated against a strict
    allowlist (no `..`, absolute paths, or separators);
  * `tmux send-keys -l` must be `--`-terminated so a prompt beginning with
    `-` is treated as literal text, not a tmux flag;
  * debug logs must not echo the literal prompt payload.

The driver is a single-file module under providers/; locate and import it
the same way the other interactive-tmux tests do.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


def _load_driver_module():
    here = Path(__file__).resolve()
    for ancestor in here.parents:
        candidate = (
            ancestor
            / "providers"
            / "workspaces"
            / "interactive-tmux"
            / "driver"
            / "interactive_tmux.py"
        )
        if candidate.is_file():
            spec = importlib.util.spec_from_file_location("interactive_tmux", candidate)
            assert spec is not None and spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    raise AssertionError("could not locate interactive_tmux.py driver")


driver = _load_driver_module()


class TestWorkspaceNameValidation:
    @pytest.mark.parametrize("name", ["itws-deadbeef", "abc", "a.b-c_d", "Workspace1"])
    def test_valid_names_resolve_inside_registry(self, name: str) -> None:
        path = driver._registry_path(name)
        assert path.parent == driver._WORKSPACE_REGISTRY_DIR
        assert path.name == f"{name}.json"

    @pytest.mark.parametrize("name", ["", ".", "..", "../etc", "a/b", "/abs/path", "a b", "name$"])
    def test_traversal_and_separators_rejected(self, name: str) -> None:
        with pytest.raises(ValueError):
            driver._registry_path(name)

    @pytest.mark.parametrize("name", ["..", "../../etc/passwd", "/tmp/evil"])
    def test_save_load_forget_reject_bad_names(self, name: str) -> None:
        with pytest.raises(ValueError):
            driver._load_workspace(name)
        with pytest.raises(ValueError):
            driver._forget_workspace(name)

    def test_load_rejects_record_with_mismatched_name(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(driver, "_WORKSPACE_REGISTRY_DIR", tmp_path)
        # A file at good.json whose record claims to be a different workspace.
        (tmp_path / "good.json").write_text(
            json.dumps(
                {
                    "name": "evil",
                    "container": "c",
                    "image": "i",
                    "workdir": "/w",
                    "tmux_size": [200, 50],
                    "host_throwaway_dir": "/tmp/x",
                    "enabled_agents": ["claude"],
                }
            )
        )
        with pytest.raises(ValueError, match="expected 'good'"):
            driver._load_workspace("good")


class TestSendLiteralOptionTerminator:
    def test_literal_send_is_dash_dash_terminated(self, monkeypatch) -> None:
        calls: list[tuple] = []
        monkeypatch.setattr(driver, "_docker_exec", lambda *a, **k: calls.append(a))
        driver._tmux_send_literal("itws-x", "claude", "-R dangerous looking prompt")
        args = calls[0]
        # args == (container, "tmux", "send-keys", "-t", target, "-l", "--", text)
        assert "--" in args
        assert args.index("--") == args.index("-l") + 1
        assert args[-1] == "-R dangerous looking prompt"


class TestRedactCmd:
    def test_literal_payload_redacted(self) -> None:
        cmd = ["tmux", "send-keys", "-t", "agents:claude", "-l", "--", "secret-token"]
        rendered = driver._redact_cmd(cmd)
        assert "secret-token" not in rendered
        assert "<redacted 12 chars>" in rendered
        assert "send-keys" in rendered

    def test_non_literal_command_unchanged(self) -> None:
        cmd = ["tmux", "capture-pane", "-p", "-t", "agents:claude"]
        assert driver._redact_cmd(cmd) == "tmux capture-pane -p -t agents:claude"


def test_ignore_uncopyable_skips_special_files(tmp_path: Path) -> None:
    """Auth staging must skip non-regular files (sockets/FIFOs) so a special
    file in a .git tree (e.g. a git fsmonitor .ipc socket) cannot abort the
    credential copytree. A FIFO exercises the same non-regular-file path as a
    socket without the macOS AF_UNIX path-length limit."""
    import os as _os

    (tmp_path / "config.toml").write_text("ok")
    (tmp_path / "sub").mkdir()
    _os.mkfifo(tmp_path / "fsmonitor--daemon.ipc")

    names = [p.name for p in tmp_path.iterdir()]
    skipped = driver._ignore_uncopyable(str(tmp_path), names)
    assert "fsmonitor--daemon.ipc" in skipped
    assert "config.toml" not in skipped
    assert "sub" not in skipped


def test_ignore_uncopyable_allows_regular_tree(tmp_path: Path) -> None:
    """With no special files, nothing is skipped (copytree behaves normally)."""
    (tmp_path / "auth.json").write_text("{}")
    (tmp_path / "sessions").mkdir()
    names = [p.name for p in tmp_path.iterdir()]
    assert driver._ignore_uncopyable(str(tmp_path), names) == set()
