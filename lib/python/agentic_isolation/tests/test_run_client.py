"""Tests for the thin ``itmux run`` Python client (Plan B, Task 7).

No real docker and no real ``itmux`` binary are required: every subprocess test
drives a FAKE ``itmux`` (a tiny Python script on disk) whose path is passed as
``itmux_bin``.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from agentic_isolation.run_client import (
    _EVENT_ADAPTER,
    AgentRunResult,
    ItmuxRunError,
    ResultEvent,
    SessionEndEvent,
    TokenUsageEvent,
    ToolEndEvent,
    ToolStartEvent,
    _terminate_process_group,
    parse_event,
    run_agent,
)

# ---------------------------------------------------------------------------
# Canned event stream mirroring the Rust contract wire shape.
# ---------------------------------------------------------------------------

_RESULT_PAYLOAD = {
    "result": {"success": True, "summary": "done"},
    "output_artifacts": ["/work/out.txt"],
    "session_log": "pane transcript",
    "observability": None,
}

_EVENT_LINES: list[str] = [
    json.dumps(
        {
            "run_id": "r1",
            "seq": 0,
            "ts": "2026-07-07T00:00:00Z",
            "type": "tool_start",
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
        }
    ),
    json.dumps(
        {
            "run_id": "r1",
            "seq": 1,
            "ts": "2026-07-07T00:00:01Z",
            "type": "tool_end",
            "tool_name": "Bash",
            "success": True,
            "output_summary": "ok",
        }
    ),
    json.dumps(
        {
            "run_id": "r1",
            "seq": 2,
            "ts": "2026-07-07T00:00:02Z",
            "type": "token_usage",
            "input_tokens": 100,
            "output_tokens": 50,
            "cost_usd": 0.01,
        }
    ),
    json.dumps(
        {
            "run_id": "r1",
            "seq": 3,
            "ts": "2026-07-07T00:00:03Z",
            "type": "session_end",
            "outcome": {"success": True, "summary": "done"},
        }
    ),
    json.dumps(
        {
            "run_id": "r1",
            "seq": 4,
            "ts": "2026-07-07T00:00:04Z",
            "type": "result",
            "result": _RESULT_PAYLOAD,
        }
    ),
]


def _write_fake_itmux(tmp_path: Path, body: str) -> Path:
    """Write an executable fake ``itmux`` Python script and return its path."""
    script = tmp_path / "fake_itmux"
    script.write_text("#!/usr/bin/env python3\n" + body)
    script.chmod(0o755)
    return script


# ---------------------------------------------------------------------------
# Model / discriminated-union parsing.
# ---------------------------------------------------------------------------


def test_parse_event_discriminates_each_variant() -> None:
    events = [parse_event(line) for line in _EVENT_LINES]
    assert isinstance(events[0], ToolStartEvent)
    assert isinstance(events[1], ToolEndEvent)
    assert isinstance(events[2], TokenUsageEvent)
    assert isinstance(events[3], SessionEndEvent)
    assert isinstance(events[4], ResultEvent)

    # Field names mirror the Rust serde names exactly.
    assert events[0].tool_name == "Bash"
    assert events[0].tool_input == {"command": "ls"}
    assert events[2].input_tokens == 100
    assert events[2].output_tokens == 50
    assert events[2].cost_usd == pytest.approx(0.01)
    assert events[3].outcome.success is True

    result_event = events[4]
    assert isinstance(result_event, ResultEvent)
    assert result_event.result.result.summary == "done"
    assert result_event.result.output_artifacts == ["/work/out.txt"]
    assert result_event.result.session_log == "pane transcript"


def test_parse_event_rejects_unknown_field() -> None:
    bad = json.dumps(
        {
            "run_id": "r1",
            "seq": 0,
            "ts": "t",
            "type": "tool_start",
            "tool_name": "Bash",
            "surprise": 1,
        }
    )
    with pytest.raises(ItmuxRunError):
        parse_event(bad)


def test_parse_event_rejects_unknown_discriminator() -> None:
    bad = json.dumps({"run_id": "r1", "seq": 0, "ts": "t", "type": "nope"})
    with pytest.raises(ItmuxRunError):
        parse_event(bad)


def test_result_model_rejects_unknown_field() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AgentRunResult.model_validate(
            {"result": {"success": True, "summary": "s"}, "session_log": "l", "extra": 1}
        )


def test_optional_defaults_match_contract() -> None:
    line = json.dumps(
        {"run_id": "r1", "seq": 0, "ts": "t", "type": "tool_end", "tool_name": "Read"}
    )
    event = _EVENT_ADAPTER.validate_json(line)
    assert isinstance(event, ToolEndEvent)
    assert event.success is False  # serde default
    assert event.output_summary is None


# ---------------------------------------------------------------------------
# run_agent happy path.
# ---------------------------------------------------------------------------


def test_run_agent_returns_result_and_streams_events(tmp_path: Path) -> None:
    lines_literal = json.dumps(_EVENT_LINES)
    body = (
        "import sys\n"
        f"for line in {lines_literal}:\n"
        "    print(line)\n"
        "    sys.stdout.flush()\n"
        "sys.exit(0)\n"
    )
    fake = _write_fake_itmux(tmp_path, body)

    seen: list[object] = []
    result = run_agent(
        Path("/recipes/demo"),
        "do the thing",
        itmux_bin=str(fake),
        on_event=seen.append,
    )

    assert isinstance(result, AgentRunResult)
    assert result.result.success is True
    assert result.result.summary == "done"
    assert result.output_artifacts == ["/work/out.txt"]
    # on_event fires once per streamed event, including the terminal result.
    assert len(seen) == len(_EVENT_LINES)
    assert isinstance(seen[-1], ResultEvent)


def test_run_agent_passes_expected_argv(tmp_path: Path) -> None:
    # Fake echoes its argv (as a session_log) so we can assert the built command.
    result_payload = dict(_RESULT_PAYLOAD)
    body = (
        "import sys, json\n"
        "argv = sys.argv[1:]\n"
        "payload = {'result': {'success': True, 'summary': ' '.join(argv)},\n"
        "           'session_log': 'x'}\n"
        "print(json.dumps({'run_id': 'r', 'seq': 0, 'ts': 't', 'type': 'result',\n"
        "                  'result': payload}))\n"
    )
    del result_payload  # not needed; kept for clarity
    fake = _write_fake_itmux(tmp_path, body)

    result = run_agent(
        Path("/recipes/demo"),
        "my task",
        image="custom:tag",
        itmux_bin=str(fake),
    )
    argv_summary = result.result.summary
    assert "run --recipe /recipes/demo --task my task" in argv_summary
    assert "--image custom:tag" in argv_summary
    assert "--json true" in argv_summary


# ---------------------------------------------------------------------------
# run_agent failure paths.
# ---------------------------------------------------------------------------


def test_run_agent_nonzero_exit_no_result_raises(tmp_path: Path) -> None:
    body = "import sys\nprint('boom: recipe failed to load', file=sys.stderr)\nsys.exit(1)\n"
    fake = _write_fake_itmux(tmp_path, body)

    with pytest.raises(ItmuxRunError) as exc_info:
        run_agent(Path("/recipes/demo"), "task", itmux_bin=str(fake))
    assert exc_info.value.returncode == 1
    assert "boom" in (exc_info.value.stderr or "")


def test_run_agent_zero_exit_no_result_raises(tmp_path: Path) -> None:
    body = "import sys\nsys.exit(0)\n"  # no events at all
    fake = _write_fake_itmux(tmp_path, body)

    with pytest.raises(ItmuxRunError, match="no terminal result"):
        run_agent(Path("/recipes/demo"), "task", itmux_bin=str(fake))


def test_run_agent_unparseable_output_raises(tmp_path: Path) -> None:
    body = "print('not json at all')\n"
    fake = _write_fake_itmux(tmp_path, body)

    with pytest.raises(ItmuxRunError, match="unparseable"):
        run_agent(Path("/recipes/demo"), "task", itmux_bin=str(fake))


# ---------------------------------------------------------------------------
# Process-group cleanup (R10).
# ---------------------------------------------------------------------------


def test_terminate_process_group_signals_pgid(monkeypatch: pytest.MonkeyPatch) -> None:
    # Spawn a real child in its own session/group so os.getpgid works, then
    # monkeypatch os.killpg to record the signals sent instead of delivering.
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        start_new_session=True,
        text=True,
    )
    try:
        expected_pgid = os.getpgid(proc.pid)
        calls: list[tuple[int, int]] = []
        monkeypatch.setattr(os, "killpg", lambda pgid, sig: calls.append((pgid, sig)))

        # grace 0.1 so the SIGTERM->SIGKILL escalation is fast (killpg is faked,
        # so the child never actually dies during the call).
        _terminate_process_group(proc, grace_s=0.1)

        assert (expected_pgid, signal.SIGTERM) in calls
        assert (expected_pgid, signal.SIGKILL) in calls
    finally:
        # Undo the killpg patch BEFORE real cleanup so the child actually dies.
        monkeypatch.undo()
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, OSError):
            pass
        proc.wait(timeout=5)


@pytest.mark.skipif(os.name != "posix", reason="process groups are POSIX-only")
def test_run_agent_timeout_reaps_child_tree(tmp_path: Path) -> None:
    # Fake emits one event, spawns a long-lived grandchild recording its PID,
    # then blocks forever WITHOUT emitting a result. run_agent's timeout must
    # kill the whole process group and leave no orphan.
    pid_file = tmp_path / "grandchild.pid"
    body = (
        "import os, sys, time, subprocess\n"
        'print(\'{"run_id": "r", "seq": 0, "ts": "t", '
        '"type": "tool_start", "tool_name": "Bash"}\')\n'
        "sys.stdout.flush()\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"open({str(pid_file)!r}, 'w').write(str(child.pid))\n"
        "time.sleep(60)\n"
    )
    fake = _write_fake_itmux(tmp_path, body)

    with pytest.raises(ItmuxRunError, match="timed out"):
        run_agent(Path("/recipes/demo"), "task", itmux_bin=str(fake), timeout=1.0)

    # Give the group signal a moment to land.
    deadline = time.time() + 5.0
    grandchild_pid = int(pid_file.read_text().strip())
    while time.time() < deadline:
        try:
            os.kill(grandchild_pid, 0)
        except ProcessLookupError:
            break  # reaped - success
        time.sleep(0.05)
    else:
        # Still alive: clean up so we don't leak, then fail.
        try:
            os.kill(grandchild_pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        pytest.fail("grandchild process was orphaned (not reaped by group cleanup)")
