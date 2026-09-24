"""Envelope identity is checked against native evidence, never substituted."""

import json

from agentic_isolation.harnesses.claude.evidence import ClaudeNativeEvidenceReader
from agentic_isolation.harnesses.codex.evidence import CodexNativeEvidenceReader


def test_claude_envelope_retains_logical_proof_locations() -> None:
    raw = '{"sessionId":"root"}\r\n{"sessionId":"root"}\r\n'
    envelope = json.dumps(
        {
            "agent": "ClaudeCode",
            "source_format": "claude-code-jsonl",
            "session_id": "root",
            "raw": raw,
        }
    ).encode()
    facts = ClaudeNativeEvidenceReader().extract_envelope(envelope)
    assert facts.native_id == "root"
    assert facts.identity_lines == (1,)
    assert facts.extractor_version.startswith("scs-envelope/1:")


def test_codex_array_envelope_preserves_child_parent_relationship() -> None:
    envelope = json.dumps(
        {
            "agent": "Codex",
            "source_format": "codex-rollout-jsonl",
            "session_id": "child",
            "raw": [
                {
                    "type": "session_meta",
                    "payload": {
                        "id": "child",
                        "source": {"subagent": {"thread_spawn": {"parent_thread_id": "parent"}}},
                    },
                }
            ],
        }
    ).encode()
    facts = CodexNativeEvidenceReader().extract_envelope(envelope)
    assert facts.native_id == "child"
    assert facts.links[0].parent_id == "parent"
    assert facts.links[0].lines == (1,)


def test_envelope_cannot_override_conflicting_native_identity() -> None:
    envelope = json.dumps(
        {
            "agent": "ClaudeCode",
            "source_format": "claude-code-jsonl",
            "session_id": "claimed",
            "raw": '{"sessionId":"actual"}',
        }
    ).encode()
    facts = ClaudeNativeEvidenceReader().extract_envelope(envelope)
    assert facts.native_id is None
    assert facts.issues == ("envelope_native_identity_conflict",)
    wrong_harness = CodexNativeEvidenceReader().extract_envelope(envelope)
    assert wrong_harness.native_id is None
    assert wrong_harness.issues == ("envelope_harness_mismatch",)


def test_invalid_and_oversize_envelopes_produce_explicit_gaps() -> None:
    reader = ClaudeNativeEvidenceReader()
    assert reader.extract_envelope(b"{").issues == ("invalid_capture_envelope",)
    assert reader.extract_envelope(b" " * (16 * 1024 * 1024 + 1)).issues == ("document_byte_limit",)
