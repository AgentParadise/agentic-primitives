"""Bounded, format-normalized conversation excerpts for human preview.

A preview is a READ convenience, never evidence: the exact archived bytes stay
the source of truth. Each harness package owns the row shapes it reads; callers
only see user/assistant text in transcript order. Other roles (system,
developer, tool output) are deliberately omitted.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

from pydantic import ValidationError

from .envelope_evidence import _Envelope

PREVIEW_CHAR_LIMIT = 32_768


@dataclass(frozen=True)
class ConversationMessage:
    role: Literal["user", "assistant"]
    text: str
    line: int


@dataclass(frozen=True)
class ConversationPreview:
    messages: tuple[ConversationMessage, ...] = ()
    truncated: bool = False
    issues: tuple[str, ...] = ()
    reader_version: str = "conversation-preview/1"


@runtime_checkable
class ConversationReader(Protocol):
    def conversation(self, content: bytes) -> ConversationPreview: ...

    def conversation_envelope(self, content: bytes) -> ConversationPreview: ...


def bounded(
    messages: list[ConversationMessage], issues: tuple[str, ...], version: str
) -> ConversationPreview:
    """Keep whole messages in order until the character budget is spent."""
    kept: list[ConversationMessage] = []
    used = 0
    for message in messages:
        remaining = PREVIEW_CHAR_LIMIT - used
        if remaining <= 0:
            return ConversationPreview(tuple(kept), True, issues, version)
        if len(message.text) > remaining:
            kept.append(ConversationMessage(message.role, message.text[:remaining], message.line))
            return ConversationPreview(tuple(kept), True, issues, version)
        kept.append(message)
        used += len(message.text)
    return ConversationPreview(tuple(kept), False, issues, version)


def conversation_from_envelope(
    content: bytes, reader: ConversationReader, *, agent: str, source_format: str
) -> ConversationPreview:
    """Unwrap an APS-V1-0004 capture envelope, then read its native rows."""
    if len(content) > 16 * 1024 * 1024:
        return ConversationPreview(issues=("document_byte_limit",))
    try:
        envelope = _Envelope.model_validate_json(content)
    except (ValidationError, ValueError, RecursionError):
        return ConversationPreview(issues=("invalid_capture_envelope",))
    if envelope.agent != agent or envelope.source_format != source_format:
        return ConversationPreview(issues=("envelope_harness_mismatch",))
    raw = envelope.raw
    native = (
        raw.encode()
        if isinstance(raw, str)
        else b"\n".join(
            json.dumps(row, ensure_ascii=False, allow_nan=False).encode() for row in raw
        )
    )
    return reader.conversation(native)
