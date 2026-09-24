"""File replacement is idempotent and failure never destroys the old config."""

import os
import tomllib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from agentic_session_store.install_child_hooks import install


def test_concurrent_installers_keep_user_settings_and_one_hook(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('# Keep me\nmodel="user-model"\n')
    path.chmod(0o600)
    with ThreadPoolExecutor(max_workers=4) as pool:
        changes = list(pool.map(lambda _: install(path), range(8)))
    assert changes.count(True) == 1
    parsed = tomllib.loads(path.read_text())
    assert parsed["model"] == "user-model"
    assert "# Keep me" in path.read_text()
    assert len(parsed["hooks"]["PreToolUse"]) == 1
    assert len(parsed["hooks"]["PostToolUse"]) == 1
    before = path.stat()
    assert not install(path)
    assert path.stat().st_ino == before.st_ino
    assert path.stat().st_mtime_ns == before.st_mtime_ns
    assert path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("kind", ["invalid", "symlink", "directory", "oversized"])
def test_invalid_targets_remain_unchanged(tmp_path: Path, kind: str) -> None:
    path = tmp_path / "config.toml"
    original = b"invalid={"
    if kind == "symlink":
        target = tmp_path / "original"
        target.write_bytes(original)
        path.symlink_to(target)
    elif kind == "directory":
        path.mkdir()
    else:
        path.write_bytes(original if kind == "invalid" else b" " * (1024 * 1024 + 1))
    with pytest.raises((OSError, ValueError)):
        install(path)
    if kind == "symlink":
        assert path.is_symlink()
        assert path.read_bytes() == original
    elif kind == "directory":
        assert path.is_dir()
    else:
        assert path.read_bytes() == (
            original if kind == "invalid" else b" " * (1024 * 1024 + 1)
        )
    assert not list(tmp_path.glob(".capture-config-*"))


def test_replace_failure_preserves_original_and_cleans_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "config.toml"
    original = b'model="user-model"\n'
    path.write_bytes(original)

    def fail(*args: object) -> None:
        raise OSError("simulated storage failure")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError):
        install(path)
    assert path.read_bytes() == original
    assert not list(tmp_path.glob(".capture-config-*"))
