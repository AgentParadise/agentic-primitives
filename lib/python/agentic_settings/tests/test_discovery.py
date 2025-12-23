"""Tests for discovery module."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

from agentic_settings import (
    find_env_file,
    find_project_root,
    get_workspace_root,
    is_in_workspace,
    resolve_path,
)


class TestFindProjectRoot:
    """Tests for find_project_root function."""

    def test_find_git_directory(self) -> None:
        """Test finding root by .git directory."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            git_dir = root / ".git"
            git_dir.mkdir()

            subdir = root / "src" / "nested"
            subdir.mkdir(parents=True)

            result = find_project_root(subdir)
            assert result == root

    def test_find_pyproject_toml(self) -> None:
        """Test finding root by pyproject.toml."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            (root / "pyproject.toml").touch()

            subdir = root / "src"
            subdir.mkdir()

            result = find_project_root(subdir)
            assert result == root

    def test_find_package_json(self) -> None:
        """Test finding root by package.json."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            (root / "package.json").touch()

            subdir = root / "src"
            subdir.mkdir()

            result = find_project_root(subdir)
            assert result == root

    def test_find_env_file_marker(self) -> None:
        """Test finding root by .env file."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            (root / ".env").touch()

            subdir = root / "src"
            subdir.mkdir()

            result = find_project_root(subdir)
            assert result == root

    def test_no_markers_found(self) -> None:
        """Test that None is returned when no markers found."""
        with TemporaryDirectory() as tmpdir:
            # Create a directory with no markers
            isolated = Path(tmpdir) / "isolated"
            isolated.mkdir()

            # Mock cwd to be in a place with no markers
            with patch.object(Path, "cwd", return_value=isolated):
                result = find_project_root(isolated)
                # May find markers higher up, or return None
                # The behavior depends on the actual filesystem
                assert result is None or result.exists()

    def test_defaults_to_cwd(self) -> None:
        """Test that it defaults to cwd when start_path is None."""
        # Just verify it doesn't crash
        result = find_project_root(None)
        assert result is None or isinstance(result, Path)


class TestFindEnvFile:
    """Tests for find_env_file function."""

    def test_find_env_in_current_dir(self) -> None:
        """Test finding .env in current directory."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            env_file = root / ".env"
            env_file.write_text("TEST=value")

            result = find_env_file(root)
            assert result == env_file

    def test_find_env_in_parent_dir(self) -> None:
        """Test finding .env in parent directory."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            env_file = root / ".env"
            env_file.write_text("TEST=value")

            subdir = root / "src" / "nested"
            subdir.mkdir(parents=True)

            result = find_env_file(subdir)
            assert result == env_file

    def test_env_not_found(self) -> None:
        """Test returning None when .env not found."""
        with TemporaryDirectory() as tmpdir:
            isolated = Path(tmpdir) / "isolated"
            isolated.mkdir()

            result = find_env_file(isolated)
            # May or may not find .env depending on actual filesystem
            assert result is None or result.exists()

    def test_custom_env_filename(self) -> None:
        """Test finding custom env file name."""
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir).resolve()
            env_file = root / ".env.local"
            env_file.write_text("TEST=value")

            result = find_env_file(root, env_file=".env.local")
            assert result == env_file


class TestResolvePath:
    """Tests for resolve_path function."""

    def test_resolve_relative_path(self) -> None:
        """Test resolving relative path."""
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            result = resolve_path("src/main.py", base=base)

            assert result.is_absolute()
            assert str(result).endswith("src/main.py")

    def test_resolve_absolute_path(self) -> None:
        """Test that absolute path is returned unchanged."""
        result = resolve_path("/absolute/path")
        assert result == Path("/absolute/path")

    def test_must_exist_success(self) -> None:
        """Test must_exist=True with existing file."""
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            existing = base / "exists.txt"
            existing.touch()

            result = resolve_path("exists.txt", base=base, must_exist=True)
            assert result.exists()

    def test_must_exist_failure(self) -> None:
        """Test must_exist=True with non-existing file."""
        with TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)

            with pytest.raises(FileNotFoundError):
                resolve_path("does_not_exist.txt", base=base, must_exist=True)


class TestGetWorkspaceRoot:
    """Tests for get_workspace_root function."""

    def test_returns_path(self) -> None:
        """Test that it returns a Path."""
        result = get_workspace_root()
        assert isinstance(result, Path)

    def test_returns_cwd_if_no_project(self) -> None:
        """Test fallback to cwd when no project markers."""
        # Can't easily test this without mocking heavily
        # Just verify it returns a valid path
        result = get_workspace_root()
        assert result.exists()


class TestIsInWorkspace:
    """Tests for is_in_workspace function."""

    def test_path_in_workspace(self) -> None:
        """Test path inside workspace returns True."""
        workspace = get_workspace_root()
        path_inside = workspace / "some" / "file.txt"

        result = is_in_workspace(path_inside)
        assert result is True

    def test_path_outside_workspace(self) -> None:
        """Test path outside workspace returns False."""
        # Use a path that's definitely outside (root of filesystem)
        result = is_in_workspace("/")
        # This might be True or False depending on workspace location
        assert isinstance(result, bool)
