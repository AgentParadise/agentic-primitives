"""Native facts stay separate from host attribution and completeness."""

import json

from agentic_isolation.harnesses import EvidenceHarnessPlugin, get_harness
from agentic_isolation.harnesses.claude.evidence import ClaudeNativeEvidenceReader
from agentic_isolation.harnesses.codex.evidence import CodexNativeEvidenceReader


def _bytes(*rows: object) -> bytes:
    return ("\n".join(json.dumps(row) for row in rows) + "\n").encode()


def _spawn(owner: str | None, target: str) -> bytes:
    identity = {"sessionId": "root"}
    if owner:
        identity.update({"agentId": owner, "isSidechain": True})
    return _bytes(
        {**identity, "message": {"content": [{"type": "tool_use", "name": "Agent", "id": "call"}]}},
        {
            **identity,
            "message": {"content": [{"type": "tool_result", "tool_use_id": "call"}]},
            "toolUseResult": {"agentId": target},
        },
    )


def test_claude_depth_three_keeps_immediate_parent_and_missing_child_reference() -> None:
    parser = ClaudeNativeEvidenceReader()
    root, child = parser.extract(_spawn(None, "b")), parser.extract(_spawn("b", "c"))
    assert root.native_id == "root"
    assert child.native_id == "agent-b"
    assert child.root_id == "root"
    assert root.links[0].child_id == "agent-b"
    assert child.links[0].parent_id == "agent-b"
    assert child.links[0].child_id == "agent-c"
    assert child.links[0].lines == (1, 2)


def test_claude_duplicate_call_result_does_not_pick_first_or_last() -> None:
    content = _spawn(None, "b")
    duplicated = content + content.splitlines()[-1] + b"\n"
    facts = ClaudeNativeEvidenceReader().extract(duplicated)
    assert facts.links == ()
    assert "unresolved_spawn:call" in facts.issues


def test_claude_conflicting_child_identity_and_root_are_not_collapsed() -> None:
    content = _bytes(
        {"sessionId": "root", "agentId": "b", "isSidechain": True},
        {"sessionId": "root", "agentId": "c", "isSidechain": True},
    )
    facts = ClaudeNativeEvidenceReader().extract(content)
    assert facts.native_id is None
    assert facts.issues == ("identity_missing_or_conflicting",)


def test_codex_canonical_header_beats_inherited_fork_history() -> None:
    facts = CodexNativeEvidenceReader().extract(
        _bytes(
            {
                "type": "session_meta",
                "payload": {
                    "id": "child",
                    "session_id": "child",
                    "forked_from_id": "fork-source",
                    "source": {
                        "subagent": {"thread_spawn": {"parent_thread_id": "parent", "depth": 2}}
                    },
                },
            },
            {"type": "session_meta", "payload": {"id": "ancestor", "forked_from_id": "other"}},
        )
    )
    assert facts.native_id == "child"
    assert {(link.parent_id, link.child_id, link.relation) for link in facts.links} == {
        ("parent", "child", "spawn"),
        ("fork-source", "child", "fork"),
    }


def test_codex_bad_canonical_header_cannot_select_ancestor() -> None:
    facts = CodexNativeEvidenceReader().extract(
        _bytes(
            {"type": "session_meta", "payload": {"id": 123}},
            {"type": "session_meta", "payload": {"id": "ancestor"}},
        )
    )
    assert facts.native_id is None
    assert "canonical_header_unreadable" in facts.issues


def test_codex_conflicting_parent_claims_are_both_preserved() -> None:
    facts = CodexNativeEvidenceReader().extract(
        _bytes(
            {
                "type": "session_meta",
                "payload": {
                    "id": "child",
                    "parent_thread_id": "parent-a",
                    "source": {"subagent": {"thread_spawn": {"parent_thread_id": "parent-b"}}},
                },
            }
        )
    )
    assert {link.parent_id for link in facts.links} == {"parent-a", "parent-b"}
    assert "parent_identity_conflict" in facts.issues


def test_limits_and_malformed_input_produce_explicit_gaps() -> None:
    parser = ClaudeNativeEvidenceReader()
    assert "document_byte_limit" in parser.extract(b"x" * (16 * 1024 * 1024 + 1)).issues
    facts = parser.extract(b"{bad\n" + _bytes({"sessionId": "opaque/ID"}))
    assert facts.native_id == "opaque/ID"
    assert facts.identity_lines == (2,)
    assert facts.issues == ("invalid_record:1",)


def test_bundled_harnesses_expose_optional_normalization_capability() -> None:
    for name in ("claude", "codex"):
        plugin = get_harness(name)
        assert isinstance(plugin, EvidenceHarnessPlugin)
        assert plugin.evidence_reader().extract(b"").native_id is None


def test_legacy_harvest_does_not_replace_child_identity_with_root() -> None:
    from agentic_isolation.harnesses.claude.transcripts import _resolve_session_id

    lines = _spawn("child", "grandchild").decode().splitlines()
    lines.insert(0, json.dumps({"sessionId": "root"}))
    assert _resolve_session_id(lines, "/root/subagents/agent-child.jsonl") == "agent-child"


def test_codex_v2_child_keeps_thread_identity_separate_from_shared_root() -> None:
    from agentic_isolation.harnesses.codex.transcripts import _resolve_session_id

    # Field semantics observed from the real 0.150.1 native-child fixture.
    row = {
        "type": "session_meta",
        "payload": {
            "id": "child-thread",
            "session_id": "root-session",
            "multi_agent_version": "v2",
            "parent_thread_id": "immediate-parent",
            "source": {
                "subagent": {
                    "thread_spawn": {
                        "parent_thread_id": "immediate-parent",
                        "depth": 2,
                        "agent_path": "/root/child/grandchild",
                    }
                }
            },
        },
    }
    facts = CodexNativeEvidenceReader().extract(_bytes(row))
    assert facts.native_id == "child-thread"
    assert facts.root_id == "root-session"
    assert facts.issues == ()
    assert [(link.parent_id, link.child_id) for link in facts.links] == [
        ("immediate-parent", "child-thread")
    ]
    assert _resolve_session_id([json.dumps(row)], "/rollout-unknown.jsonl") == "child-thread"
