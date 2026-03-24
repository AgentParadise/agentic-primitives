"""Tests for configuration types."""

import json
from pathlib import Path

import pytest

from agentic_isolation.config import (
    MountConfig,
    ResourceLimits,
    WorkspaceConfig,
    _load_plugin_manifest,
    _resolve_single_env_var,
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


class TestLoadPluginManifest:
    """Tests for _load_plugin_manifest helper."""

    def test_returns_none_for_missing_dir(self, tmp_path: Path) -> None:
        """Should return None when plugin directory has no manifest."""
        assert _load_plugin_manifest(str(tmp_path / "nonexistent")) is None

    def test_returns_none_for_missing_manifest(self, tmp_path: Path) -> None:
        """Should return None when .claude-plugin dir exists but plugin.json doesn't."""
        (tmp_path / ".claude-plugin").mkdir()
        assert _load_plugin_manifest(str(tmp_path)) is None

    def test_loads_valid_manifest(self, tmp_path: Path) -> None:
        """Should parse and return valid plugin.json."""
        plugin_dir = tmp_path / ".claude-plugin"
        plugin_dir.mkdir()
        manifest = {"name": "test-plugin", "requires_env": {"API_KEY": {"secret": True}}}
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest))

        result = _load_plugin_manifest(str(tmp_path))
        assert result is not None
        assert result["name"] == "test-plugin"

    def test_returns_none_for_invalid_json(self, tmp_path: Path) -> None:
        """Should return None for malformed JSON."""
        plugin_dir = tmp_path / ".claude-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text("{invalid json")

        assert _load_plugin_manifest(str(tmp_path)) is None


class TestResolveSingleEnvVar:
    """Tests for _resolve_single_env_var helper."""

    def test_returns_value_when_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return env var value when present."""
        monkeypatch.setenv("TEST_VAR", "hello")
        value, resolved = _resolve_single_env_var("TEST_VAR", {}, "test-plugin")
        assert value == "hello"
        assert resolved is True

    def test_returns_empty_when_unset_optional(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should return empty string for unset optional var."""
        monkeypatch.delenv("TEST_VAR", raising=False)
        value, resolved = _resolve_single_env_var("TEST_VAR", {}, "test-plugin")
        assert value == ""
        assert resolved is False

    def test_raises_when_unset_required(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Should raise ValueError for unset required var."""
        monkeypatch.delenv("REQUIRED_VAR", raising=False)
        with pytest.raises(ValueError, match="requires env var REQUIRED_VAR"):
            _resolve_single_env_var(
                "REQUIRED_VAR",
                {"required": True, "description": "needed"},
                "my-plugin",
            )


class TestResolvePluginEnv:
    """Tests for WorkspaceConfig.resolve_plugin_env."""

    def test_resolves_secret_env_var(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Should add secret env vars to secrets dict."""
        plugin_dir = tmp_path / ".claude-plugin"
        plugin_dir.mkdir()
        manifest = {
            "name": "test-plugin",
            "requires_env": {"API_KEY": {"secret": True}},
        }
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest))
        monkeypatch.setenv("API_KEY", "s3cret")

        config = WorkspaceConfig()
        config.plugins.append(str(tmp_path))
        config.resolve_plugin_env()

        assert config.secrets["API_KEY"] == "s3cret"
        assert "API_KEY" not in config.environment

    def test_resolves_non_secret_env_var(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Should add non-secret env vars to environment dict."""
        plugin_dir = tmp_path / ".claude-plugin"
        plugin_dir.mkdir()
        manifest = {
            "name": "test-plugin",
            "requires_env": {"LOG_LEVEL": {"secret": False}},
        }
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest))
        monkeypatch.setenv("LOG_LEVEL", "debug")

        config = WorkspaceConfig()
        config.plugins.append(str(tmp_path))
        config.resolve_plugin_env()

        assert config.environment["LOG_LEVEL"] == "debug"
        assert "LOG_LEVEL" not in config.secrets

    def test_skips_already_set_vars(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Should not overwrite vars already in secrets or environment."""
        plugin_dir = tmp_path / ".claude-plugin"
        plugin_dir.mkdir()
        manifest = {
            "name": "test-plugin",
            "requires_env": {"API_KEY": {"secret": True}},
        }
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest))
        monkeypatch.setenv("API_KEY", "new-value")

        config = WorkspaceConfig()
        config.secrets["API_KEY"] = "original"
        config.plugins.append(str(tmp_path))
        config.resolve_plugin_env()

        assert config.secrets["API_KEY"] == "original"

    def test_skips_missing_manifest(self, tmp_path: Path) -> None:
        """Should silently skip plugins without manifests."""
        config = WorkspaceConfig()
        config.plugins.append(str(tmp_path / "nonexistent"))
        config.resolve_plugin_env()  # Should not raise

    def test_idempotent(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Should be safe to call multiple times."""
        plugin_dir = tmp_path / ".claude-plugin"
        plugin_dir.mkdir()
        manifest = {
            "name": "test-plugin",
            "requires_env": {"TOKEN": {"secret": True}},
        }
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest))
        monkeypatch.setenv("TOKEN", "abc")

        config = WorkspaceConfig()
        config.plugins.append(str(tmp_path))
        config.resolve_plugin_env()
        config.resolve_plugin_env()  # Second call should be safe

        assert config.secrets["TOKEN"] == "abc"
