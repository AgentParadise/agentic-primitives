"""A truncated index or substituted body must never advance capture."""

import base64
import hashlib
import json
from unittest.mock import AsyncMock

import pytest

from agentic_isolation.providers.base import ExecuteResult
from agentic_isolation.session_spool import (
    SpoolEntry,
    SpoolReadError,
    WorkspaceSpoolReader,
    capture_retained_partition,
)


def entry(
    sequence: int, body: bytes = b'{"agent":"Codex","session_id":"native"}\r\n'
) -> SpoolEntry:
    return SpoolEntry(
        sequence=sequence,
        archive_sha256=hashlib.sha256(body).hexdigest(),
        byte_count=len(body),
        agent="Codex",
        native_session_id="native",
    )


def result(stdout: str, exit_code: int = 0) -> ExecuteResult:
    return ExecuteResult(exit_code=exit_code, stdout=stdout, stderr="", duration_ms=0)


@pytest.mark.asyncio
async def test_recovery_preserves_origin_and_parses_tags_as_data() -> None:
    tags = "workflow:run,$(never-execute)"
    encoded = base64.b64encode(tags.encode()).decode()
    execute = AsyncMock(
        side_effect=[
            result("original-host\n"),
            result("deployment"),
            result(f"SESSION_STORE_TAGS_B64={encoded}\n"),
            result("{}", exit_code=3),
        ]
    )
    await capture_retained_partition(execute, "/spool", "partition")
    capture = execute.await_args
    assert "--spool-only" in capture.args[0]
    assert capture.kwargs["env"]["SESSION_STORE_ORIGIN_HOST"] == "original-host"
    assert capture.kwargs["env"]["SESSION_STORE_ORIGIN_DEPLOYMENT"] == "deployment"
    assert capture.kwargs["env"]["SESSION_STORE_TAGS"] == tags
    assert tags not in capture.args[0]


@pytest.mark.asyncio
async def test_reader_preserves_exact_bytes_and_explicit_host_location() -> None:
    execute = AsyncMock(
        return_value=result(
            base64.b64encode(b'{"agent":"Codex","session_id":"native"}\r\n').decode()
        )
    )
    reader = WorkspaceSpoolReader(execute, "/spool/run 'quoted'/envelopes")
    assert await reader.read(entry(7)) == b'{"agent":"Codex","session_id":"native"}\r\n'
    call = execute.await_args
    assert "pipefail" in call.args[0]
    assert call.kwargs["env"]["EXPORTER_SPOOL_DIR"] == "/spool/run 'quoted'/envelopes"
    with pytest.raises(SpoolReadError, match="identity"):
        await reader.read(entry(7).model_copy(update={"native_session_id": "substituted"}))
    execute.return_value = result(base64.b64encode(b"wrong\r\n").decode())
    with pytest.raises(SpoolReadError, match="revision"):
        await reader.read(entry(7))
    execute.return_value = result("", exit_code=1)
    with pytest.raises(SpoolReadError, match="unavailable"):
        await reader.read(entry(7))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sequences,watermark,next_after",
    [
        ([3, 2], 3, None),
        ([2, 2], 3, 2),
        ([2], 3, None),
        ([], 3, None),
        ([4], 3, None),
        ([2], 3, 1),
        ([3], 3, 3),
    ],
)
async def test_inconsistent_pages_never_advance(sequences, watermark, next_after) -> None:
    payload = {
        "schema_version": 1,
        "watermark": watermark,
        "entries": [entry(seq).model_dump() for seq in sequences],
        "next_after": next_after,
    }
    reader = WorkspaceSpoolReader(
        AsyncMock(return_value=result(json.dumps(payload))), "/spool/envelopes"
    )
    with pytest.raises(SpoolReadError):
        await reader.page(0, 3)


@pytest.mark.asyncio
async def test_fixed_watermark_allows_sequence_gaps_and_rejects_concurrent_head_change() -> None:
    payload = {
        "schema_version": 1,
        "watermark": 7,
        "entries": [entry(3).model_dump(), entry(7).model_dump()],
        "next_after": None,
    }
    execute = AsyncMock(return_value=result(json.dumps(payload)))
    reader = WorkspaceSpoolReader(execute, "/spool/envelopes")
    page = await reader.page(1, 7)
    assert [item.sequence for item in page.entries] == [3, 7]
    with pytest.raises(SpoolReadError, match="watermark"):
        await reader.page(1, 6)
