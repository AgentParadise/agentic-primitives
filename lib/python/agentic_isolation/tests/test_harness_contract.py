"""Contract tests for the per-harness plugin model. See issue #792.

Covers: HarnessPlugin and TranscriptSource are structurally satisfiable;
optional slots return None rather than raising; the registry round-trips
and rejects names AgentName does not recognize; the exec_argv helper
shell-quotes argv exactly once; every bundled harness package is
actually registered (finding 3); `HarnessPlugin.name` and
`HarnessTranscript.agent` are typed `AgentName`, not `str` (finding 4).
"""

from __future__ import annotations

import ast
import inspect
import pkgutil
import subprocess
import sys
from dataclasses import dataclass

import pytest

import agentic_isolation.harnesses as harnesses_pkg
from agentic_isolation.harnesses import (
    AgentName,
    ExecFn,
    HarnessPlugin,
    HarnessTranscript,
    TranscriptExtractionResult,
    TranscriptSource,
    exec_argv,
    get_harness,
    iter_harnesses,
    register_harness,
)
from agentic_isolation.providers.base import ExecuteResult


@dataclass
class _FakeSource:
    _agent: AgentName = AgentName.CLAUDE

    @property
    def agent(self) -> AgentName:
        return self._agent

    async def extract(self) -> TranscriptExtractionResult:
        return TranscriptExtractionResult()


@dataclass
class _FakeHarness:
    _name: AgentName = AgentName.CLAUDE

    @property
    def name(self) -> AgentName:
        return self._name

    def transcript_source(self, exec_fn: ExecFn) -> TranscriptSource | None:
        return _FakeSource()


class _RecordingExec:
    """Minimal stand-in for `Workspace.execute` / `WorkspaceProvider.execute`."""

    def __init__(self) -> None:
        self.commands: list[str] = []

    async def __call__(
        self,
        command: str,
        *,
        timeout: float | None = None,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
    ) -> ExecuteResult:
        self.commands.append(command)
        return ExecuteResult(exit_code=0, stdout="", stderr="")


class TestHarnessContract:
    def test_source_satisfies_protocol(self) -> None:
        assert isinstance(_FakeSource(), TranscriptSource)

    def test_harness_satisfies_protocol(self) -> None:
        assert isinstance(_FakeHarness(), HarnessPlugin)

    def test_agent_name_is_lenient(self) -> None:
        assert AgentName.parse("CLAUDE") is AgentName.CLAUDE
        assert AgentName.parse("unknown-harness") is None

    def test_registry_round_trips(self) -> None:
        register_harness(_FakeHarness())
        assert get_harness("claude") is not None
        assert get_harness("nope") is None

    def test_registry_rejects_names_agentname_does_not_know(self) -> None:
        """A harness must not register under a name the rest of the
        system (AgentName) would never recognize - see issue #792.

        A raw string is passed here on purpose (not an `AgentName`
        member) to exercise a plugin that lies about its own name; the
        `AgentPlugin` contract types `name` as `AgentName`, but nothing
        stops a buggy third-party `HarnessPlugin` from returning
        something else at runtime, which is exactly the case
        `register_harness` must guard against.
        """
        bad_harness = _FakeHarness(_name="not-a-real-harness")  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="unknown harness name"):
            register_harness(bad_harness)

    def test_result_success_flips_on_errors(self) -> None:
        assert TranscriptExtractionResult().success is True
        assert TranscriptExtractionResult(errors=["x"]).success is False

    def test_transcript_to_dict(self) -> None:
        t = HarnessTranscript(
            agent=AgentName.CLAUDE, session_id="s1", lines=["{}"], source_path="/p"
        )
        assert t.to_dict()["session_id"] == "s1"

    def test_transcript_agent_is_agentname(self) -> None:
        """`HarnessTranscript.agent` is the canonical `AgentName` type,
        not a plain `str` - issue #792 finding 4."""
        t = HarnessTranscript(agent=AgentName.CODEX, session_id="s1")
        assert isinstance(t.agent, AgentName)
        assert t.agent is AgentName.CODEX

    def test_bundled_harness_names_are_agentname(self) -> None:
        """Every bundled harness plugin reports its identity as
        `AgentName`, not `str` - issue #792 finding 4."""
        for plugin in iter_harnesses():
            assert isinstance(plugin.name, AgentName)

    async def test_exec_argv_shell_quotes_once(self) -> None:
        recorder = _RecordingExec()
        await exec_argv(recorder, ["echo", "hello world"])
        assert recorder.commands == ["echo 'hello world'"]


def _imported_leaf_names(source: str) -> set[str]:
    """Return the leaf module name of every REAL `import` / `from ...
    import ...` statement in `source` - parsed via `ast`, not substring
    matching, so a name appearing only in a comment or docstring does not
    count (issue #792 round 2 finding 3)."""
    tree = ast.parse(source)
    leaf_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                leaf_names.add(alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                leaf_names.add(alias.name.rsplit(".", 1)[-1])
    return leaf_names


class TestEveryHarnessPackageIsRegistered:
    """Issue #792 finding 3: adding a harness package without wiring it
    into `_register_bundled_harnesses()` is a silent failure today - the
    package imports and type-checks fine, but `get_harness()` never
    resolves it because nothing ever imports it for the module-scope
    `register_harness()` side effect.

    This is a static check on `_register_bundled_harnesses()`'s own
    source rather than a runtime registry check: the registry
    (`_REGISTRY`) is shared, mutable, module-level state that other
    tests in this file (e.g. `test_registry_round_trips`) deliberately
    overwrite with fakes, so asserting against `iter_harnesses()` here
    would be order-dependent. Parsing the function's source into an AST
    and inspecting actual `Import` / `ImportFrom` nodes (round 2 finding
    3 - substring matching would pass even if a subpackage name appeared
    only in a comment or docstring) is exact and immune to that
    pollution.

    The residual requirement to also add a new `AgentName` member is a
    known, accepted limitation - see the `harnesses/__init__.py` module
    docstring.

    Cheap complement only, NOT authoritative (round 3 finding 3): this
    proves a same-named `Import`/`ImportFrom` node exists in the
    function's source, but that is satisfiable by `import unrelated.claude`
    or an import gated behind `if False`, neither of which actually
    registers anything. `TestEveryHarnessPackageResolvesInAFreshInterpreter`
    below is the exact, authoritative check.
    """

    def test_every_harness_subpackage_is_imported_by_bundled_registration(self) -> None:
        from agentic_isolation.harnesses import _register_bundled_harnesses

        harnesses_path = harnesses_pkg.__path__
        subpackage_names = [
            module_info.name
            for module_info in pkgutil.iter_modules(harnesses_path)
            if module_info.ispkg
        ]
        assert subpackage_names, "expected at least one harness subpackage to scan"

        source = inspect.getsource(_register_bundled_harnesses)
        imported = _imported_leaf_names(source)
        missing = [name for name in subpackage_names if name not in imported]
        assert not missing, (
            f"harness subpackage(s) {missing} are not actually imported (by a real "
            "Import/ImportFrom AST node) by _register_bundled_harnesses() in "
            "harnesses/__init__.py - a package that exists but is never imported here "
            "silently never registers (issue #792 finding 3)"
        )

    def test_guard_rejects_a_name_only_present_in_a_comment_or_docstring(self) -> None:
        """A subpackage name that appears only in a comment/docstring -
        never as a real import - must NOT satisfy the guard. This is the
        exact gap round 2 finding 3 identified in the old substring-based
        check."""
        fake_source = (
            "def _register_bundled_harnesses() -> None:\n"
            '    """Docstring mentioning gemini, but never importing it."""\n'
            "    # TODO: also wire up gemini eventually\n"
            "    from agentic_isolation.harnesses import claude as _claude\n"
        )
        imported = _imported_leaf_names(fake_source)
        assert imported == {"claude"}
        assert "gemini" not in imported


class TestEveryHarnessPackageResolvesInAFreshInterpreter:
    """Issue #792 round 3 finding 3: the AST guard above proves only that
    a same-named `Import`/`ImportFrom` node exists somewhere in
    `_register_bundled_harnesses()`'s source - it would accept `import
    unrelated.claude` or an import gated behind `if False`, neither of
    which actually calls `register_harness()`. This test is the exact,
    authoritative check.

    A runtime assertion against `get_harness()` in THIS process would be
    order-dependent: `_REGISTRY` is shared, mutable, module-level state,
    and sibling tests in this file (e.g. `test_registry_round_trips`,
    `test_registry_rejects_names_agentname_does_not_know`) deliberately
    mutate it with fakes / bad names. Spawning a FRESH interpreter via
    `subprocess` sidesteps that entirely: nothing this test suite has
    already done to `_REGISTRY` can leak into the child process, so the
    check is both exact (a real runtime `get_harness()` call, not an AST
    proxy for one) and immune to test execution order.
    """

    def test_every_bundled_harness_resolves_via_get_harness(self) -> None:
        harnesses_path = harnesses_pkg.__path__
        subpackage_names = [
            module_info.name
            for module_info in pkgutil.iter_modules(harnesses_path)
            if module_info.ispkg
        ]
        assert subpackage_names, "expected at least one harness subpackage to scan"

        script_lines = [
            "import agentic_isolation",
            "from agentic_isolation.harnesses import get_harness",
        ]
        for name in subpackage_names:
            message = f"get_harness({name!r}) resolved to None in a fresh interpreter"
            script_lines.append(f"assert get_harness({name!r}) is not None, {message!r}")
        script = "\n".join(script_lines)

        completed = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert completed.returncode == 0, (
            "fresh-interpreter registration check failed for bundled harness "
            f"package(s) {subpackage_names}:\n"
            f"stdout: {completed.stdout}\nstderr: {completed.stderr}"
        )
