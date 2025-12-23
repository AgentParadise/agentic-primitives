"""Tests for configuration types."""


from agentic_isolation.config import (
    MountConfig,
    ResourceLimits,
    WorkspaceConfig,
)


class TestResourceLimits:
    """Tests for ResourceLimits."""

    def test_defaults(self) -> None:
        """Should have sensible defaults."""
        limits = ResourceLimits()
        assert limits.cpu == "2"
        assert limits.memory == "4G"
        assert limits.network is True
        assert limits.timeout_seconds == 3600

    def test_to_docker_args(self) -> None:
        """Should convert to Docker arguments."""
        limits = ResourceLimits(cpu="4", memory="8G", network=False)
        args = limits.to_docker_args()

        assert args["cpu_count"] == 4
        assert args["mem_limit"] == "8G"
        assert args["network_mode"] == "none"

    def test_to_docker_args_with_network(self) -> None:
        """Should not set network_mode when network enabled."""
        limits = ResourceLimits(network=True)
        args = limits.to_docker_args()

        assert "network_mode" not in args


class TestMountConfig:
    """Tests for MountConfig."""

    def test_basic_mount(self) -> None:
        """Should create basic mount."""
        mount = MountConfig("/host/path", "/container/path")
        assert mount.host_path == "/host/path"
        assert mount.container_path == "/container/path"
        assert mount.read_only is False

    def test_readonly_mount(self) -> None:
        """Should create read-only mount."""
        mount = MountConfig("/host", "/container", read_only=True)
        assert mount.read_only is True

    def test_to_docker_mount(self) -> None:
        """Should convert to Docker mount spec."""
        mount = MountConfig("/host/data", "/workspace/data", read_only=True)
        docker_mount = mount.to_docker_mount()

        assert docker_mount["type"] == "bind"
        assert docker_mount["target"] == "/workspace/data"
        assert docker_mount["read_only"] is True


class TestWorkspaceConfig:
    """Tests for WorkspaceConfig."""

    def test_defaults(self) -> None:
        """Should have sensible defaults."""
        config = WorkspaceConfig()
        assert config.provider == "local"
        assert config.working_dir == "/workspace"
        assert config.auto_cleanup is True

    def test_chained_configuration(self) -> None:
        """Should support method chaining."""
        config = (
            WorkspaceConfig()
            .with_mount("/host", "/container")
            .with_secret("API_KEY", "secret")
            .with_env("DEBUG", "true")
        )

        assert len(config.mounts) == 1
        assert config.secrets["API_KEY"] == "secret"
        assert config.environment["DEBUG"] == "true"

    def test_with_mount(self) -> None:
        """Should add mount configurations."""
        config = WorkspaceConfig()
        config.with_mount("/host", "/container", read_only=True)

        assert len(config.mounts) == 1
        assert config.mounts[0].host_path == "/host"
        assert config.mounts[0].read_only is True

    def test_with_secret(self) -> None:
        """Should add secrets."""
        config = WorkspaceConfig()
        config.with_secret("TOKEN", "abc123")

        assert config.secrets["TOKEN"] == "abc123"

    def test_with_env(self) -> None:
        """Should add environment variables."""
        config = WorkspaceConfig()
        config.with_env("LOG_LEVEL", "debug")

        assert config.environment["LOG_LEVEL"] == "debug"
