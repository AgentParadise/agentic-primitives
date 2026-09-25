"""Conversation previews: harness rows in, role/text out, bounded and lossless about gaps."""

import json

from agentic_isolation.harnesses import ConversationHarnessPlugin, get_harness
from agentic_isolation.harnesses.claude.conversation import ClaudeConversationReader
from agentic_isolation.harnesses.codex.conversation import CodexConversationReader
from agentic_isolation.harnesses.conversation import PREVIEW_CHAR_LIMIT


def _bytes(*rows: object) -> bytes:
    return ("\n".join(json.dumps(row) for row in rows) + "\n").encode()


def test_codex_skips_header_and_developer_messages() -> None:
    content = _bytes(
        {"type": "session_meta", "payload": {"id": "s", "instructions": "x" * 50_000}},
        {
            "type": "response_item",
            "payload": {"type": "message", "role": "developer", "content": "internal"},
        },
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Spawn a child"}],
            },
        },
        {"type": "response_item", "payload": {"type": "function_call", "name": "shell"}},
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "OK"}],
            },
        },
    )
    preview = CodexConversationReader().conversation(content)
    assert [(m.role, m.text, m.line) for m in preview.messages] == [
        ("user", "Spawn a child", 3),
        ("assistant", "OK", 5),
    ]
    assert not preview.truncated


def test_claude_reads_string_and_block_content_and_reports_bad_rows() -> None:
    content = b"bad\n" + _bytes(
        {"sessionId": "s", "message": {"role": "user", "content": "hi"}},
        {
            "sessionId": "s",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "hello"},
                    {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
                ],
            },
        },
        {"sessionId": "s", "type": "system"},
    )
    preview = ClaudeConversationReader().conversation(content)
    assert [(m.role, m.text) for m in preview.messages] == [("user", "hi"), ("assistant", "hello")]
    assert preview.issues == ("invalid_record:1",)


def test_preview_is_bounded_and_says_so() -> None:
    content = _bytes(*({"message": {"role": "user", "content": "y" * 10_000}} for _ in range(5)))
    preview = ClaudeConversationReader().conversation(content)
    assert sum(len(m.text) for m in preview.messages) == PREVIEW_CHAR_LIMIT
    assert preview.truncated


def test_envelope_is_unwrapped_and_harness_checked() -> None:
    raw = _bytes({"message": {"role": "assistant", "content": "enveloped"}}).decode()
    envelope = json.dumps(
        {"agent": "ClaudeCode", "source_format": "claude-code-jsonl", "session_id": "s", "raw": raw}
    ).encode()
    assert (
        ClaudeConversationReader().conversation_envelope(envelope).messages[0].text == "enveloped"
    )
    assert CodexConversationReader().conversation_envelope(envelope).issues == (
        "envelope_harness_mismatch",
    )


def test_bundled_harnesses_expose_conversation_capability() -> None:
    for name in ("claude", "codex"):
        plugin = get_harness(name)
        assert isinstance(plugin, ConversationHarnessPlugin)
        assert plugin.conversation_reader().conversation(b"").messages == ()
