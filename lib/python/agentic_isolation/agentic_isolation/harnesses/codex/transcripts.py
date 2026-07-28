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
    f"printf '%s\\\\n' '{_TRANSCRIPT_ROOT_ABSENT_MARKER}'; exit 0; fi; "
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
        except Exception:  # noqa: BLE001 - a single malformed line (deeply
            # nested JSON raises RecursionError, a RuntimeError subclass,
            # not a ValueError - see issue #792 finding 1) must never lose
            # the rest of the file's lines.
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

    `extract()` MUST NEVER raise (see `TranscriptSource.extract`): every
    exec and every file read is wrapped so one bad transcript can never
    lose the others or abort a workspace teardown. Unknown or extra
    fields in a line are tolerated (`_resolve_session_id` only reads
    what it needs); a malformed line simply fails to yield a session id
    from that line and parsing moves on.
    """

    _exec_fn: ExecFn

    @property
    def agent(self) -> AgentName:
        return AgentName.CODEX

    async def extract(self) -> TranscriptExtractionResult:
        errors: list[str] = []

        try:
            find_result = await self._exec_fn(_FIND_TRANSCRIPTS_COMMAND)
        except Exception as exc:  # noqa: BLE001 - extract() must never raise
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
            except Exception as exc:  # noqa: BLE001 - extract() must never raise
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
            except Exception as exc:  # noqa: BLE001 - extract() must never
                # raise; if session id resolution somehow fails despite its
                # own guard, fall back to the filename stem instead of
                # aborting the whole harvest (issue #792 finding 1).
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
