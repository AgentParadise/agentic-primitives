"""Unit tests for agentic_memory.contract."""

from __future__ import annotations

import pathlib
import re

import pytest

from agentic_memory.contract import (
    CAPABILITY,
    Env,
    MemoryContract,
    NamespaceKind,
    capability_env_name,
    is_namespace_well_formed,
    is_provider_well_formed,
    sanitize_namespace,
)


def test_env_names_follow_the_adr_038_rule():
    """Every name in Env must match AGENTIC_<CAP>_<FIELD>.

    This is what keeps the enum honest: a typo'd literal in Env fails here
    rather than silently reading a variable nobody sets.
    """
    for member in Env:
        assert member == capability_env_name(CAPABILITY, member.name), (
            f"{member.name} = {member!s} violates the AGENTIC_<CAP>_<FIELD> rule"
        )


class TestNamespaceKind:
    def test_parses_known_values(self):
        assert NamespaceKind.parse("task") == NamespaceKind.TASK
        assert NamespaceKind.parse("WORKFLOW") == NamespaceKind.WORKFLOW
        assert NamespaceKind.parse("Domain") == NamespaceKind.DOMAIN

    def test_unknown_falls_back_to_custom(self):
        assert NamespaceKind.parse("nonsense") == NamespaceKind.CUSTOM

    def test_empty_or_none_defaults_to_task(self):
        assert NamespaceKind.parse(None) == NamespaceKind.TASK
        assert NamespaceKind.parse("") == NamespaceKind.TASK


class TestNamespaceValidation:
    @pytest.mark.parametrize(
        "namespace",
        [
            "task-abc",
            "task_abc",
            "task.abc",
            "task:abc",
            "ABC123",
            "team-product-alpha",
            "workflow:phase-1",
        ],
    )
    def test_well_formed_namespaces(self, namespace):
        assert is_namespace_well_formed(namespace) is True

    @pytest.mark.parametrize(
        "namespace",
        [
            "",
            "task abc",  # space
            "task/abc",  # slash
            "task\\abc",  # backslash
            "task;abc",  # semicolon
            "task$abc",  # dollar
            "task\nabc",  # newline
            "task|abc",  # pipe
        ],
    )
    def test_ill_formed_namespaces(self, namespace):
        assert is_namespace_well_formed(namespace) is False

    def test_sanitization(self):
        assert sanitize_namespace("task abc/v2") == "task-abc-v2"
        assert sanitize_namespace("task   abc") == "task-abc"
        assert sanitize_namespace("---task---") == "task"
        assert sanitize_namespace("") == "unnamed"
        assert sanitize_namespace("$$$") == "unnamed"


class TestProviderValidation:
    @pytest.mark.parametrize("provider", ["hindsight", "lossless-claw", "provider_1", "v1.2"])
    def test_well_formed_providers(self, provider):
        assert is_provider_well_formed(provider) is True

    @pytest.mark.parametrize(
        "provider",
        [
            "",
            "../evil",
            "evil/provider",
            "evil provider",
            "evil;provider",
            ".hidden",
            "evil..provider",
        ],
    )
    def test_ill_formed_providers(self, provider):
        assert is_provider_well_formed(provider) is False


class TestMemoryContractFromEnv:
    def test_no_provider_returns_none(self):
        assert MemoryContract.from_env({}) is None
        assert MemoryContract.from_env({Env.PROVIDER: ""}) is None
        assert MemoryContract.from_env({Env.PROVIDER: "none"}) is None
        assert MemoryContract.from_env({Env.PROVIDER: "NONE"}) is None

    def test_minimal_contract(self):
        c = MemoryContract.from_env(
            {
                Env.PROVIDER: "hindsight",
                Env.NAMESPACE: "task-abc",
                Env.URL: "http://hindsight:8888",
            }
        )
        assert c is not None
        assert c.provider == "hindsight"
        assert c.namespace == "task-abc"
        assert c.url == "http://hindsight:8888"
        assert c.namespace_kind == NamespaceKind.TASK  # default
        assert c.auth is None
        assert c.config_json is None
        assert c.config_dict is None

    def test_full_contract(self):
        c = MemoryContract.from_env(
            {
                Env.PROVIDER: "hindsight",
                Env.NAMESPACE: "wf:phase-1",
                Env.URL: "http://hindsight:8888",
                Env.NAMESPACE_KIND: "workflow",
                Env.AUTH: "hsk_abc123",
                Env.CONFIG_JSON: '{"recallAdditionalBanks": ["shared"]}',
            }
        )
        assert c is not None
        assert c.namespace_kind == NamespaceKind.WORKFLOW
        assert c.auth == "hsk_abc123"
        assert c.config_dict == {"recallAdditionalBanks": ["shared"]}

    def test_invalid_config_json_does_not_raise(self):
        c = MemoryContract.from_env(
            {
                Env.PROVIDER: "hindsight",
                Env.NAMESPACE: "x",
                Env.URL: "http://x:1",
                Env.CONFIG_JSON: "{not-valid-json",
            }
        )
        assert c is not None
        assert c.config_json == "{not-valid-json"
        assert c.config_dict is None  # parse failed but contract still constructible

    def test_whitespace_stripped(self):
        c = MemoryContract.from_env(
            {
                Env.PROVIDER: "  hindsight  ",
                Env.NAMESPACE: "  task-x  ",
                Env.URL: "  http://x:1  ",
            }
        )
        assert c is not None
        assert c.provider == "hindsight"
        assert c.namespace == "task-x"
        assert c.url == "http://x:1"

    def test_missing_required_does_not_raise(self):
        """from_env() returns a contract even with missing required vars —
        the doctor's job to surface the issue, not from_env's."""
        c = MemoryContract.from_env({Env.PROVIDER: "hindsight"})
        assert c is not None
        assert c.namespace == ""
        assert c.url is None


PKG = pathlib.Path(__file__).resolve().parent.parent
_PREFIX = capability_env_name(CAPABILITY, "")
LITERAL = re.compile(rf'"{re.escape(_PREFIX)}[A-Z_]+"')


def test_no_env_name_literals_outside_the_enum():
    """Only contract.py's Env block may spell these names as literals.

    Scans both the package and its tests/ directory — the regex is derived
    from CAPABILITY (via the same `capability_env_name` rule Env's members
    are built from) rather than a hardcoded prefix, so a capability rename
    keeps this guard honest instead of silently going stale.
    """
    skip_dirs = {".venv", "__pycache__", "build", "dist"}
    offenders = []
    for path in PKG.rglob("*.py"):
        if skip_dirs & set(path.relative_to(PKG).parts):
            continue
        if any(part.endswith(".egg-info") for part in path.parts):
            continue
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if not LITERAL.search(line):
                continue
            # The Env class body is the one legal home for these literals.
            if path.name == "contract.py" and any(
                line.strip().startswith(f"{m.name} =") for m in Env
            ):
                continue
            offenders.append(f"{path.name}:{lineno}: {line.strip()}")
    assert not offenders, "use Env.<NAME> instead of a literal:\n" + "\n".join(offenders)
