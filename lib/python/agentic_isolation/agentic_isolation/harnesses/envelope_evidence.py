"""Normalize envelope payloads for evidence extraction, never for archival."""

import json
from dataclasses import replace
from typing import Protocol, runtime_checkable

from pydantic import JsonValue, ValidationError

from .evidence import NativeEvidence, NativeEvidenceReader, WireModel


@runtime_checkable
class EnvelopeEvidenceReader(Protocol):
    def extract_envelope(self, content: bytes) -> NativeEvidence: ...


class _Envelope(WireModel):
    agent: str
    source_format: str
    session_id: str
    raw: str | list[JsonValue]


def extract_envelope(
    content: bytes, reader: NativeEvidenceReader, *, agent: str, source_format: str
) -> NativeEvidence:
    if len(content) > 16 * 1024 * 1024:
        return NativeEvidence(None, issues=("document_byte_limit",))
    try:
        envelope = _Envelope.model_validate_json(content)
        if envelope.agent != agent or envelope.source_format != source_format:
            return NativeEvidence(None, issues=("envelope_harness_mismatch",))
        # Array normalization supplies logical row locations only. The caller
        # archives the original envelope bytes, including its raw representation.
        raw = envelope.raw
        native = (
            raw.encode()
            if isinstance(raw, str)
            else b"\n".join(
                json.dumps(row, ensure_ascii=False, allow_nan=False).encode() for row in raw
            )
        )
        result = reader.extract(native)
    except (ValidationError, ValueError, UnicodeError, RecursionError):
        return NativeEvidence(None, issues=("invalid_capture_envelope",))
    if result.native_id is not None and result.native_id != envelope.session_id:
        return NativeEvidence(None, issues=("envelope_native_identity_conflict",))
    return replace(result, extractor_version=f"scs-envelope/1:{result.extractor_version}")
