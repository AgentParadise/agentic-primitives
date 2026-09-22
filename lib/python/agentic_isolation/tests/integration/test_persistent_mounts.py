"""A capture volume survives abrupt container loss and workspace removal."""

import subprocess
import uuid
from pathlib import Path

import pytest

from agentic_isolation import MountConfig, SecurityConfig, WorkspaceConfig, WorkspaceDockerProvider


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(not WorkspaceDockerProvider.is_available(), reason="Docker not available")
async def test_spool_survives_kill_and_workspace_replacement(tmp_path: Path) -> None:
    volume = f"agentic-test-spool-{uuid.uuid4().hex}"
    provider = WorkspaceDockerProvider(
        default_image="alpine:3.19",
        default_network="bridge",
        security=SecurityConfig.development(),
        workspace_base_dir=tmp_path,
    )
    config = WorkspaceConfig(
        image="alpine:3.19", mounts=[MountConfig(volume, "/spool", kind="volume")]
    )
    first = None
    second = None
    try:
        first = await provider.create(config)
        written = await provider.execute(
            first, "printf 'native evidence\\n' > /spool/transcript && sync"
        )
        assert written.exit_code == 0, written.stderr
        subprocess.run(
            ["docker", "kill", first.metadata["container_name"]], check=True, capture_output=True
        )
        await provider.destroy(first)
        first = None
        second = await provider.create(config)
        restored = await provider.execute(second, "cat /spool/transcript")
        assert restored.exit_code == 0, restored.stderr
        assert restored.stdout == "native evidence\n"
    finally:
        if first is not None:
            await provider.destroy(first)
        if second is not None:
            await provider.destroy(second)
        subprocess.run(["docker", "volume", "rm", volume], check=True, capture_output=True)
