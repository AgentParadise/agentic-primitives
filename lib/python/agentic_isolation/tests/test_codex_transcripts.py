"""Tests for the codex harness transcript source. See issue #792.

Real schema recovered on 2026-07-28 from an actual `~/.codex/sessions/`
tree (NOT reasoned about from the codex `--json` STDOUT event stream,
which is a different thing - see the codex package docstring). Codex
writes one rollout JSONL file per session under
`$CODEX_HOME/sessions/<year>/<month>/<day>/rollout-<timestamp>-<uuid>.jsonl`
(`$CODEX_HOME` defaults to `~/.codex`). Each line is a JSON object with
a top-level `type` (`session_meta`, `event_msg`, `response_item`,
`turn_context`, `world_state`, ...). Only the `session_meta` line
carries `payload.session_id`; other line types do not.

Covers: protocol conformance, a transcript parsed from the real
schema, the empty-result case (missing sessions dir - codex legitimately
persists nothing under `--ephemeral`), exec failures never escaping
`extract()`, partial read failures not losing the good transcript, the
`$CODEX_HOME` override, and the filename-stem session id fallback.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from agentic_isolation.harnesses import ExecFn, TranscriptSource
from agentic_isolation.harnesses.codex import CodexHarness
from agentic_isolation.harnesses.codex.transcripts import CodexTranscriptSource
from agentic_isolation.providers.base import ExecuteResult


@dataclass
class _FakeExec:
    """Fake `ExecFn`. `find_stdout` is returned for the `find` command;
    `file_contents` maps path -> content for subsequent reads, and
    `read_errors` maps path -> exception to raise instead of reading.
    `raise_on_find` short-circuits the whole extract() to exercise the
    "exec raises" path. `seen_commands` records every command issued so
    tests can assert on the `$CODEX_HOME` resolution used.
    """

    find_stdout: str = ""
    find_exit_code: int = 0
    file_contents: dict[str, str] = field(default_factory=dict)
    read_errors: dict[str, Exception] = field(default_factory=dict)
    raise_on_find: Exception | None = None
    seen_commands: list[str] = field(default_factory=list)

    async def __call__(
        self,
        command: str,
        *,
        timeout: float | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> ExecuteResult:
        self.seen_commands.append(command)
        if "find" in command:
            if self.raise_on_find is not None:
                raise self.raise_on_find
            return ExecuteResult(exit_code=self.find_exit_code, stdout=self.find_stdout, stderr="")
        for path, err in self.read_errors.items():
            if path in command:
                raise err
        for path, content in self.file_contents.items():
            if path in command:
                return ExecuteResult(exit_code=0, stdout=content, stderr="")
        return ExecuteResult(exit_code=1, stdout="", stderr="no such file")


def _session_meta_line(session_id: str) -> str:
    return json.dumps(
        {
            "timestamp": "2026-07-28T21:14:35.154Z",
            "type": "session_meta",
            "payload": {
                "session_id": session_id,
                "id": session_id,
                "timestamp": "2026-07-28T21:14:35.035Z",
                "cwd": "/workspace",
                "originator": "codex_exec",
                "cli_version": "0.144.6",
                "source": "exec",
            },
        }
    )


def _event_msg_line() -> str:
    return json.dumps(
        {
            "timestamp": "2026-07-28T21:14:35.154Z",
            "type": "event_msg",
            "payload": {
                "type": "task_started",
                "turn_id": "019faa94-52f9-7052-98fa-7138c4527a1a",
                "started_at": 1785273275,
                "model_context_window": 258400,
            },
        }
    )


class TestCodexTranscriptSourceProtocol:
    def test_satisfies_transcript_source_protocol(self) -> None:
        source = CodexHarness().transcript_source(_FakeExec())
        assert source is not None
        assert isinstance(source, TranscriptSource)
        assert source.agent == "codex"


class TestSingleTranscriptRealSchema:
    async def test_session_id_from_session_meta_payload(self) -> None:
        path = (
            "/root/.codex/sessions/2026/07/28/"
            "rollout-2026-07-28T14-14-35-019faa94-5284-7391-a40b-1b4667c416d9.jsonl"
        )
        session_id = "019faa94-5284-7391-a40b-1b4667c416d9"
        line1 = _session_meta_line(session_id)
        line2 = _event_msg_line()
        content = f"{line1}\n{line2}\n"
        exec_fn = _FakeExec(find_stdout=path + "\n", file_contents={path: content})
        source = CodexTranscriptSource(exec_fn)

        result = await source.extract()

        assert result.success is True
        assert len(result.transcripts) == 1
        transcript = result.transcripts[0]
        assert transcript.agent == "codex"
        assert transcript.session_id == session_id
        assert transcript.lines == [line1, line2]
        assert transcript.source_path == path

    async def test_tolerates_unknown_extra_fields(self) -> None:
        path = "/root/.codex/sessions/2026/07/28/rollout-x.jsonl"
        payload = json.loads(_session_meta_line("sess-1"))
        payload["payload"]["some_future_field"] = {"nested": True}
        payload["a_brand_new_top_level_field"] = 42
        content = json.dumps(payload) + "\n"
        exec_fn = _FakeExec(find_stdout=path + "\n", file_contents={path: content})
        source = CodexTranscriptSource(exec_fn)

        result = await source.extract()

        assert result.success is True
        assert result.transcripts[0].session_id == "sess-1"


class TestMissingSessionsDirIsCleanEmpty:
    async def test_empty_find_output_yields_empty_success(self) -> None:
        exec_fn = _FakeExec(find_stdout="")
        source = CodexTranscriptSource(exec_fn)

        result = await source.extract()

        assert result.success is True
        assert result.transcripts == []
        assert result.errors == []

    async def test_nonzero_find_exit_code_yields_empty_not_error(self) -> None:
        """A missing sessions dir is a legitimate outcome (e.g. codex ran
        with `--ephemeral` and persisted nothing) - not an error."""
        exec_fn = _FakeExec(find_stdout="", find_exit_code=1)
        source = CodexTranscriptSource(exec_fn)

        result = await source.extract()

        assert result.success is True
        assert result.transcripts == []
        assert result.errors == []


class TestExecRaises:
    async def test_exec_raising_never_escapes_extract(self) -> None:
        exec_fn = _FakeExec(raise_on_find=RuntimeError("workspace unreachable"))
        source = CodexTranscriptSource(exec_fn)

        result = await source.extract()

        assert result.success is False
        assert len(result.errors) == 1
        assert "workspace unreachable" in result.errors[0]
        assert result.transcripts == []


class TestPartialReadFailure:
    async def test_one_bad_file_does_not_lose_the_good_one(self) -> None:
        good_path = "/root/.codex/sessions/2026/07/28/rollout-good.jsonl"
        bad_path = "/root/.codex/sessions/2026/07/28/rollout-bad.jsonl"
        good_line = _session_meta_line("good-session")
        exec_fn = _FakeExec(
            find_stdout=f"{good_path}\n{bad_path}\n",
            file_contents={good_path: good_line + "\n"},
            read_errors={bad_path: OSError("permission denied")},
        )
        source = CodexTranscriptSource(exec_fn)

        result = await source.extract()

        assert result.success is False
        assert len(result.errors) == 1
        assert "permission denied" in result.errors[0]
        assert len(result.transcripts) == 1
        assert result.transcripts[0].session_id == "good-session"


class TestCodexHomeOverride:
    async def test_find_command_honors_codex_home_with_fallback(self) -> None:
        exec_fn = _FakeExec(find_stdout="")
        source = CodexTranscriptSource(exec_fn)

        await source.extract()

        assert len(exec_fn.seen_commands) == 1
        command = exec_fn.seen_commands[0]
        assert "CODEX_HOME" in command
        assert "$HOME/.codex" in command or ".codex" in command


class TestSessionIdFallback:
    async def test_falls_back_to_filename_stem_when_no_session_meta_line(self) -> None:
        path = "/root/.codex/sessions/2026/07/28/rollout-fallback-stem.jsonl"
        content = _event_msg_line() + "\n"
        exec_fn = _FakeExec(find_stdout=path + "\n", file_contents={path: content})
        source = CodexTranscriptSource(exec_fn)

        result = await source.extract()

        assert result.success is True
        assert len(result.transcripts) == 1
        assert result.transcripts[0].session_id == "rollout-fallback-stem"


class TestExecFnProtocolMatch:
    def test_fake_exec_matches_execfn_shape(self) -> None:
        exec_fn: ExecFn = _FakeExec()
        assert callable(exec_fn)
