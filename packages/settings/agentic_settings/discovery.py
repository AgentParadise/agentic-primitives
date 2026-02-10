"""Environment and project discovery utilities."""

from __future__ import annotations

from pathlib import Path


def find_project_root(start_path: Path | str | None = None) -> Path | None:
    """Find the project root by searching for marker files.

    Searches upward from start_path for common project root markers:
    - .git directory
    - pyproject.toml
    - package.json
    - Cargo.toml
    - .env file

    Args:
        start_path: Starting directory for search. Defaults to current working directory.

    Returns:
        Path to project root, or None if not found.
    """
    if start_path is None:
        start_path = Path.cwd()
    else:
        start_path = Path(start_path)

    # Markers that indicate project root (in priority order)
    markers = [".git", "pyproject.toml", "package.json", "Cargo.toml", ".env"]

    current = start_path.resolve()
    root = Path(current.anchor)  # Filesystem root (/ on Unix, C:\ on Windows)

    while current != root:
        for marker in markers:
            if (current / marker).exists():
                return current
        current = current.parent

    # Check root as well
    for marker in markers:
        if (root / marker).exists():
            return root

    return None


def find_env_file(
    start_path: Path | str | None = None,
    env_file: str = ".env",
) -> Path | None:
    """Find the .env file by searching upward from start_path.

    Args:
        start_path: Starting directory for search. Defaults to current working directory.
        env_file: Name of the env file to find. Defaults to ".env".

    Returns:
        Path to .env file, or None if not found.
    """
    if start_path is None:
        start_path = Path.cwd()
    else:
        start_path = Path(start_path)

    current = start_path.resolve()
    root = Path(current.anchor)

    # Search upward
    while current != root:
        env_path = current / env_file
        if env_path.is_file():
            return env_path
        current = current.parent

    # Check root
    env_path = root / env_file
    if env_path.is_file():
        return env_path

    return None


def get_env_files_to_search(start_path: Path | str | None = None) -> list[str]:
    """Get list of paths that would be searched for .env file.

    Useful for error messages when .env is not found.

    Args:
        start_path: Starting directory for search.

    Returns:
        List of paths that would be searched.
    """
    if start_path is None:
        start_path = Path.cwd()
    else:
        start_path = Path(start_path)

    current = start_path.resolve()
    root = Path(current.anchor)
    paths: list[str] = []

    while current != root:
        paths.append(str(current / ".env"))
        current = current.parent

    paths.append(str(root / ".env"))
    return paths


def resolve_path(
    path: str | Path,
    base: Path | None = None,
    must_exist: bool = False,
) -> Path:
    """Resolve a path, making it absolute.

    Args:
        path: The path to resolve (can be relative or absolute)
        base: Base path for relative paths. Defaults to project root or cwd.
        must_exist: If True, raise FileNotFoundError if path doesn't exist.

    Returns:
        Resolved absolute path.

    Raises:
        FileNotFoundError: If must_exist=True and path doesn't exist.
    """
    path = Path(path)

    if path.is_absolute():
        resolved = path
    else:
        if base is None:
            base = find_project_root() or Path.cwd()
        resolved = (base / path).resolve()

    if must_exist and not resolved.exists():
        raise FileNotFoundError(f"Path does not exist: {resolved}")

    return resolved


def get_workspace_root() -> Path:
    """Get the workspace/project root directory.

    Returns project root if found, otherwise current working directory.

    Returns:
        Path to workspace root.
    """
    return find_project_root() or Path.cwd()


def is_in_workspace(path: Path | str) -> bool:
    """Check if a path is within the workspace root.

    Args:
        path: Path to check.

    Returns:
        True if path is within workspace.
    """
    path = Path(path).resolve()
    workspace = get_workspace_root().resolve()

    try:
        path.relative_to(workspace)
        return True
    except ValueError:
        return False
