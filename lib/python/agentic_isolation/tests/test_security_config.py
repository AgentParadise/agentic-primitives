"""Unit tests for SecurityConfig."""

from unittest.mock import MagicMock, patch

from agentic_isolation.config import SecurityConfig


class TestSecurityConfig:
    """Tests for SecurityConfig dataclass."""

    def test_default_is_production_hardened(self) -> None:
        """Default config should have all security features enabled."""
        config = SecurityConfig()

        assert config.cap_drop_all is True
        assert config.no_new_privileges is True
        assert config.read_only_root is True
        assert config.tmpfs_tmp is True
        assert config.tmpfs_home is True
        assert config.pids_limit == 256

    def test_production_classmethod(self) -> None:
        """SecurityConfig.production() should return hardened config."""
        config = SecurityConfig.production()

        assert config.cap_drop_all is True
        assert config.no_new_privileges is True
        assert config.read_only_root is True
        assert config.pids_limit == 256

    def test_development_classmethod(self) -> None:
        """SecurityConfig.development() should return relaxed config."""
        config = SecurityConfig.development()

        # These should be relaxed for development
        assert config.read_only_root is False
        assert config.use_gvisor is False

        # These should still be secure
        assert config.cap_drop_all is True
        assert config.no_new_privileges is True

    def test_to_docker_run_args_includes_all_flags(self) -> None:
        """to_docker_run_args() should generate all security flags."""
        config = SecurityConfig.production()
        # Force gvisor off for predictable test
        config.use_gvisor = False

        args = config.to_docker_run_args()

        assert "--cap-drop=ALL" in args
        assert "--security-opt=no-new-privileges" in args
        assert "--read-only" in args
        assert "--tmpfs=/tmp:rw,noexec,nosuid,size=256m" in args
        assert "--tmpfs=/home/agent:rw,exec,nosuid,size=128m,uid=1000,gid=1000" in args
        assert "--pids-limit=256" in args
        # gvisor disabled, so no runtime flag
        assert "--runtime=runsc" not in args

    def test_to_docker_run_args_with_gvisor(self) -> None:
        """to_docker_run_args() should include gVisor runtime when enabled."""
        config = SecurityConfig(use_gvisor=True)

        args = config.to_docker_run_args()

        assert "--runtime=runsc" in args

    def test_to_docker_run_args_respects_disabled_features(self) -> None:
        """Disabled features should not appear in docker args."""
        config = SecurityConfig(
            cap_drop_all=False,
            read_only_root=False,
            tmpfs_tmp=False,
            use_gvisor=False,
        )

        args = config.to_docker_run_args()

        assert "--cap-drop=ALL" not in args
        assert "--read-only" not in args
        assert "--tmpfs=/tmp:rw,noexec,nosuid,size=256m" not in args

    def test_custom_pids_limit(self) -> None:
        """Custom pids_limit should be used."""
        config = SecurityConfig(pids_limit=512)

        args = config.to_docker_run_args()

        assert "--pids-limit=512" in args

    def test_pids_limit_zero_not_included(self) -> None:
        """pids_limit of 0 should not be included (unlimited)."""
        config = SecurityConfig(pids_limit=0, use_gvisor=False)

        args = config.to_docker_run_args()

        # Should not have any pids-limit arg
        assert not any("pids-limit" in arg for arg in args)


class TestSecurityConfigGVisorDetection:
    """Tests for gVisor auto-detection."""

    @patch("shutil.which")
    def test_detect_gvisor_no_docker(self, mock_which: MagicMock) -> None:
        """Should return False if docker is not installed."""
        mock_which.return_value = None

        result = SecurityConfig.detect_gvisor()

        assert result is False

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_detect_gvisor_with_runsc(self, mock_run: MagicMock, mock_which: MagicMock) -> None:
        """Should return True if runsc runtime is available."""
        mock_which.return_value = "/usr/bin/docker"
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"runc":{},"runsc":{}}',
        )

        result = SecurityConfig.detect_gvisor()

        assert result is True

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_detect_gvisor_without_runsc(self, mock_run: MagicMock, mock_which: MagicMock) -> None:
        """Should return False if runsc runtime is not available."""
        mock_which.return_value = "/usr/bin/docker"
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"runc":{}}',
        )

        result = SecurityConfig.detect_gvisor()

        assert result is False

    @patch("shutil.which")
    @patch("subprocess.run")
    def test_detect_gvisor_docker_error(self, mock_run: MagicMock, mock_which: MagicMock) -> None:
        """Should return False if docker info fails."""
        mock_which.return_value = "/usr/bin/docker"
        mock_run.return_value = MagicMock(returncode=1, stdout="")

        result = SecurityConfig.detect_gvisor()

        assert result is False
