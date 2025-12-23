"""Contract tests for workspace providers.

Verifies all providers implement the required interface correctly.
"""


import pytest

from agentic_isolation import (
    AgenticWorkspace,
    SecurityConfig,
    WorkspaceDockerProvider,
    WorkspaceLocalProvider,
)
from agentic_isolation.providers.base import WorkspaceProvider


class TestProviderContracts:
    """Tests that all providers implement the required interface."""

    @pytest.mark.parametrize(
        "provider_class",
        [WorkspaceDockerProvider, WorkspaceLocalProvider],
    )
    def test_provider_implements_workspace_provider(
        self, provider_class: type
    ) -> None:
        """All providers should implement WorkspaceProvider protocol."""
        provider = provider_class()
        assert isinstance(provider, WorkspaceProvider)

    @pytest.mark.parametrize(
        "provider_class",
        [WorkspaceDockerProvider, WorkspaceLocalProvider],
    )
    def test_provider_has_name(self, provider_class: type) -> None:
        """All providers should have a name property."""
        provider = provider_class()
        assert hasattr(provider, "name")
        assert isinstance(provider.name, str)
        assert len(provider.name) > 0

    @pytest.mark.parametrize(
        "provider_class",
        [WorkspaceDockerProvider, WorkspaceLocalProvider],
    )
    def test_provider_has_create_method(self, provider_class: type) -> None:
        """All providers should have async create method."""
        provider = provider_class()
        assert hasattr(provider, "create")
        assert callable(provider.create)

    @pytest.mark.parametrize(
        "provider_class",
        [WorkspaceDockerProvider, WorkspaceLocalProvider],
    )
    def test_provider_has_destroy_method(self, provider_class: type) -> None:
        """All providers should have async destroy method."""
        provider = provider_class()
        assert hasattr(provider, "destroy")
        assert callable(provider.destroy)

    @pytest.mark.parametrize(
        "provider_class",
        [WorkspaceDockerProvider, WorkspaceLocalProvider],
    )
    def test_provider_has_execute_method(self, provider_class: type) -> None:
        """All providers should have async execute method."""
        provider = provider_class()
        assert hasattr(provider, "execute")
        assert callable(provider.execute)

    @pytest.mark.parametrize(
        "provider_class",
        [WorkspaceDockerProvider, WorkspaceLocalProvider],
    )
    def test_provider_has_stream_method(self, provider_class: type) -> None:
        """All providers should have async stream method."""
        provider = provider_class()
        assert hasattr(provider, "stream")
        assert callable(provider.stream)

    @pytest.mark.parametrize(
        "provider_class",
        [WorkspaceDockerProvider, WorkspaceLocalProvider],
    )
    def test_provider_has_file_methods(self, provider_class: type) -> None:
        """All providers should have file operation methods."""
        provider = provider_class()

        assert hasattr(provider, "write_file")
        assert callable(provider.write_file)

        assert hasattr(provider, "read_file")
        assert callable(provider.read_file)

        assert hasattr(provider, "file_exists")
        assert callable(provider.file_exists)


class TestAgenticWorkspaceContract:
    """Tests that AgenticWorkspace has the expected interface."""

    def test_has_create_classmethod(self) -> None:
        """Should have create classmethod."""
        assert hasattr(AgenticWorkspace, "create")
        assert callable(AgenticWorkspace.create)

    def test_create_returns_instance(self) -> None:
        """create() should return AgenticWorkspace instance."""
        instance = AgenticWorkspace.create(provider="local")
        assert isinstance(instance, AgenticWorkspace)

    def test_has_execute_method(self) -> None:
        """Should have execute method."""
        assert hasattr(AgenticWorkspace, "execute")

    def test_has_stream_method(self) -> None:
        """Should have stream method."""
        assert hasattr(AgenticWorkspace, "stream")

    def test_has_file_methods(self) -> None:
        """Should have file operation methods."""
        assert hasattr(AgenticWorkspace, "write_file")
        assert hasattr(AgenticWorkspace, "read_file")
        assert hasattr(AgenticWorkspace, "file_exists")

    def test_has_properties(self) -> None:
        """Should have id, path, provider_name properties."""
        assert hasattr(AgenticWorkspace, "id")
        assert hasattr(AgenticWorkspace, "path")
        assert hasattr(AgenticWorkspace, "provider_name")


class TestSecurityConfigContract:
    """Tests that SecurityConfig has the expected interface."""

    def test_has_production_classmethod(self) -> None:
        """Should have production() classmethod."""
        assert hasattr(SecurityConfig, "production")
        config = SecurityConfig.production()
        assert isinstance(config, SecurityConfig)

    def test_has_development_classmethod(self) -> None:
        """Should have development() classmethod."""
        assert hasattr(SecurityConfig, "development")
        config = SecurityConfig.development()
        assert isinstance(config, SecurityConfig)

    def test_has_to_docker_run_args(self) -> None:
        """Should have to_docker_run_args() method."""
        config = SecurityConfig()
        assert hasattr(config, "to_docker_run_args")
        args = config.to_docker_run_args()
        assert isinstance(args, list)

    def test_production_vs_development_differ(self) -> None:
        """Production and development configs should differ."""
        prod = SecurityConfig.production()
        dev = SecurityConfig.development()

        # At least one field should differ
        assert prod.read_only_root != dev.read_only_root or prod.use_gvisor != dev.use_gvisor
