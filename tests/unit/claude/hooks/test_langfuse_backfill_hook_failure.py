"""A failed hook invocation must report the status that decided it failed.

Issue #1247 was reported against the Docker isolation provider, but the same
shape lived here: `run_hook()` raised a message assembled from the child's
output alone and fell back to the words `official hook failed` when the child
wrote nothing — a sentence that tells a reader only what they already knew
from the exception being raised at all.

The subprocess is never really spawned; `subprocess.run` is monkeypatched.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = (
    REPO_ROOT / "plugins" / "observability" / "scripts" / "langfuse-backfill-claude-chunked.py"
)


def _load_script() -> Any:
    """Import the backfill script by path (its name is not a valid module)."""
    spec = importlib.util.spec_from_file_location("langfuse_backfill_chunked", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("langfuse_backfill_chunked", module)
    spec.loader.exec_module(module)
    return module


def _hook_exits_with(
    monkeypatch: pytest.MonkeyPatch,
    returncode: int,
    stderr: str = "",
    stdout: str = "",
) -> Any:
    module = _load_script()

    def _run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["uv"], returncode=returncode, stdout=stdout, stderr=stderr
        )

    monkeypatch.setattr(module.subprocess, "run", _run)
    return module


def _invoke(module: Any) -> None:
    module.run_hook(Path("/nowhere/hook.py"), Path("/nowhere/replay.jsonl"), "sess-1", {})


def test_silent_hook_failure_names_the_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    """A hook killed before it writes anything still has to be attributable.

    17 is not a status the old code could have surfaced: it built the message
    from output that, here, does not exist.
    """
    module = _hook_exits_with(monkeypatch, 17)

    with pytest.raises(RuntimeError) as excinfo:
        _invoke(module)

    message = str(excinfo.value)
    assert "17" in message
    assert "no output" in message


def test_hook_stderr_is_reported_alongside_the_exit_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _hook_exits_with(monkeypatch, 2, stderr="langfuse: 401 unauthorized\n")

    with pytest.raises(RuntimeError) as excinfo:
        _invoke(module)

    message = str(excinfo.value)
    assert "exit code 2" in message
    assert "401 unauthorized" in message


def test_hook_stdout_is_used_when_stderr_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Falling back to stdout was existing behaviour worth keeping."""
    module = _hook_exits_with(monkeypatch, 3, stdout="traceback on stdout\n")

    with pytest.raises(RuntimeError) as excinfo:
        _invoke(module)

    message = str(excinfo.value)
    assert "exit code 3" in message
    assert "traceback on stdout" in message


def test_successful_hook_raises_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _hook_exits_with(monkeypatch, 0)

    _invoke(module)
