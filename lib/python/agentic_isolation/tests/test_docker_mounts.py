"""Mount configuration must reach Docker without changing field boundaries."""

import csv
from pathlib import Path

import pytest

from agentic_isolation import MountConfig, SecurityConfig, WorkspaceConfig, WorkspaceDockerProvider


def command(mounts: list[MountConfig]) -> list[str]:
    return WorkspaceDockerProvider()._build_run_command(
        container_name="test",
        workspace_id="test",
        workspace_dir=Path("/tmp/workspace"),
        image="alpine:3.19",
        config=WorkspaceConfig(mounts=mounts),
        security=SecurityConfig.development(),
    )


def test_named_and_bind_mounts_preserve_sources_and_readonly() -> None:
    source = Path('/tmp/path,with"quotes')
    args = command(
        [
            MountConfig("session-spool", "/spool", kind="volume"),
            MountConfig(source, "/input", read_only=True),
        ]
    )
    mounts = [
        next(csv.reader([args[index + 1]])) for index, arg in enumerate(args) if arg == "--mount"
    ]
    assert mounts == [
        ["type=volume", "source=session-spool", "target=/spool"],
        [
            "type=bind",
            f"source={source.resolve()}",
            "target=/input",
            "readonly",
        ],
    ]
    assert not any(arg.startswith("--tmpfs=/spool:") for arg in args)
    assert any(arg.startswith("--tmpfs=/home/agent:") for arg in args)


@pytest.mark.parametrize("target", ["/workspace", "/workspace/", "/workspace/."])
def test_extra_mount_cannot_replace_workspace(target: str) -> None:
    with pytest.raises(ValueError, match="Duplicate"):
        command([MountConfig("spool", target, kind="volume")])


def test_duplicate_normalized_targets_fail() -> None:
    with pytest.raises(ValueError, match="Duplicate"):
        command(
            [
                MountConfig("first", "/spool", kind="volume"),
                MountConfig("second", "/spool/", kind="volume"),
            ]
        )


@pytest.mark.parametrize(
    "source,target",
    [
        ("/host", "relative"),
        ("/host", "/"),
        ("/host", "//"),
        ("/host", "//workspace"),
        ("/host", "/safe/../spool"),
        ("/host\n", "/spool"),
    ],
)
def test_invalid_paths_fail_before_launch(source: str, target: str) -> None:
    with pytest.raises(ValueError):
        MountConfig(source, target)


@pytest.mark.parametrize("name", ["../escape", "volume,readonly", "-option", "x", ""])
def test_invalid_volume_names_fail(name: str) -> None:
    with pytest.raises(ValueError, match="volume name"):
        MountConfig(name, "/spool", kind="volume")
