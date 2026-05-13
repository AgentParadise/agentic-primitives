"""Unit tests for agentic_isolation.workspace_files.WorkspaceFiles.

Run with: cd lib/python/agentic_isolation && uv run pytest tests/test_workspace_files.py -v
"""

from pathlib import Path
from unittest.mock import MagicMock


def test_bind_mount_descriptor_shape(tmp_path: Path):
    """bind_mount() returns a docker.types.Mount with the expected
    source/target/type/read_only fields."""
    from agentic_isolation.workspace_files import WorkspaceFiles

    client = MagicMock()
    wf = WorkspaceFiles(client=client)
    mount = wf.bind_mount(tmp_path, "/etc/agentic/workspace", read_only=True)

    # docker.types.Mount stores its config in a dict-like .source/.target
    # accessible attributes; verify either attribute or the internal _data dict.
    # The library represents the mount internally as a serializable dict —
    # we check the dict representation.
    raw = dict(mount)
    assert raw["Target"] == "/etc/agentic/workspace"
    assert raw["Source"] == str(tmp_path.resolve())
    assert raw["Type"] == "bind"
    assert raw["ReadOnly"] is True


def test_bind_mount_resolves_relative_paths(tmp_path: Path, monkeypatch):
    """Relative host_path is resolved to an absolute path in the mount
    descriptor (Docker rejects relative bind sources)."""
    from agentic_isolation.workspace_files import WorkspaceFiles

    # Create a real subdir then chdir into the temp dir so a relative
    # path can be resolved.
    sub = tmp_path / "sub"
    sub.mkdir()
    monkeypatch.chdir(tmp_path)

    wf = WorkspaceFiles(client=MagicMock())
    mount = wf.bind_mount(Path("sub"), "/etc/agentic/workspace", read_only=True)

    raw = dict(mount)
    assert Path(raw["Source"]).is_absolute()
    assert raw["Source"] == str(sub.resolve())


def test_inject_archives_and_calls_put_archive():
    """inject() should tar the supplied bytes under the target basename
    and call docker.client.containers.get(id).put_archive(parent_dir, tar)."""
    from agentic_isolation.workspace_files import WorkspaceFiles

    container = MagicMock()
    client = MagicMock()
    client.containers.get.return_value = container

    wf = WorkspaceFiles(client=client)
    wf.inject("ctr-123", "/workspace/CLAUDE.md", b"hello world\n")

    # Verify lookup + put_archive call shape
    client.containers.get.assert_called_once_with("ctr-123")
    assert container.put_archive.called
    args, kwargs = container.put_archive.call_args
    # First positional: parent dir in container
    assert args[0] == "/workspace"
    # Second positional or 'data' kwarg: bytes — must be a tar archive
    archive_bytes = args[1] if len(args) > 1 else kwargs["data"]
    assert archive_bytes[:4] != b""  # non-empty
    # Quick sanity: tar archives start with the filename bytes in the
    # header at offset 0 — the basename should appear in the first 100 bytes.
    assert b"CLAUDE.md" in archive_bytes[:200]


def test_inject_rejects_relative_path():
    """inject() raises ValueError on non-absolute container_path."""
    from agentic_isolation.workspace_files import WorkspaceFiles

    wf = WorkspaceFiles(client=MagicMock())
    try:
        wf.inject("ctr", "relative/path", b"x")
    except ValueError as e:
        assert "absolute" in str(e)
    else:
        raise AssertionError("expected ValueError")


def test_inject_rejects_empty_basename():
    """inject() raises ValueError on a path whose .name is empty (e.g. /)."""
    from agentic_isolation.workspace_files import WorkspaceFiles

    wf = WorkspaceFiles(client=MagicMock())
    try:
        wf.inject("ctr", "/", b"x")
    except ValueError as e:
        assert "basename" in str(e)
    else:
        raise AssertionError("expected ValueError")
