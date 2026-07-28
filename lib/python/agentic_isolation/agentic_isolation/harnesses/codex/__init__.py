"""Codex harness package. See issue #792.

Bundles the transcript extraction know-how for the `codex` harness
(OpenAI Codex CLI). See `agentic_isolation.harnesses` for the shared
contract (`HarnessPlugin`, `TranscriptSource`, `ExecFn`) this package
conforms to.

Two DIFFERENT codex output formats exist and must never be confused:

1. The `codex --json` / `codex exec --json` STDOUT event stream: a
   sequence of `thread.started` / `turn.started` / `item.started` /
   `item.completed` events. This is the LIVE run's own output, captured
   by the executor during execution (see the fixtures under
   `packages/syn-domain/tests/fixtures/codex/` in the syn137 repo). It
   is NOT what this package parses.
2. The ON-DISK rollout session file this package DOES parse: one JSONL
   file per session under `$CODEX_HOME/sessions/<yyyy>/<mm>/<dd>/
   rollout-<timestamp>-<uuid>.jsonl` (`$CODEX_HOME` defaults to
   `~/.codex`), confirmed by inspecting a real `~/.codex/sessions/`
   tree on 2026-07-28. See `transcripts.py` for the schema details.

Codex's `--ephemeral` flag explicitly skips persisting rollout files,
so a missing sessions directory is a legitimate, clean, empty result -
not an error.
"""

from __future__ import annotations

from agentic_isolation.harnesses import AgentName, ExecFn, TranscriptSource, register_harness
from agentic_isolation.harnesses.codex.transcripts import CodexTranscriptSource


class CodexHarness:
    """`HarnessPlugin` for the `codex` (OpenAI Codex CLI) harness."""

    @property
    def name(self) -> str:
        return AgentName.CODEX

    def transcript_source(self, exec_fn: ExecFn) -> TranscriptSource | None:
        return CodexTranscriptSource(exec_fn)


register_harness(CodexHarness())

__all__ = ["CodexHarness"]
