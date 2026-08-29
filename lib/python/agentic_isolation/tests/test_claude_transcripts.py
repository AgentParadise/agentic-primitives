"""Tests for the claude harness transcript source. See issue #792.

Covers: protocol conformance, single-transcript extraction, the
two-transcript delegation case (parent + delegated `claude -p` child
with distinct session ids), the empty-result case, exec failures never
escaping `extract()`, partial read failures not losing the good
transcript, and the filename-stem fallback for session id.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from agentic_isolation.harnesses import ExecFn, TranscriptSource
from agentic_isolation.harnesses.claude import ClaudeHarness
from agentic_isolation.harnesses.claude.transcripts import (
    _FIND_TRANSCRIPTS_COMMAND,
    _TRANSCRIPT_ROOT_ABSENT_MARKER,
    ClaudeTranscriptSource,
)
from agentic_isolation.providers.base import ExecuteResult


@dataclass
class _FakeExec:
    """Fake `ExecFn`. `find_stdout` is returned for the `find` command;
    `file_contents` maps path -> content for subsequent reads, and
    `read_errors` maps path -> exception to raise instead of reading.
    `raise_on_find` short-circuits the whole extract() to exercise the
    "exec raises" path.
    """

    find_stdout: str = ""
    find_exit_code: int = 0
    find_stderr: str = ""
    file_contents: dict[str, str] = field(default_factory=dict)
    read_errors: dict[str, Exception] = field(default_factory=dict)
    raise_on_find: Exception | None = None

    async def __call__(
        self,
        command: str,
        *,
        timeout: float | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> ExecuteResult:
        if "find" in command:
            if self.raise_on_find is not None:
                raise self.raise_on_find
            return ExecuteResult(
                exit_code=self.find_exit_code,
                stdout=self.find_stdout,
                stderr=self.find_stderr,
            )
        # A "cat"-style read of a specific path.
        for path, err in self.read_errors.items():
            if path in command:
                raise err
        for path, content in self.file_contents.items():
            if path in command:
                return ExecuteResult(exit_code=0, stdout=content, stderr="")
        return ExecuteResult(exit_code=1, stdout="", stderr="no such file")


class TestClaudeTranscriptSourceProtocol:
    def test_satisfies_transcript_source_protocol(self) -> None:
        source = ClaudeHarness().transcript_source(_FakeExec())
        assert source is not None
        assert isinstance(source, TranscriptSource)
        assert source.agent == "claude"


class TestSingleTranscript:
    async def test_session_id_and_lines_from_session_id_field(self) -> None:
        path = "/home/user/.claude/projects/proj1/abcd1234.jsonl"
        line1 = json.dumps({"sessionId": "abcd1234", "type": "user"})
        line2 = json.dumps({"type": "assistant"})
        content = f"{line1}\n{line2}\n"
        exec_fn = _FakeExec(find_stdout=path + "\n", file_contents={path: content})
        source = ClaudeTranscriptSource(exec_fn)

        result = await source.extract()

        assert result.success is True
        assert len(result.transcripts) == 1
        transcript = result.transcripts[0]
        assert transcript.agent == "claude"
        assert transcript.session_id == "abcd1234"
        assert transcript.lines == [line1, line2]
        assert transcript.source_path == path


class TestDelegationCase:
    async def test_two_transcripts_parent_and_delegated_child_recovered(self) -> None:
        parent_path = "/home/user/.claude/projects/proj1/parent-session.jsonl"
        child_path = "/home/user/.claude/projects/proj1/child-session.jsonl"
        parent_line = json.dumps({"sessionId": "parent-session", "type": "user"})
        child_line = json.dumps({"sessionId": "child-session", "type": "user"})
        exec_fn = _FakeExec(
            find_stdout=f"{parent_path}\n{child_path}\n",
            file_contents={
                parent_path: parent_line + "\n",
                child_path: child_line + "\n",
            },
        )
        source = ClaudeTranscriptSource(exec_fn)

        result = await source.extract()

        assert result.success is True
        assert len(result.transcripts) == 2
        session_ids = {t.session_id for t in result.transcripts}
        assert session_ids == {"parent-session", "child-session"}
        assert session_ids != {next(iter(session_ids))}  # distinct, not collapsed


class TestNoFiles:
    async def test_empty_find_output_yields_empty_success(self) -> None:
        exec_fn = _FakeExec(find_stdout="")
        source = ClaudeTranscriptSource(exec_fn)

        result = await source.extract()

        assert result.success is True
        assert result.transcripts == []
        assert result.errors == []

    async def test_absent_root_marker_yields_empty_not_error(self) -> None:
        """The dedicated "root absent" stdout marker (exit 0) normalizes
        to a clean empty harvest - not any exit code (issue #792 round 2
        finding 2: an exit code alone is not an authenticated sentinel,
        since `ExecFn` may reuse any exit code for an unrelated transport
        failure)."""
        exec_fn = _FakeExec(find_stdout=_TRANSCRIPT_ROOT_ABSENT_MARKER + "\n")
        source = ClaudeTranscriptSource(exec_fn)

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
            find_stderr="find: '/home/user/.claude/projects': Permission denied",
        )
        source = ClaudeTranscriptSource(exec_fn)

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
        source = ClaudeTranscriptSource(exec_fn)

        result = await source.extract()

        assert result.success is False
        assert len(result.errors) == 1
        assert "transport closed unexpectedly" in result.errors[0]
        assert result.transcripts == []


class TestExecRaises:
    async def test_exec_raising_never_escapes_extract(self) -> None:
        exec_fn = _FakeExec(raise_on_find=RuntimeError("workspace unreachable"))
        source = ClaudeTranscriptSource(exec_fn)

        result = await source.extract()

        assert result.success is False
        assert len(result.errors) == 1
        assert "workspace unreachable" in result.errors[0]
        assert result.transcripts == []


class TestPartialReadFailure:
    async def test_one_bad_file_does_not_lose_the_good_one(self) -> None:
        good_path = "/home/user/.claude/projects/proj1/good-session.jsonl"
        bad_path = "/home/user/.claude/projects/proj1/bad-session.jsonl"
        good_line = json.dumps({"sessionId": "good-session"})
        exec_fn = _FakeExec(
            find_stdout=f"{good_path}\n{bad_path}\n",
            file_contents={good_path: good_line + "\n"},
            read_errors={bad_path: OSError("permission denied")},
        )
        source = ClaudeTranscriptSource(exec_fn)

        result = await source.extract()

        assert result.success is False
        assert len(result.errors) == 1
        assert "permission denied" in result.errors[0]
        assert len(result.transcripts) == 1
        assert result.transcripts[0].session_id == "good-session"


class TestSessionIdFallback:
    async def test_falls_back_to_filename_stem_when_no_line_has_session_id(self) -> None:
        path = "/home/user/.claude/projects/proj1/fallback-stem.jsonl"
        content = json.dumps({"type": "user", "no": "sessionId here"}) + "\n"
        exec_fn = _FakeExec(find_stdout=path + "\n", file_contents={path: content})
        source = ClaudeTranscriptSource(exec_fn)

        result = await source.extract()

        assert result.success is True
        assert len(result.transcripts) == 1
        assert result.transcripts[0].session_id == "fallback-stem"


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
        path = "/home/user/.claude/projects/proj1/deeply-nested.jsonl"
        nested = '{"a":' * 50000 + "1" + "}" * 50000
        exec_fn = _FakeExec(find_stdout=path + "\n", file_contents={path: nested + "\n"})
        source = ClaudeTranscriptSource(exec_fn)

        result = await source.extract()

        assert result.success is True
        assert len(result.transcripts) == 1
        # No line carried a resolvable sessionId, so the fallback stem
        # is used - the important assertion is that nothing raised.
        assert result.transcripts[0].session_id == "deeply-nested"


class TestMalformedJsonLineFallsBackSilently:
    async def test_malformed_json_line_falls_back_to_stem_without_recording_error(
        self,
    ) -> None:
        """A genuinely malformed (not-JSON-at-all) line is an expected
        "this line is not usable JSON" shape (`json.JSONDecodeError`) and
        must fall back to the filename stem WITHOUT recording an error -
        issue #792 round 3 finding 2."""
        path = "/home/user/.claude/projects/proj1/malformed.jsonl"
        content = "{not valid json at all\n"
        exec_fn = _FakeExec(find_stdout=path + "\n", file_contents={path: content})
        source = ClaudeTranscriptSource(exec_fn)

        result = await source.extract()

        assert result.success is True
        assert result.errors == []
        assert len(result.transcripts) == 1
        assert result.transcripts[0].session_id == "malformed"


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
        path = "/home/user/.claude/projects/proj1/unexpected.jsonl"
        content = json.dumps({"sessionId": "s1"}) + "\n"
        exec_fn = _FakeExec(find_stdout=path + "\n", file_contents={path: content})
        source = ClaudeTranscriptSource(exec_fn)

        def _boom(*_args: object, **_kwargs: object) -> object:
            raise TypeError("boom: not a malformed-JSON error")

        monkeypatch.setattr("agentic_isolation.harnesses.claude.transcripts.json.loads", _boom)

        result = await source.extract()

        assert result.success is False
        assert len(result.errors) == 1
        assert "unexpected.jsonl" in result.errors[0]
        assert "boom" in result.errors[0]
        assert len(result.transcripts) == 1
        assert result.transcripts[0].session_id == "unexpected"


class TestExecFnProtocolMatch:
    def test_fake_exec_matches_execfn_shape(self) -> None:
        exec_fn: ExecFn = _FakeExec()
        assert callable(exec_fn)


class TestRealShellNeverFakeExecFn:
    """`_FakeExec` above returns the marker string directly - it can never
    catch a shell-level escaping defect in `_FIND_TRANSCRIPTS_COMMAND`
    itself. These tests run the ACTUAL generated command through a real
    `sh` subprocess instead, closing that structural gap (issue #792: a
    `printf '%s\\\\n'` double-escaping defect in the Python source reached
    the shell as a literal backslash-n, not a newline, so the absent-root
    marker could never exactly match in a real shell - every existing test
    used a fake `exec_fn` and so never exercised real shell escaping)."""

    def test_absent_root_emits_exactly_the_marker_plus_one_newline(self, tmp_path: Path) -> None:
        fake_home = tmp_path / "definitely_absent_home"
        env = dict(os.environ)
        env["HOME"] = str(fake_home)

        result = subprocess.run(
            ["sh", "-lc", _FIND_TRANSCRIPTS_COMMAND],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

        assert result.returncode == 0
        # Exact byte-for-byte check: a literal `\n` (backslash + `n`, two
        # characters) instead of a real newline (`\n`, one 0x0a byte) is
        # exactly the regression this test exists to catch - `.strip()`
        # alone would not distinguish the two, so the assertion below
        # checks the raw stdout, not a stripped version.
        assert result.stdout == _TRANSCRIPT_ROOT_ABSENT_MARKER + "\n"
        assert result.stdout.strip() == _TRANSCRIPT_ROOT_ABSENT_MARKER

    def test_present_root_with_matching_files_lists_them_without_the_marker(
        self, tmp_path: Path
    ) -> None:
        fake_home = tmp_path / "real_home"
        project_dir = fake_home / ".claude" / "projects" / "proj1"
        project_dir.mkdir(parents=True)
        transcript_path = project_dir / "session-abc.jsonl"
        transcript_path.write_text(json.dumps({"sessionId": "session-abc"}) + "\n")

        env = dict(os.environ)
        env["HOME"] = str(fake_home)

        result = subprocess.run(
            ["sh", "-lc", _FIND_TRANSCRIPTS_COMMAND],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )

        assert result.returncode == 0
        assert str(transcript_path) in result.stdout
        assert _TRANSCRIPT_ROOT_ABSENT_MARKER not in result.stdout
