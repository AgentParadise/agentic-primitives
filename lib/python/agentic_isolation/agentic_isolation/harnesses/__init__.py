"""Per-harness packages.

A workspace may host several agent harnesses (claude, codex, gemini). They
differ in every dimension that matters: where transcripts are written (or
whether they are written at all), how hook events are emitted, how auth is
staged, how the CLI is launched. Scattering that knowledge across the codebase
makes adding a harness a nine-file change and misleads readers about which
paths are live.

A `HarnessPlugin` bundles everything about ONE harness. Slots are optional: a
harness that cannot do a thing returns None rather than raising, so capability
is discovered rather than assumed.

v1 fills the transcript-extraction slot. Hook integration, auth staging and
launch are declared migration targets, not yet moved. See issue #792.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable

ExecFn = Callable[[list[str]], Awaitable[tuple[int, str]]]
"""Run a command inside the workspace, returning (exit_code, stdout)."""


class AgentName(StrEnum):
    """Known agent harnesses that can run inside a workspace."""

    CLAUDE = "claude"
    CODEX = "codex"
    GEMINI = "gemini"

    @classmethod
    def parse(cls, value: str) -> AgentName | None:
        """Case-insensitive lookup; None for an unknown harness.

        Lenient by design: a newer workspace image naming a harness this
        version does not know must be ignored, not fatal.
        """
        try:
            return cls(value.strip().lower())
        except ValueError:
            return None


@dataclass(frozen=True)
class HarnessTranscript:
    """One transcript recovered from a workspace."""

    agent: str
    session_id: str
    lines: list[str] = field(default_factory=list)
    source_path: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "agent": self.agent,
            "session_id": self.session_id,
            "line_count": len(self.lines),
            "source_path": self.source_path,
        }


@dataclass(frozen=True)
class TranscriptExtractionResult:
    """Outcome of recovering every transcript one harness left behind."""

    transcripts: list[HarnessTranscript] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, object]:
        return {
            "transcripts": [t.to_dict() for t in self.transcripts],
            "errors": list(self.errors),
            "success": self.success,
        }


@runtime_checkable
class TranscriptSource(Protocol):
    """Recovers every transcript one harness left in a workspace."""

    @property
    def agent(self) -> str: ...

    async def extract(self) -> TranscriptExtractionResult:
        """Recover all transcripts. MUST NOT raise.

        Transport and parse failures are reported through
        `TranscriptExtractionResult.errors` so a harvest of one harness can
        never abort a workspace teardown.
        """
        ...


@runtime_checkable
class HarnessPlugin(Protocol):
    """Everything the system needs to know about one agent harness.

    Optional slots return None when unsupported. Future slots (hook
    integration, auth staging, launch spec) are added here so a new harness
    remains a single-package change.
    """

    @property
    def name(self) -> str: ...

    def transcript_source(self, exec_fn: ExecFn) -> TranscriptSource | None:
        """A source for this harness's transcripts, or None if it persists none."""
        ...


_REGISTRY: dict[str, HarnessPlugin] = {}


def register_harness(plugin: HarnessPlugin) -> None:
    """Register `plugin`. A new harness joins by registering here."""
    _REGISTRY[plugin.name] = plugin


def get_harness(name: str) -> HarnessPlugin | None:
    """Return the plugin for `name`, or None if unsupported."""
    return _REGISTRY.get(name)


def iter_harnesses() -> tuple[HarnessPlugin, ...]:
    """All registered harness plugins."""
    return tuple(_REGISTRY.values())
