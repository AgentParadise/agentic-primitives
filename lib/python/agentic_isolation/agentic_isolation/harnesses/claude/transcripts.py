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

_TRANSCRIPT_ROOT_ABSENT_EXIT_CODE = 9
"""Sentinel exit code meaning "the transcript root does not exist".

Distinguishes a legitimate empty harvest (workspace never wrote
`~/.claude/projects`) from a real transport failure (permission denied,
unreachable filesystem, ...). Only this exit code normalizes to a clean
empty `TranscriptExtractionResult`; every other non-zero exit is a real
error and is reported through `errors` - see issue #792 (finding 1: the
listing command used to unconditionally force a zero exit code,
swallowing every `find` failure as a clean empty result and making
transport failures unreportable).
"""

_FIND_TRANSCRIPTS_COMMAND = (
    'root="$HOME/.claude/projects"; '
    f'if [ ! -d "$root" ]; then exit {_TRANSCRIPT_ROOT_ABSENT_EXIT_CODE}; fi; '
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
        except (json.JSONDecodeError, ValueError):
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

    `extract()` MUST NEVER raise (see `TranscriptSource.extract`): every
    exec and every file read is wrapped so one bad transcript can never
    lose the others or abort a workspace teardown.
    """

    _exec_fn: ExecFn

    @property
    def agent(self) -> AgentName:
        return AgentName.CLAUDE

    async def extract(self) -> TranscriptExtractionResult:
        errors: list[str] = []

        try:
            find_result = await self._exec_fn(_FIND_TRANSCRIPTS_COMMAND)
        except Exception as exc:  # noqa: BLE001 - extract() must never raise
            errors.append(f"failed to list claude transcripts: {exc}")
            return TranscriptExtractionResult(transcripts=[], errors=errors)

        if not find_result.success:
            if find_result.exit_code == _TRANSCRIPT_ROOT_ABSENT_EXIT_CODE:
                # The transcript root does not exist yet in this
                # workspace - a legitimate empty harvest, not an error.
                return TranscriptExtractionResult(transcripts=[], errors=[])
            errors.append(
                f"failed to list claude transcripts: exit {find_result.exit_code}: "
                f"{find_result.stderr}"
            )
            return TranscriptExtractionResult(transcripts=[], errors=errors)

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
            session_id = _resolve_session_id(lines, path)
            transcripts.append(
                HarnessTranscript(
                    agent=AgentName.CLAUDE,
                    session_id=session_id,
                    lines=lines,
                    source_path=path,
                )
            )

        return TranscriptExtractionResult(transcripts=transcripts, errors=errors)
