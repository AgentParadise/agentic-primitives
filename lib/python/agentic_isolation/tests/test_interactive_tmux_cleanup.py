"""Driver tests: throwaway credential dirs must not leak on startup failure.

`start_workspace` stages copies of host auth material (claude/codex/gemini
credentials) into a throwaway dir under the system temp dir before running
the container. If `docker run` (or credential staging itself) fails, that
dir must be removed; leaking it leaves auth material under /tmp.

These tests exercise the failure paths WITHOUT docker: subprocess calls are
monkeypatched at the driver module level.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


# The driver lives at providers/workspaces/interactive-tmux/driver/
# interactive_tmux.py and is not a packaged module yet; locate and import
# it the same way the other interactive-tmux tests do.
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
            sys.modules.setdefault("interactive_tmux", module)
            spec.loader.exec_module(module)
            return module
    pytest.skip("interactive_tmux driver not found in repo layout")


driver = _load_driver_module()


@pytest.fixture
def fake_claude_home(tmp_path: Path) -> Path:
    """A host ~/.claude dir with just enough for the claude adapter."""
    home = tmp_path / "home"
    claude_dir = home / ".claude"
    claude_dir.mkdir(parents=True)
    (claude_dir / ".credentials.json").write_text("{}")
    (home / ".claude.json").write_text("{}")
    return claude_dir


@pytest.fixture
def recorded_throwaway_dirs(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Record every mkdtemp the driver creates so tests can assert cleanup."""
    created: list[Path] = []
    real_mkdtemp = tempfile.mkdtemp

    def recording_mkdtemp(*args, **kwargs):
        path = real_mkdtemp(*args, **kwargs)
        created.append(Path(path))
        return path

    monkeypatch.setattr(driver.tempfile, "mkdtemp", recording_mkdtemp)
    return created


@pytest.fixture
def no_real_subprocess(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Stub the driver's cleanup `subprocess.run` (docker rm) and log calls."""
    calls: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(driver.subprocess, "run", fake_run)
    return calls


class TestThrowawayDirCleanup:
    def test_docker_run_failure_removes_throwaway_dir(
        self,
        fake_claude_home: Path,
        recorded_throwaway_dirs: list[Path],
        no_real_subprocess: list[list[str]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def failing_run(cmd, check=True, capture=True, timeout_s=None):
            if cmd[:2] == ["docker", "run"]:
                raise subprocess.CalledProcessError(125, cmd)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(driver, "_run", failing_run)

        with pytest.raises(subprocess.CalledProcessError):
            driver.InteractiveTmuxWorkspace.start_workspace(
                name="leaktest",
                host_auth={"claude": fake_claude_home},
            )

        assert len(recorded_throwaway_dirs) == 1
        assert not recorded_throwaway_dirs[0].exists()
        # Best-effort container removal happened too.
        assert any(call[:3] == ["docker", "rm", "-f"] for call in no_real_subprocess)

    def test_credential_staging_failure_removes_throwaway_dir(
        self,
        tmp_path: Path,
        recorded_throwaway_dirs: list[Path],
        no_real_subprocess: list[list[str]],
    ) -> None:
        """A bad host auth dir (no .credentials.json) must not leak the dir."""
        bad_claude_dir = tmp_path / ".claude"
        bad_claude_dir.mkdir()

        with pytest.raises(FileNotFoundError):
            driver.InteractiveTmuxWorkspace.start_workspace(
                name="leaktest",
                host_auth={"claude": bad_claude_dir},
            )

        assert len(recorded_throwaway_dirs) == 1
        assert not recorded_throwaway_dirs[0].exists()

    def test_no_enabled_agents_removes_throwaway_dir(
        self,
        recorded_throwaway_dirs: list[Path],
        no_real_subprocess: list[list[str]],
    ) -> None:
        with pytest.raises(ValueError, match="no enabled agents"):
            driver.InteractiveTmuxWorkspace.start_workspace(
                name="leaktest",
                host_auth={},
            )

        assert len(recorded_throwaway_dirs) == 1
        assert not recorded_throwaway_dirs[0].exists()
