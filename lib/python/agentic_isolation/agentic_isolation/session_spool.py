"""Host-issued, bounded reads from the exporter's durable local spool."""

from __future__ import annotations

import base64
import hashlib
import shlex
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from agentic_isolation.harnesses import ExecFn, exec_argv


class SpoolReadError(Exception):
    """No capture may be acknowledged after a failed or inconsistent read."""


class _EnvelopeIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", strict=True)
    agent: str
    session_id: str


class SpoolEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    sequence: int = Field(gt=0)
    archive_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    byte_count: int = Field(ge=0)
    agent: str = Field(min_length=1, max_length=128)
    native_session_id: str = Field(min_length=1, max_length=2048)


class SpoolPage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    schema_version: Literal[1]
    watermark: int = Field(ge=0)
    entries: tuple[SpoolEntry, ...] = Field(max_length=500)
    next_after: int | None = Field(default=None, ge=1)


async def capture_retained_partition(execute: ExecFn, root: str, partition: str) -> None:
    """Reuse persisted capture origin so recovery does not invent new revisions."""
    if (
        not root.startswith("/")
        or partition.startswith("/")
        or ".." in PurePosixPath(partition).parts
    ):
        raise ValueError("Invalid retained capture partition")
    metadata = f"{root}/.agentic-session-store/{partition}"
    origin = await exec_argv(execute, ["cat", f"{metadata}/.origin-host"], timeout=10)
    host = origin.stdout.strip()
    if origin.exit_code != 0 or not host or len(host) > 1024 or "\n" in host or "\x00" in host:
        raise SpoolReadError("Original capture origin is unavailable")
    deployment = await exec_argv(execute, ["cat", f"{metadata}/.origin-deployment"], timeout=10)
    if deployment.exit_code != 0 or len(deployment.stdout) > 4096:
        raise SpoolReadError("Original capture deployment is unavailable")
    capture_env = await exec_argv(
        execute,
        [
            "sh",
            "-c",
            'if [ -e "$1" ]; then cat "$1"; fi',
            "capture-metadata",
            f"{metadata}/.capture-env",
        ],
        timeout=10,
    )
    if capture_env.exit_code != 0 or len(capture_env.stdout) > 65536:
        raise SpoolReadError("Original capture tags are unavailable")
    tags = ""
    if capture_env.exit_code == 0:
        for line in capture_env.stdout.splitlines():
            if line.startswith("SESSION_STORE_TAGS_B64="):
                tags = base64.b64decode(line.partition("=")[2], validate=True).decode()
    result = await exec_argv(
        execute,
        ["/usr/local/bin/apss-session-exporter", "--spool-only"],
        timeout=60,
        env={
            "HOME": "/tmp",
            "CLAUDE_PROJECTS_ROOT": f"{root}/{partition}/claude",
            "CODEX_SESSIONS_ROOT": f"{root}/{partition}/codex",
            "EXPORTER_SPOOL_DIR": f"{metadata}/envelopes",
            "SESSION_STORE_ORIGIN_HOST": host,
            "SESSION_STORE_ORIGIN_ENV": "container",
            "SESSION_STORE_ORIGIN_DEPLOYMENT": deployment.stdout,
            "SESSION_STORE_TAGS": tags,
            "MAX_ENVELOPE_BYTES": str(16 * 1024 * 1024),
        },
    )
    if result.exit_code not in (0, 3) or result.timed_out:
        raise SpoolReadError("Retained transcript capture failed")


class WorkspaceSpoolReader:
    def __init__(self, execute: ExecFn, spool_dir: str, *, max_bytes: int = 16 * 1024 * 1024):
        path = PurePosixPath(spool_dir)
        if not path.is_absolute() or ".." in path.parts or max_bytes < 1:
            raise ValueError("Invalid spool location or byte limit")
        self._execute = execute
        self._env = {"EXPORTER_SPOOL_DIR": spool_dir, "MAX_ENVELOPE_BYTES": str(max_bytes)}
        self._max_bytes = max_bytes
        self._binary = "/usr/local/bin/apss-session-exporter"

    async def page(self, after: int, watermark: int | None = None) -> SpoolPage:
        if after < 0 or (watermark is not None and watermark < after):
            raise ValueError("Invalid spool cursor")
        cursor = str(after) if watermark is None else f"{after}:{watermark}"
        result = await exec_argv(
            self._execute, [self._binary, "--spool-list", cursor], timeout=30, env=self._env
        )
        if result.exit_code != 0 or result.timed_out or len(result.stdout) > 2 * 1024 * 1024:
            raise SpoolReadError("Spool index unavailable or oversized")
        page = SpoolPage.model_validate_json(result.stdout)
        if page.watermark < after or (watermark is not None and page.watermark != watermark):
            raise SpoolReadError("Spool watermark changed within traversal")
        sequences = [entry.sequence for entry in page.entries]
        if sequences != sorted(set(sequences)) or any(
            seq <= after or seq > page.watermark for seq in sequences
        ):
            raise SpoolReadError("Spool page is unordered or outside requested bounds")
        if page.next_after is not None and (not sequences or page.next_after != sequences[-1]):
            raise SpoolReadError("Spool continuation does not follow returned entries")
        if page.next_after == page.watermark:
            raise SpoolReadError("Spool continuation cannot advance")
        if page.next_after is None and (sequences[-1] if sequences else after) != page.watermark:
            raise SpoolReadError("Spool traversal ended before its watermark")
        return page

    async def read(self, entry: SpoolEntry) -> bytes:
        if entry.byte_count > self._max_bytes:
            raise SpoolReadError("Spool body exceeds capture limit")
        command = shlex.join([self._binary, "--spool-read", str(entry.sequence)]) + " | base64"
        result = await exec_argv(
            self._execute, ["bash", "-o", "pipefail", "-c", command], timeout=30, env=self._env
        )
        if (
            result.exit_code != 0
            or result.timed_out
            or len(result.stdout) > (self._max_bytes * 2 + 1024)
        ):
            raise SpoolReadError("Spool body unavailable or oversized")
        try:
            body = base64.b64decode("".join(result.stdout.split()), validate=True)
        except ValueError as error:
            raise SpoolReadError("Spool body transfer encoding is invalid") from error
        if (
            len(body) != entry.byte_count
            or hashlib.sha256(body).hexdigest() != entry.archive_sha256
        ):
            raise SpoolReadError("Spool body does not match indexed revision")
        identity = _EnvelopeIdentity.model_validate_json(body)
        if identity.agent != entry.agent or identity.session_id != entry.native_session_id:
            raise SpoolReadError("Spool index identity does not match its envelope")
        return body
