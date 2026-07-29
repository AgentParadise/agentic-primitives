"""Transcript extraction for the `codex` (OpenAI Codex CLI) harness.

Real schema recovered on 2026-07-28 by inspecting an ACTUAL
`~/.codex/sessions/` tree on disk - not by reasoning about the codex
`--json` STDOUT event stream, which is a different thing entirely (see
the codex package docstring for both formats and why they must not be
conflated).

Codex writes one rollout JSONL file per session under
`$CODEX_HOME/sessions/<year>/<month>/<day>/rollout-<timestamp>-<uuid>.jsonl`,
where `$CODEX_HOME` defaults to `~/.codex` (confirmed by `codex exec
--help`, which documents `--ignore-user-config` as still using
`$CODEX_HOME` for auth). Each line is a JSON object with a top-level
`type`: `session_meta`, `event_msg`, `response_item`, `turn_context`,
`world_state` were all observed in one real file. Only the
`session_meta` line carries `payload.session_id`.

Codex also has `--ephemeral`, which explicitly skips persisting session
files. A missing (or empty) sessions directory is therefore a clean,
successful, empty result here - not an error - mirroring the "no
transcript root yet" case in the claude source.

`CodexTranscriptSource` recovers every rollout file after the fact via
the workspace's `ExecFn`, never by reaching into the filesystem
directly: the workspace may be a remote container, so all I/O goes
through `exec_fn`.
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

_TRANSCRIPT_ROOT_ABSENT_MARKER = "__agentic_isolation_codex_transcript_root_absent__"
"""Unique stdout marker meaning "the codex sessions root does not exist".

Distinguishes a legitimate empty harvest (codex ran with `--ephemeral`,
or the sessions root was never created) from a real transport failure
(permission denied, unreachable filesystem, ...). An exit code alone
cannot carry this distinction: `ExecFn` itself may fail transport with
any exit code (including one a shell script happens to pick for
"absent"), and `find` reserves no exit code for "the directory never
existed" - see issue #792 (round 2 finding 2). Only an EXACT stdout match
against this marker (exit 0) normalizes to a clean empty
`TranscriptExtractionResult`; any non-zero exit is unconditionally a real
error reported through `errors`. The listing command used to
unconditionally force a zero exit code on `find` failure via a bare
`|| true`, and later a fixed "absent" exit code that a transport failure
could coincidentally reproduce - both swallowed real failures as a clean
empty result.
"""

_FIND_TRANSCRIPTS_COMMAND = (
    'root="${CODEX_HOME:-$HOME/.codex}/sessions"; '
    'if [ ! -d "$root" ]; then '
    # A single backslash reaches the shell here (Python source needs one
    # escaped backslash, `\\n`, to produce that): POSIX `printf` then
    # interprets `\n` in the format string as a real newline. An earlier
    # version had an extra level of escaping (`\\\\n` in the Python
    # source), which put a LITERAL two-character `\n` (backslash then
    # `n`) into the shell command instead of an escape sequence - `printf`
    # emitted that pair verbatim as text, never a newline, so the marker
    # line could never exactly match `_TRANSCRIPT_ROOT_ABSENT_MARKER` and
    # the absent-root path never actually worked in a real shell (issue
    # #792, found by a live-container proof run; every existing test used
    # a fake `exec_fn` that returned the marker directly, so the real
    # shell was never exercised). Proven byte-for-byte with `od -c` after
    # the fix: exactly the marker followed by one `\n` (0x0a), nothing
    # else.
    f"printf '%s\\n' '{_TRANSCRIPT_ROOT_ABSENT_MARKER}'; exit 0; fi; "
    "find \"$root\" -name 'rollout-*.jsonl' -type f"
)

_SESSION_META_TYPE = "session_meta"
"""The only rollout line `type` that carries `payload.session_id` (see
issue #792 finding 2: reading `payload.session_id` off ANY line let an
unrelated record type - or a malformed rollout - yield the wrong id)."""


def _resolve_session_id(lines: list[str], source_path: str) -> str:
    """Prefer the `session_meta` line's `payload.session_id`; fall back
    to the filename stem.

    Only a line whose top-level `type` is `session_meta` (observed
    first in every real rollout file inspected) carries a session id -
    other line types (`event_msg`, `response_item`, `turn_context`,
    `world_state`) do not, even if they happen to contain a
    `payload.session_id`-shaped field. All lines are still scanned,
    tolerant of a reordered or truncated file, rather than assuming
    position - but the `type` check is what actually authorizes reading
    the field.
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
        if parsed.get("type") != _SESSION_META_TYPE:
            continue
        payload = parsed.get("payload")
        if not isinstance(payload, dict):
            continue
        session_id = payload.get("session_id")
        if isinstance(session_id, str) and session_id:
            return session_id
    return Path(source_path).stem


@dataclass
class CodexTranscriptSource:
    """`TranscriptSource` for the `codex` harness.

    `extract()` MUST NEVER raise (see `TranscriptSource.extract`): its
    entire body runs inside one outer `try`/`except Exception` in
    `extract()` itself (issue #792 round 3 finding 1), so nothing after
    the exec awaits - reading `find_result` fields, string processing,
    building dataclasses - can escape either. Per-file guards inside
    `_extract()` still exist on top of that outer boundary so one bad
    transcript can never lose the others. Unknown or extra fields in a
    line are tolerated (`_resolve_session_id` only reads what it needs);
    a malformed line simply fails to yield a session id from that line
    and parsing moves on.
    """

    _exec_fn: ExecFn

    @property
    def agent(self) -> AgentName:
        return AgentName.CODEX

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
            errors.append(f"unexpected error extracting codex transcripts: {exc}")
            return TranscriptExtractionResult(transcripts=[], errors=errors)

    async def _extract(self, errors: list[str]) -> TranscriptExtractionResult:
        try:
            find_result = await self._exec_fn(_FIND_TRANSCRIPTS_COMMAND)
        except Exception as exc:  # noqa: BLE001 - reported with a specific
            # "failed to list" message before falling through to the outer
            # boundary in `extract()`.
            errors.append(f"failed to list codex transcripts: {exc}")
            return TranscriptExtractionResult(transcripts=[], errors=errors)

        if not find_result.success:
            # A non-zero exit is unconditionally a real transport failure -
            # no exit code is treated as an "absent root" sentinel, since
            # `ExecFn` may fail for unrelated reasons and reuse any exit
            # code (issue #792 round 2 finding 2).
            errors.append(
                f"failed to list codex transcripts: exit {find_result.exit_code}: "
                f"{find_result.stderr}"
            )
            return TranscriptExtractionResult(transcripts=[], errors=errors)

        if find_result.stdout.strip() == _TRANSCRIPT_ROOT_ABSENT_MARKER:
            # codex may legitimately have persisted nothing (e.g. run with
            # `--ephemeral`), or the sessions root does not exist yet -
            # authenticated by the exact marker, not merely a zero exit -
            # a clean empty harvest, not an error.
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
                    agent=AgentName.CODEX,
                    session_id=session_id,
                    lines=lines,
                    source_path=path,
                )
            )

        return TranscriptExtractionResult(transcripts=transcripts, errors=errors)
