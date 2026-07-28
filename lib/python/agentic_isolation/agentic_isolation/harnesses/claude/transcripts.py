"""Transcript extraction for the `claude` (Claude Code CLI) harness.

Claude Code writes one JSONL transcript file per session under
`~/.claude/projects/<project>/<session_id>.jsonl` inside the workspace
(including any delegated sub-agent session started via `claude -p`,
which writes its own file with its own session id - see issue #792).
`ClaudeTranscriptSource` recovers every such file after the fact via the
workspace's `ExecFn`, never by reaching into the filesystem directly:
the workspace may be a remote container, so all I/O goes through
`exec_fn`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from agentic_isolation.harnesses import (
    AgentName,
    ExecFn,
    HarnessTranscript,
    TranscriptExtractionResult,
    exec_argv,
)

_TRANSCRIPT_ROOT_ABSENT_MARKER = "__agentic_isolation_claude_transcript_root_absent__"
"""Unique stdout marker meaning "the transcript root does not exist".

Distinguishes a legitimate empty harvest (workspace never wrote
`~/.claude/projects`) from a real transport failure (permission denied,
unreachable filesystem, ...). An exit code alone cannot carry this
distinction: `ExecFn` itself may fail transport with any exit code
(including one a shell script happens to pick for "absent"), and `find`
reserves no exit code for "the directory never existed" - see issue #792
(round 2 finding 2). Only an EXACT stdout match against this marker (exit
0) normalizes to a clean empty `TranscriptExtractionResult`; any non-zero
exit is unconditionally a real error reported through `errors`. The
listing command used to unconditionally force a zero exit code on `find`
failure via a bare `|| true`, and later a fixed "absent" exit code that a
transport failure could coincidentally reproduce - both swallowed real
failures as a clean empty result.
"""

_FIND_TRANSCRIPTS_COMMAND = (
    'root="$HOME/.claude/projects"; '
    'if [ ! -d "$root" ]; then '
    f"printf '%s\\\\n' '{_TRANSCRIPT_ROOT_ABSENT_MARKER}'; exit 0; fi; "
    "find \"$root\" -name '*.jsonl' -type f"
)


def _resolve_session_id(lines: list[str], source_path: str) -> str:
    """Prefer the first line's `sessionId`; fall back to the filename stem.

    Claude Code's JSONL lines all carry the same `sessionId`, but only
    the first line is consulted: cheaper, and sufficient since the
    field does not vary within one file.
    """
    for line in lines:
        try:
            parsed = json.loads(line)
        except (json.JSONDecodeError, ValueError, RecursionError):
            # These are the expected "this line is not usable JSON" shapes:
            # `json.JSONDecodeError` (a `ValueError` subclass, listed
            # explicitly for clarity) for ordinary malformed JSON, and
            # `RecursionError` (a `RuntimeError` subclass, NOT a
            # `ValueError`) for deeply nested JSON - see issue #792 finding
            # 1. A single line in either shape must never lose the rest of
            # the file's lines, so it is skipped silently. Anything else is
            # a genuine parser/programming defect and must propagate to the
            # outer `extract()` boundary, where it IS recorded in `errors`
            # (issue #792 round 3 finding 2: a bare `except Exception` here
            # previously swallowed unexpected errors without a trace).
            continue
        if not isinstance(parsed, dict):
            continue
        session_id = parsed.get("sessionId")
        if isinstance(session_id, str) and session_id:
            return session_id
    return Path(source_path).stem


@dataclass
class ClaudeTranscriptSource:
    """`TranscriptSource` for the `claude` harness.

    `extract()` MUST NEVER raise (see `TranscriptSource.extract`): its
    entire body runs inside one outer `try`/`except Exception` in
    `extract()` itself (issue #792 round 3 finding 1), so nothing after
    the exec awaits - reading `find_result` fields, string processing,
    building dataclasses - can escape either. Per-file guards inside
    `_extract()` still exist on top of that outer boundary so one bad
    transcript can never lose the others.
    """

    _exec_fn: ExecFn

    @property
    def agent(self) -> AgentName:
        return AgentName.CLAUDE

    async def extract(self) -> TranscriptExtractionResult:
        errors: list[str] = []

        try:
            return await self._extract(errors)
        except Exception as exc:  # noqa: BLE001 - a transcript harvest must
            # never abort a workspace teardown, so this is the ONE outer
            # boundary wrapping the entire body of `extract()`: not just the
            # exec awaits, but everything after them too (reading
            # `find_result.success`/`.stdout`/`.stderr`, `.strip()`,
            # `.splitlines()`, building error strings, constructing
            # dataclasses, appending results) - issue #792 round 3 finding
            # 1. `BaseException` (`KeyboardInterrupt`, `SystemExit`) is
            # deliberately NOT caught here - swallowing those would be a
            # defect, not a fix. Inner per-file guards below still exist so
            # one bad file cannot lose its siblings; this outer guard exists
            # for whatever they don't anticipate.
            errors.append(f"unexpected error extracting claude transcripts: {exc}")
            return TranscriptExtractionResult(transcripts=[], errors=errors)

    async def _extract(self, errors: list[str]) -> TranscriptExtractionResult:
        try:
            find_result = await self._exec_fn(_FIND_TRANSCRIPTS_COMMAND)
        except Exception as exc:  # noqa: BLE001 - reported with a specific
            # "failed to list" message before falling through to the outer
            # boundary in `extract()`.
            errors.append(f"failed to list claude transcripts: {exc}")
            return TranscriptExtractionResult(transcripts=[], errors=errors)

        if not find_result.success:
            # A non-zero exit is unconditionally a real transport failure -
            # no exit code is treated as an "absent root" sentinel, since
            # `ExecFn` may fail for unrelated reasons and reuse any exit
            # code (issue #792 round 2 finding 2).
            errors.append(
                f"failed to list claude transcripts: exit {find_result.exit_code}: "
                f"{find_result.stderr}"
            )
            return TranscriptExtractionResult(transcripts=[], errors=errors)

        if find_result.stdout.strip() == _TRANSCRIPT_ROOT_ABSENT_MARKER:
            # The transcript root does not exist yet in this workspace -
            # authenticated by the exact marker, not merely a zero exit -
            # a legitimate empty harvest, not an error.
            return TranscriptExtractionResult(transcripts=[], errors=[])

        paths = [line.strip() for line in find_result.stdout.splitlines() if line.strip()]

        transcripts: list[HarnessTranscript] = []
        for path in paths:
            try:
                read_result = await exec_argv(self._exec_fn, ["cat", path])
            except Exception as exc:  # noqa: BLE001 - one bad file's exec
                # failure must never lose the other files' transcripts.
                errors.append(f"failed to read {path}: {exc}")
                continue

            if not read_result.success:
                errors.append(
                    f"failed to read {path}: exit {read_result.exit_code}: {read_result.stderr}"
                )
                continue

            lines = [line for line in read_result.stdout.splitlines() if line.strip()]
            try:
                session_id = _resolve_session_id(lines, path)
            except Exception as exc:  # noqa: BLE001 - if session id
                # resolution somehow fails despite its own guard, fall back
                # to the filename stem instead of losing the whole file
                # (issue #792 finding 1).
                errors.append(f"failed to resolve session id for {path}: {exc}")
                session_id = Path(path).stem
            transcripts.append(
                HarnessTranscript(
                    agent=AgentName.CLAUDE,
                    session_id=session_id,
                    lines=lines,
                    source_path=path,
                )
            )

        return TranscriptExtractionResult(transcripts=transcripts, errors=errors)
