"""WorkspaceFiles — primitive for staging files into a workspace container.

Two complementary modes:

  bind_mount(host, ctr, read_only) -> docker.types.Mount
    Host-resident static content. Returns a Mount descriptor the caller
    passes to client.containers.create(mounts=[...]). Cheap, no copy.

  inject(container_id, ctr_path, content: bytes) -> None
    Generated / object-storage / remote-daemon content. Streams a
    single-file tar archive into a (created, not yet started) container.

See: docs/superpowers/specs/2026-05-12-workspace-injection-contract-design.md §6
"""

from __future__ import annotations

import io
import tarfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import docker
    import docker.types


@dataclass
class WorkspaceFiles:
    """Stage files into a workspace container before it starts.

    `client` is a docker.DockerClient. The helper does not own the
    client — callers pass in whatever client they're already using.
    """

    client: "docker.DockerClient"

    def bind_mount(
        self,
        host_path: Path,
        container_path: str,
        read_only: bool = True,
    ) -> "docker.types.Mount":
        """Build a Mount descriptor for `containers.create(mounts=[...])`.

        Relative host_paths are resolved to absolute paths (Docker rejects
        relative bind sources). The descriptor is a plain ``docker.types.Mount``
        the caller hands to the docker SDK unmodified.
        """
        from docker.types import Mount

        return Mount(
            target=container_path,
            source=str(Path(host_path).resolve()),
            type="bind",
            read_only=read_only,
        )

    def inject(
        self,
        container_id: str,
        container_path: str,
        content: bytes,
    ) -> None:
        """Stream ``content`` into the container as a single-file tar archive
        at ``container_path``.

        Must be called after ``containers.create()`` and before
        ``container.start()`` — the put_archive API requires the container
        to exist but works regardless of running state.
        """
        target = Path(container_path)
        parent = str(target.parent)
        basename = target.name

        # Build an in-memory tar containing one file.
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            info = tarfile.TarInfo(name=basename)
            info.size = len(content)
            info.mtime = int(time.time())
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(content))
        archive = buf.getvalue()

        container = self.client.containers.get(container_id)
        container.put_archive(parent, archive)
