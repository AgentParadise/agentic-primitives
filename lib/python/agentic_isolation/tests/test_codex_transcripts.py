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

import pytest

from agentic_isolation.harnesses import ExecFn, TranscriptSource
from agentic_isolation.harnesses.codex import CodexHarness
from agentic_isolation.harnesses.codex.transcripts import (
    _TRANSCRIPT_ROOT_ABSENT_MARKER,
    CodexTranscriptSource,
)
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
    find_stderr: str = ""
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
            return ExecuteResult(
                exit_code=self.find_exit_code,
                stdout=self.find_stdout,
                stderr=self.find_stderr,
            )
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


def _event_msg_line(*, spoofed_session_id: str | None = None) -> str:
    payload: dict[str, object] = {
        "type": "task_started",
        "turn_id": "019faa94-52f9-7052-98fa-7138c4527a1a",
        "started_at": 1785273275,
        "model_context_window": 258400,
    }
    if spoofed_session_id is not None:
        # A non-`session_meta` line that happens to carry a
        # `payload.session_id`-shaped field - must NOT be read as the
        # session id (issue #792 finding 2).
        payload["session_id"] = spoofed_session_id
    return json.dumps(
        {
            "timestamp": "2026-07-28T21:14:35.154Z",
            "type": "event_msg",
            "payload": payload,
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

    async def test_absent_root_marker_yields_empty_not_error(self) -> None:
        """A missing sessions dir is a legitimate outcome (e.g. codex ran
        with `--ephemeral` and persisted nothing) - not an error. The
        source shell script signals this with the dedicated
        `_TRANSCRIPT_ROOT_ABSENT_MARKER` on stdout (exit 0), not any
        exit code alone (issue #792 round 2 finding 2: an exit code is
        not an authenticated sentinel, since `ExecFn` may reuse any exit
        code for an unrelated transport failure)."""
        exec_fn = _FakeExec(find_stdout=_TRANSCRIPT_ROOT_ABSENT_MARKER + "\n")
        source = CodexTranscriptSource(exec_fn)

        result = await source.extract()

        assert result.success is True
        assert result.transcripts == []
        assert result.errors == []


class TestRealListingFailureIsAnError:
    async def test_nonabsent_nonzero_exit_is_reported_as_error(self) -> None:
        """Any non-zero `find` exit is a real transport failure
        (permission denied, unreachable filesystem, ...) and must
        populate `errors` - issue #792 finding 1: a bare `|| true` used
        to swallow this into a clean empty result."""
        exec_fn = _FakeExec(
            find_stdout="",
            find_exit_code=1,
            find_stderr="find: '/root/.codex/sessions': Permission denied",
        )
        source = CodexTranscriptSource(exec_fn)

        result = await source.extract()

        assert result.success is False
        assert len(result.errors) == 1
        assert "Permission denied" in result.errors[0]
        assert result.transcripts == []

    async def test_transport_failure_reusing_the_old_sentinel_exit_code_is_still_an_error(
        self,
    ) -> None:
        """A transport failure that happens to exit with the same code
        the old (removed) "root absent" sentinel used (9), but without
        the stdout marker, MUST be treated as a real error - not
        misread as a clean empty harvest. This is the specific
        regression from relying on an exit code alone as an
        authenticated sentinel (issue #792 round 2 finding 2)."""
        exec_fn = _FakeExec(
            find_stdout="",
            find_exit_code=9,
            find_stderr="find: transport closed unexpectedly",
        )
        source = CodexTranscriptSource(exec_fn)

        result = await source.extract()

        assert result.success is False
        assert len(result.errors) == 1
        assert "transport closed unexpectedly" in result.errors[0]
        assert result.transcripts == []


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

    async def test_falls_back_to_filename_stem_even_if_a_non_session_meta_line_has_session_id(
        self,
    ) -> None:
        """A `payload.session_id`-shaped field on a non-`session_meta`
        line must not be read - issue #792 finding 2."""
        path = "/root/.codex/sessions/2026/07/28/rollout-spoofed.jsonl"
        content = _event_msg_line(spoofed_session_id="not-the-real-session") + "\n"
        exec_fn = _FakeExec(find_stdout=path + "\n", file_contents={path: content})
        source = CodexTranscriptSource(exec_fn)

        result = await source.extract()

        assert result.success is True
        assert len(result.transcripts) == 1
        assert result.transcripts[0].session_id == "rollout-spoofed"


class TestSessionMetaTypeIsAuthoritative:
    async def test_session_meta_id_wins_over_spoofed_event_msg_id(self) -> None:
        """A non-`session_meta` line carrying `payload.session_id` must
        never override the real `session_meta` id - issue #792 finding
        2."""
        path = "/root/.codex/sessions/2026/07/28/rollout-precedence.jsonl"
        real_session_id = "019faa94-5284-7391-a40b-1b4667c416d9"
        spoofed_line = _event_msg_line(spoofed_session_id="not-the-real-session")
        meta_line = _session_meta_line(real_session_id)
        content = f"{spoofed_line}\n{meta_line}\n"
        exec_fn = _FakeExec(find_stdout=path + "\n", file_contents={path: content})
        source = CodexTranscriptSource(exec_fn)

        result = await source.extract()

        assert result.success is True
        assert len(result.transcripts) == 1
        assert result.transcripts[0].session_id == real_session_id


class TestDeeplyNestedJsonNeverEscapesExtract:
    def test_deeply_nested_json_raises_recursion_error_when_parsed_directly(self) -> None:
        """Sanity check that this test is not vacuous: a raw `json.loads`
        on the fixture below genuinely raises `RecursionError` - a
        `RuntimeError` subclass, NOT a `ValueError` - before `extract()`
        gets anywhere near it (issue #792 round 2 finding 1)."""
        nested = '{"a":' * 50000 + "1" + "}" * 50000
        with pytest.raises(RecursionError):
            json.loads(nested)

    async def test_deeply_nested_json_line_never_escapes_extract(self) -> None:
        """The same deeply-nested-JSON line, fed through `extract()`,
        must not raise: the old code only caught `json.JSONDecodeError`
        and `ValueError`, so `RecursionError` escaped `extract()`
        entirely - violating the "MUST NEVER RAISE" contract (issue #792
        round 2 finding 1)."""
        path = "/root/.codex/sessions/2026/07/28/rollout-deeply-nested.jsonl"
        nested = '{"a":' * 50000 + "1" + "}" * 50000
        exec_fn = _FakeExec(find_stdout=path + "\n", file_contents={path: nested + "\n"})
        source = CodexTranscriptSource(exec_fn)

        result = await source.extract()

        assert result.success is True
        assert len(result.transcripts) == 1
        # No line carried a `session_meta` payload, so the fallback stem
        # is used - the important assertion is that nothing raised.
        assert result.transcripts[0].session_id == "rollout-deeply-nested"


class TestMalformedJsonLineFallsBackSilently:
    async def test_malformed_json_line_falls_back_to_stem_without_recording_error(
        self,
    ) -> None:
        """A genuinely malformed (not-JSON-at-all) line is an expected
        "this line is not usable JSON" shape (`json.JSONDecodeError`) and
        must fall back to the filename stem WITHOUT recording an error -
        issue #792 round 3 finding 2."""
        path = "/root/.codex/sessions/2026/07/28/rollout-malformed.jsonl"
        content = "{not valid json at all\n"
        exec_fn = _FakeExec(find_stdout=path + "\n", file_contents={path: content})
        source = CodexTranscriptSource(exec_fn)

        result = await source.extract()

        assert result.success is True
        assert result.errors == []
        assert len(result.transcripts) == 1
        assert result.transcripts[0].session_id == "rollout-malformed"


class TestUnexpectedParseErrorIsRecordedNotSwallowed:
    async def test_unexpected_error_during_line_parsing_is_recorded_in_errors(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A genuine parser/programming defect (anything other than
        malformed-JSON/deeply-nested-JSON) raised while parsing a line
        must NOT be silently swallowed - issue #792 round 3 finding 2: the
        previous bare `except Exception` around `json.loads` traded one
        silent-failure mode (unresolved session id escaping `extract()`)
        for another (an unexpected defect vanishing without a trace). It
        must propagate out of `_resolve_session_id` and be caught (and
        recorded in `errors`) by the surrounding per-file guard in
        `extract()` instead."""
        path = "/root/.codex/sessions/2026/07/28/rollout-unexpected.jsonl"
        content = _session_meta_line("s1") + "\n"
        exec_fn = _FakeExec(find_stdout=path + "\n", file_contents={path: content})
        source = CodexTranscriptSource(exec_fn)

        def _boom(*_args: object, **_kwargs: object) -> object:
            raise TypeError("boom: not a malformed-JSON error")

        monkeypatch.setattr("agentic_isolation.harnesses.codex.transcripts.json.loads", _boom)

        result = await source.extract()

        assert result.success is False
        assert len(result.errors) == 1
        assert "rollout-unexpected.jsonl" in result.errors[0]
        assert "boom" in result.errors[0]
        assert len(result.transcripts) == 1
        assert result.transcripts[0].session_id == "rollout-unexpected"


class TestExecFnProtocolMatch:
    def test_fake_exec_matches_execfn_shape(self) -> None:
        exec_fn: ExecFn = _FakeExec()
        assert callable(exec_fn)
