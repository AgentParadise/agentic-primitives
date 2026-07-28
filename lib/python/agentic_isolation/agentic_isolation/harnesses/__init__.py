"""Per-harness packages.

A workspace may host several agent harnesses (claude, codex, gemini). They
differ in every dimension that matters: where transcripts are written (or
whether they are written at all), how hook events are emitted, how the CLI
parses its own output. Scattering that knowledge across the codebase makes
adding a harness a nine-file change and misleads readers about which paths
are live.

A `HarnessPlugin` bundles everything the system needs to know about ONE
harness's own output. It does NOT own launch or auth: `RunExecutor` already
launches a harness process and `WorkspaceExecutor` already stages
credentials into the workspace (see `agent_run_spec.py` /
`agent_run_result.py`). `HarnessPlugin` is scoped to transcript extraction
today, and later harness-specific output parsing - never to launch or auth.

v1 fills the transcript-extraction slot. See issue #792.

Known limitation (codex review, 2026-07-28): adding a THIRD bundled
harness package still requires two central edits - a new `AgentName`
member above, and a new import line in `_register_bundled_harnesses()`
below. A forgotten import is a silent, not a loud, failure: the package
exists and type-checks but `get_harness()` never resolves it. There is
no fully automatic discovery mechanism today; `tests/test_harness_contract.py`
(`test_every_harness_package_is_registered`) makes a forgotten import a
loud CI failure by scanning `harnesses/` for `HarnessPlugin`
implementations and asserting each is reachable through `get_harness()`.
Treat that test as the enforcement point, not this docstring.

Reconciliation note (2026-07-28, codex recon): `AgentRecipe.agent`
(`recipe.py`) is still `Literal["claude", "codex"]`, a second authority
alongside `AgentName` below. Unifying them was attempted here and reverted:
`tests/test_recipe.py::test_unknown_agent_rejected` mirrors the APSS Agent
Recipe Standard's invalid-example fixture and requires `agent="gemini"` to
be REJECTED by `AgentRecipe`, whereas `AgentName` already knows `GEMINI` as
a valid harness (a workspace can host a gemini harness before the recipe
spec accepts gemini recipes). Making `AgentRecipe` consume `AgentName`
as-is would silently flip that spec-conformance test to green for the
wrong reason. Reconciling the two needs either a recipe-scoped subset type
or an update to the APSS spec fixtures, not a one-line type swap. Left as
a follow-up; `AgentRecipe` is unchanged.
"""

from __future__ import annotations

import shlex
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable

from agentic_isolation.providers.base import ExecuteResult


class ExecFn(Protocol):
    """Run a command inside a workspace.

    Matches `Workspace.execute` / `WorkspaceProvider.execute`
    (`workspace.py`, `providers/base.py`) exactly: a shell `command`
    string in, an `ExecuteResult` out. A bound `workspace.execute` method
    can be passed directly as an `ExecFn`, no adapter required.

    Harnesses that want to build a command from an argument list should
    use `exec_argv()` below rather than repeating shell-quoting logic.
    """

    async def __call__(
        self,
        command: str,
        *,
        timeout: float | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> ExecuteResult: ...


async def exec_argv(
    exec_fn: ExecFn,
    argv: Sequence[str],
    *,
    timeout: float | None = None,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> ExecuteResult:
    """Run `argv` through `exec_fn` as a single shell-quoted command.

    `Workspace.execute` / `WorkspaceProvider.execute` take a shell string,
    not argv. This is the ONE place that does `shlex.join(argv)` so every
    harness implementation builds commands the same, safe way instead of
    each reinventing shell quoting.
    """
    return await exec_fn(shlex.join(argv), timeout=timeout, cwd=cwd, env=env)


class AgentName(StrEnum):
    """Known agent harnesses that can run inside a workspace.

    The single canonical harness-name authority for the transcript
    contract in this module. See the module docstring for the current
    (deliberate) gap with `AgentRecipe.agent`.
    """

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
    """One DURABLE transcript recovered from a workspace after the fact.

    Contrast with `AgentRunResult.session_log` (`agent_run_result.py`),
    which is the LIVE run's own output captured by the executor during
    execution. `HarnessTranscript` is produced later, by harvesting
    whatever a harness persisted to disk (or nothing, if it persists
    nothing) - a parent run can have zero, one, or several of these
    (e.g. a delegated child session writes its own file with a distinct
    `session_id`). The two are never the same object and must not be
    conflated.
    """

    agent: AgentName
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
    """Outcome of recovering every DURABLE transcript one harness left behind.

    See `HarnessTranscript` for how this differs from the live run's
    `AgentRunResult.session_log`.
    """

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
    """Recovers every DURABLE transcript one harness left in a workspace.

    Not the live run's output (see `HarnessTranscript`) - a harvest that
    runs after the fact, typically just before workspace teardown.
    """

    @property
    def agent(self) -> AgentName: ...

    async def extract(self) -> TranscriptExtractionResult:
        """Recover all transcripts. MUST NOT raise.

        Transport and parse failures are reported through
        `TranscriptExtractionResult.errors` so a harvest of one harness can
        never abort a workspace teardown.
        """
        ...


@runtime_checkable
class HarnessPlugin(Protocol):
    """Everything the system needs to know about one harness's own output.

    Scoped to transcript extraction today, and later harness-specific
    output parsing. It does NOT own launch (that is `RunExecutor`'s job)
    or credential staging (that is `WorkspaceExecutor`'s job) - see the
    module docstring. Optional slots return None when unsupported, so
    capability is discovered rather than assumed.
    """

    @property
    def name(self) -> AgentName: ...

    def transcript_source(self, exec_fn: ExecFn) -> TranscriptSource | None:
        """A source for this harness's transcripts, or None if it persists none."""
        ...


_REGISTRY: dict[AgentName, HarnessPlugin] = {}
"""Typed registry of the bundled harness plugins, keyed by `AgentName`.

Not a free-form `dict[str, HarnessPlugin]`: a plugin can only be
registered under a name `AgentName` already recognizes, so `AgentName`
stays the single arbiter of "is this a real harness name" for this
registry (`register_harness()` used to accept any string, which let a
harness register under a name `AgentRecipe`/`AgentName` would both
reject - see issue #792). No third-party (out-of-tree) harness has been
identified yet; if one shows up, this is the extension point.
"""


def register_harness(plugin: HarnessPlugin) -> None:
    """Register `plugin` under its own `name`.

    Raises `ValueError` if `plugin.name` is not a known `AgentName` - a
    harness cannot register itself under a name the rest of the system
    would never recognize.
    """
    parsed = AgentName.parse(plugin.name)
    if parsed is None:
        raise ValueError(f"unknown harness name: {plugin.name!r}")
    _REGISTRY[parsed] = plugin


def get_harness(name: str) -> HarnessPlugin | None:
    """Return the plugin for `name`, or None if unsupported."""
    parsed = AgentName.parse(name)
    if parsed is None:
        return None
    return _REGISTRY.get(parsed)


def iter_harnesses() -> tuple[HarnessPlugin, ...]:
    """All registered harness plugins."""
    return tuple(_REGISTRY.values())


def _register_bundled_harnesses() -> None:
    """Import the bundled harness packages for their registration side effect.

    `harnesses.claude` / `harnesses.codex` each call `register_harness()` at
    module scope, so importing them here (once, at the bottom of this
    module, after every name they import from this module is already
    defined) is enough to make `get_harness("claude")` / `get_harness("codex")`
    resolve for any consumer that only does `import agentic_isolation` -
    no separate opt-in import required. Not a circular import: these
    submodules import names (`AgentName`, `register_harness`, ...) that are
    already bound in this module's namespace by the time this function runs.
    """
    from agentic_isolation.harnesses import claude as _claude  # noqa: F401
    from agentic_isolation.harnesses import codex as _codex  # noqa: F401


_register_bundled_harnesses()
