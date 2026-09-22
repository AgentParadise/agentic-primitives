"""Bounded, format-normalized native facts. Consumers decide run membership.

These records are observations, not host attestations or capture-completeness
claims. Exact bytes remain the input; line locations are one-based JSONL lines.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, TypeVar

from pydantic import BaseModel, ConfigDict, ValidationError


@dataclass(frozen=True)
class NativeLink:
    parent_id: str
    child_id: str
    relation: Literal["spawn", "fork", "resume"]
    basis: Literal["parent_call_result", "child_header"]
    mechanism: str
    lines: tuple[int, ...]
    call_id: str | None = None


@dataclass(frozen=True)
class NativeEvidence:
    native_id: str | None
    identity_lines: tuple[int, ...] = ()
    root_id: str | None = None
    links: tuple[NativeLink, ...] = ()
    issues: tuple[str, ...] = ()
    extractor_version: str = "native-evidence/1"


class NativeEvidenceReader(Protocol):
    def extract(self, content: bytes) -> NativeEvidence: ...


class WireModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore", strict=True)


T = TypeVar("T", bound=WireModel)


def read_rows(
    content: bytes,
    model: type[T],
    *,
    max_bytes: int = 16 * 1024 * 1024,
    max_lines: int = 100_000,
    max_line_bytes: int = 1024 * 1024,
) -> tuple[tuple[tuple[int, T], ...], tuple[str, ...]]:
    if len(content) > max_bytes:
        return (), ("document_byte_limit",)
    lines = content.splitlines()
    if len(lines) > max_lines:
        return (), ("document_line_limit",)
    rows: list[tuple[int, T]] = []
    issues: list[str] = []
    for index, line in enumerate(lines, 1):
        if not line.strip():
            continue
        if len(line) > max_line_bytes:
            issues.append(f"line_byte_limit:{index}")
            continue
        try:
            rows.append((index, model.model_validate_json(line)))
        except (ValidationError, ValueError, RecursionError):
            issues.append(f"invalid_record:{index}")
    return tuple(rows), tuple(issues)
