"""Bounded workspace transport for durable child-hook observations.

The host supplies the retained journal location. Returned observations are not
host attestations, workflow membership decisions or session-body receipts.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from agentic_isolation.harnesses import ExecFn, exec_argv

Identity = Annotated[str, Field(min_length=1, max_length=2048)]


class JournalReadError(Exception):
    """No recovery checkpoint may advance after an invalid journal read."""


class _Wire(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    @field_validator("*", mode="after")
    @classmethod
    def bounded_identity(cls, value: object) -> object:
        if isinstance(value, str) and ("\x00" in value or len(value.encode()) > 2048):
            raise ValueError("Invalid journal identity")
        return value


class ChildCall(_Wire):
    invocation_id: Identity
    attempt_id: Identity
    harness: Literal["claude", "codex"]
    parent_native_id: Identity
    tool_call_id: Identity
    target_harness: Literal["claude", "codex"] | None = None


class ChildIntent(_Wire):
    sequence: int = Field(gt=0)
    child_invocation_id: Identity
    call: ChildCall
    child_native_id: Identity | None
    status: Literal["launched", "launch_failed", "completed", "failed", "cancelled"] | None = None
    exit_code: int | None = Field(default=None, ge=-255, le=255)

    @model_validator(mode="after")
    def valid_outcome(self):
        if self.status in {None, "launched", "launch_failed"}:
            valid = self.exit_code is None
        elif self.status == "completed":
            valid = self.exit_code == 0
        elif self.status == "failed":
            valid = self.exit_code is not None and self.exit_code > 0
        else:
            valid = self.exit_code is not None and self.exit_code < 0
        if not valid or (self.status == "launch_failed" and self.child_native_id is not None):
            raise ValueError("Invalid child launch outcome")
        return self


class ChildChange(_Wire):
    sequence: int = Field(gt=0)
    intent: ChildIntent


class ChildPage(_Wire):
    watermark: int = Field(ge=0)
    changes: tuple[ChildChange, ...] = Field(max_length=100)
    next_after: int | None = Field(ge=1)


class _Export(_Wire):
    schema_version: Literal[1, 2]
    page: ChildPage


class WorkspaceChildJournalReader:
    def __init__(self, execute: ExecFn, journal_path: str) -> None:
        path = PurePosixPath(journal_path)
        if not path.is_absolute() or ".." in path.parts or "\x00" in journal_path:
            raise ValueError("Invalid retained journal path")
        self._execute = execute
        self._path = journal_path

    async def page(self, after: int = 0, watermark: int | None = None) -> ChildPage:
        if after < 0 or (watermark is not None and watermark < after):
            raise ValueError("Invalid child journal cursor")
        command = [
            "python3",
            "-m",
            "agentic_session_store.child_export",
            self._path,
            "--after",
            str(after),
            "--limit",
            "100",
        ]
        if watermark is not None:
            command.extend(["--watermark", str(watermark)])
        result = await exec_argv(self._execute, command, timeout=30)
        if result.exit_code != 0 or result.timed_out or len(result.stdout) > 16 * 1024 * 1024:
            raise JournalReadError("Child journal unavailable or oversized")
        try:
            page = _Export.model_validate_json(result.stdout).page
        except ValidationError as error:
            raise JournalReadError("Invalid child journal page") from error
        if page.watermark < after or (watermark is not None and page.watermark != watermark):
            raise JournalReadError("Child journal watermark changed")
        sequences = [change.sequence for change in page.changes]
        if sequences != sorted(set(sequences)) or any(
            sequence <= after or sequence > page.watermark for sequence in sequences
        ):
            raise JournalReadError("Child journal changes outside requested bounds")
        last = sequences[-1] if sequences else after
        if page.next_after is not None:
            if not sequences or page.next_after != last or last >= page.watermark:
                raise JournalReadError("Child journal continuation cannot advance")
        elif last != page.watermark:
            raise JournalReadError("Child journal traversal ended before its watermark")
        return page
