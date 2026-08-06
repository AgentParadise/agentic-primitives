"""Claude harness package. See issue #792.

Bundles the transcript extraction know-how for the `claude` harness
(Claude Code CLI). See `agentic_isolation.harnesses` for the shared
contract (`HarnessPlugin`, `TranscriptSource`, `ExecFn`) this package
conforms to.
"""

from __future__ import annotations

from agentic_isolation.harnesses import AgentName, ExecFn, TranscriptSource, register_harness
from agentic_isolation.harnesses.claude.transcripts import ClaudeTranscriptSource


class ClaudeHarness:
    """`HarnessPlugin` for the `claude` (Claude Code CLI) harness."""

    @property
    def name(self) -> AgentName:
        return AgentName.CLAUDE

    def transcript_source(self, exec_fn: ExecFn) -> TranscriptSource | None:
        return ClaudeTranscriptSource(exec_fn)


register_harness(ClaudeHarness())

__all__ = ["ClaudeHarness"]
