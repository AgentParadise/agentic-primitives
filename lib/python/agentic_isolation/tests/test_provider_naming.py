"""Unit tests for provider naming."""

import pytest


class TestProviderNaming:
    """Tests for provider class naming conventions."""

    def test_workspace_docker_provider_exists(self) -> None:
        """WorkspaceDockerProvider should be importable."""
        from agentic_isolation import WorkspaceDockerProvider

        assert WorkspaceDockerProvider is not None
        assert WorkspaceDockerProvider().name == "docker"

    def test_workspace_local_provider_exists(self) -> None:
        """WorkspaceLocalProvider should be importable."""
        from agentic_isolation import WorkspaceLocalProvider

        assert WorkspaceLocalProvider is not None
        assert WorkspaceLocalProvider().name == "local"

    def test_agentic_workspace_exists(self) -> None:
        """AgenticWorkspace should be importable."""
        from agentic_isolation import AgenticWorkspace

        assert AgenticWorkspace is not None


class TestSecurityConfigExports:
    """Tests for SecurityConfig exports."""

    def test_security_config_importable_from_root(self) -> None:
        """SecurityConfig should be importable from agentic_isolation."""
        from agentic_isolation import SecurityConfig

        assert SecurityConfig is not None
        assert hasattr(SecurityConfig, "production")
        assert hasattr(SecurityConfig, "development")

    def test_security_config_in_workspace_config(self) -> None:
        """WorkspaceConfig should have security field."""
        from agentic_isolation import WorkspaceConfig, SecurityConfig

        config = WorkspaceConfig()
        assert hasattr(config, "security")
        assert isinstance(config.security, SecurityConfig)


class TestStreamingMethodExists:
    """Tests for streaming method availability."""

    def test_workspace_docker_provider_has_stream(self) -> None:
        """WorkspaceDockerProvider should have stream method."""
        from agentic_isolation import WorkspaceDockerProvider

        provider = WorkspaceDockerProvider()
        assert hasattr(provider, "stream")
        assert callable(provider.stream)

    def test_workspace_local_provider_has_stream(self) -> None:
        """WorkspaceLocalProvider should have stream method."""
        from agentic_isolation import WorkspaceLocalProvider

        provider = WorkspaceLocalProvider()
        assert hasattr(provider, "stream")
        assert callable(provider.stream)

    def test_agentic_workspace_has_stream(self) -> None:
        """AgenticWorkspace should have stream method."""
        from agentic_isolation import AgenticWorkspace

        # Check class has the method
        assert hasattr(AgenticWorkspace, "stream")
