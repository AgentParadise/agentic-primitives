"""Bounded, format-normalized conversation excerpts for human preview.

A preview is a READ convenience, never evidence: the exact archived bytes stay
the source of truth. It carries ONLY human-visible user and assistant message
text. Each harness package owns an ALLOWLIST of the row shapes that are such
text; everything else (reasoning, tool calls and results, injected context,
meta/compaction/replay rows) is excluded by not being on it.

Resource use is bounded before materialization: lines are scanned in place,
oversized lines are skipped without parsing, and reading stops as soon as the
character budget is spent.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

from pydantic import ValidationError

from .envelope_evidence import _Envelope

Role = Literal["user", "assistant"]

PREVIEW_CHAR_LIMIT = 32_768
MAX_DOCUMENT_BYTES = 16 * 1024 * 1024
MAX_LINE_BYTES = 1024 * 1024
MAX_ISSUES = 64
#: Not JSON, so every RowParser rejects it and the row is reported invalid_record.
_UNREADABLE = b"\x00"


@dataclass(frozen=True)
class ConversationMessage:
    role: Role
    text: str
    line: int


@dataclass(frozen=True)
class ConversationPreview:
    messages: tuple[ConversationMessage, ...] = ()
    truncated: bool = False
    issues: tuple[str, ...] = ()
    reader_version: str = "conversation-preview/2"


@runtime_checkable
class ConversationReader(Protocol):
    def conversation(self, content: bytes) -> ConversationPreview: ...

    def conversation_envelope(self, content: bytes) -> ConversationPreview: ...


class RowParser(Protocol):
    """Per-document parser. Returns the allowlisted messages on one line.

    Raises ValueError (incl. pydantic ValidationError) for an unreadable line.
    """

    def messages(self, line: bytes) -> Iterable[tuple[Role, str]]: ...


@dataclass
class _Builder:
    version: str
    messages: list[ConversationMessage] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    used: int = 0
    truncated: bool = False

    def issue(self, value: str) -> None:
        if len(self.issues) < MAX_ISSUES:
            self.issues.append(value)
        elif len(self.issues) == MAX_ISSUES:
            self.issues.append("issue_limit")

    def add(self, role: Role, text: str, line: int) -> None:
        remaining = PREVIEW_CHAR_LIMIT - self.used
        if len(text) > remaining:
            text = text[:remaining]
            self.truncated = True
        if text:
            self.messages.append(ConversationMessage(role, text, line))
            self.used += len(text)
        if self.used >= PREVIEW_CHAR_LIMIT:
            self.truncated = True

    def result(self) -> ConversationPreview:
        return ConversationPreview(
            tuple(self.messages), self.truncated, tuple(self.issues), self.version
        )


def native_lines(content: bytes) -> Iterator[tuple[int, bytes | None]]:
    """Yield (one-based line, bytes) without splitting the whole document.

    Lines over MAX_LINE_BYTES yield None and are never copied or parsed.
    """
    view = memoryview(content)
    start, number, size = 0, 0, len(content)
    while start < size:
        end = content.find(b"\n", start)
        end = size if end == -1 else end
        number += 1
        if end - start > MAX_LINE_BYTES:
            yield number, None
        else:
            yield number, bytes(view[start:end])
        start = end + 1


def collect(
    lines: Iterable[tuple[int, bytes | None]], parser: RowParser, version: str
) -> ConversationPreview:
    builder = _Builder(version)
    for number, line in lines:
        if builder.truncated:
            break
        if line is None:
            builder.issue(f"line_byte_limit:{number}")
            continue
        if not line.strip():
            continue
        try:
            found = tuple(parser.messages(line))
        except (ValidationError, ValueError, RecursionError):
            builder.issue(f"invalid_record:{number}")
            continue
        for role, text in found:
            builder.add(role, text, number)
            if builder.truncated:
                break
    return builder.result()


def read_native(content: bytes, parser: RowParser, version: str) -> ConversationPreview:
    if len(content) > MAX_DOCUMENT_BYTES:
        return ConversationPreview(issues=("document_byte_limit",), reader_version=version)
    return collect(native_lines(content), parser, version)


def _envelope_rows(raw: Iterable[object]) -> Iterator[tuple[int, bytes | None]]:
    for number, row in enumerate(raw, 1):
        try:
            encoded = json.dumps(row, ensure_ascii=False, allow_nan=False).encode()
        except (ValueError, UnicodeError, RecursionError):
            yield number, _UNREADABLE
            continue
        yield number, (None if len(encoded) > MAX_LINE_BYTES else encoded)


def read_envelope(
    content: bytes, parser: RowParser, version: str, *, agent: str, source_format: str
) -> ConversationPreview:
    """Unwrap an APS-V1-0004 capture envelope, then read its native rows lazily."""
    if len(content) > MAX_DOCUMENT_BYTES:
        return ConversationPreview(issues=("document_byte_limit",), reader_version=version)
    try:
        envelope = _Envelope.model_validate_json(content)
    except (ValidationError, ValueError, RecursionError):
        return ConversationPreview(issues=("invalid_capture_envelope",), reader_version=version)
    if envelope.agent != agent or envelope.source_format != source_format:
        return ConversationPreview(issues=("envelope_harness_mismatch",), reader_version=version)
    raw = envelope.raw
    if isinstance(raw, list):
        return collect(_envelope_rows(raw), parser, version)
    try:
        native = raw.encode()
    except UnicodeError:
        return ConversationPreview(issues=("invalid_capture_envelope",), reader_version=version)
    return collect(native_lines(native), parser, version)
