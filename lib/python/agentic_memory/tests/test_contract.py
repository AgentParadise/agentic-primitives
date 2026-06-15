"""Unit tests for agentic_memory.contract."""

from __future__ import annotations

import pytest

from agentic_memory.contract import (
    MemoryContract,
    NamespaceKind,
    is_namespace_well_formed,
    is_provider_well_formed,
    sanitize_namespace,
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
        assert MemoryContract.from_env({"AGENTIC_MEMORY_PROVIDER": ""}) is None
        assert MemoryContract.from_env({"AGENTIC_MEMORY_PROVIDER": "none"}) is None
        assert MemoryContract.from_env({"AGENTIC_MEMORY_PROVIDER": "NONE"}) is None

    def test_minimal_contract(self):
        c = MemoryContract.from_env(
            {
                "AGENTIC_MEMORY_PROVIDER": "hindsight",
                "AGENTIC_MEMORY_NAMESPACE": "task-abc",
                "AGENTIC_MEMORY_URL": "http://hindsight:8888",
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
                "AGENTIC_MEMORY_PROVIDER": "hindsight",
                "AGENTIC_MEMORY_NAMESPACE": "wf:phase-1",
                "AGENTIC_MEMORY_URL": "http://hindsight:8888",
                "AGENTIC_MEMORY_NAMESPACE_KIND": "workflow",
                "AGENTIC_MEMORY_AUTH": "hsk_abc123",
                "AGENTIC_MEMORY_CONFIG_JSON": '{"recallAdditionalBanks": ["shared"]}',
            }
        )
        assert c is not None
        assert c.namespace_kind == NamespaceKind.WORKFLOW
        assert c.auth == "hsk_abc123"
        assert c.config_dict == {"recallAdditionalBanks": ["shared"]}

    def test_invalid_config_json_does_not_raise(self):
        c = MemoryContract.from_env(
            {
                "AGENTIC_MEMORY_PROVIDER": "hindsight",
                "AGENTIC_MEMORY_NAMESPACE": "x",
                "AGENTIC_MEMORY_URL": "http://x:1",
                "AGENTIC_MEMORY_CONFIG_JSON": "{not-valid-json",
            }
        )
        assert c is not None
        assert c.config_json == "{not-valid-json"
        assert c.config_dict is None  # parse failed but contract still constructible

    def test_whitespace_stripped(self):
        c = MemoryContract.from_env(
            {
                "AGENTIC_MEMORY_PROVIDER": "  hindsight  ",
                "AGENTIC_MEMORY_NAMESPACE": "  task-x  ",
                "AGENTIC_MEMORY_URL": "  http://x:1  ",
            }
        )
        assert c is not None
        assert c.provider == "hindsight"
        assert c.namespace == "task-x"
        assert c.url == "http://x:1"

    def test_missing_required_does_not_raise(self):
        """from_env() returns a contract even with missing required vars —
        the doctor's job to surface the issue, not from_env's."""
        c = MemoryContract.from_env({"AGENTIC_MEMORY_PROVIDER": "hindsight"})
        assert c is not None
        assert c.namespace == ""
        assert c.url is None
