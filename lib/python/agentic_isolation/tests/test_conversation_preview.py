"""Conversation previews carry ONLY human-visible user/assistant text, within bounds.

Claude fixtures mirror row shapes counted in real Claude Code 2.1.x transcripts
(attachment/system/summary rows, isMeta and isCompactSummary user rows,
tool_result user rows, thinking/tool_use assistant blocks, origin.kind). The
Codex fixture is a REAL codex-cli 0.156.1 rollout generated offline by
tests/fixtures/generate_codex_rollout.py.
"""

from __future__ import annotations

import json
import tracemalloc
from pathlib import Path
from typing import Literal

import pytest

from agentic_isolation.harnesses import ConversationHarnessPlugin, get_harness
from agentic_isolation.harnesses.claude.conversation import ClaudeConversationReader
from agentic_isolation.harnesses.claude.conversation import _Parser as _ClaudeParser
from agentic_isolation.harnesses.codex.conversation import CodexConversationReader
from agentic_isolation.harnesses.conversation import (
    MAX_LINE_BYTES,
    PREVIEW_CHAR_LIMIT,
    ConversationPreview,
    _envelope_rows,
    collect,
)

FIXTURES = Path(__file__).parent / "fixtures"
SECRETS = ("SECRET", "TOOL_OUTPUT", "environment_context", "skills_instructions", "HIDDEN")


def _bytes(*rows: object) -> bytes:
    return ("\n".join(json.dumps(row) for row in rows) + "\n").encode()


def _pairs(preview: ConversationPreview) -> list[tuple[str, str]]:
    return [(m.role, m.text) for m in preview.messages]


def _leaks(preview: ConversationPreview) -> list[str]:
    text = "\n".join(m.text for m in preview.messages)
    return [secret for secret in SECRETS if secret in text]


def _user(content: object, **extra: object) -> dict[str, object]:
    return {
        "type": "user",
        "sessionId": "s",
        "isSidechain": False,
        "userType": "external",
        "message": {"role": "user", "content": content},
        **extra,
    }


def _assistant(*blocks: object, **extra: object) -> dict[str, object]:
    return {
        "type": "assistant",
        "sessionId": "s",
        "isSidechain": False,
        "message": {"role": "assistant", "content": list(blocks)},
        **extra,
    }


CLAUDE_ADVERSARIAL = _bytes(
    {"type": "attachment", "attachment": {"content": "HIDDEN attachment"}},
    {"type": "system", "content": "HIDDEN system", "level": "info"},
    {"type": "summary", "summary": "HIDDEN summary", "leafUuid": "x"},
    _user("HIDDEN caveat", isMeta=True),
    _user([{"type": "text", "text": "HIDDEN meta block"}], isMeta=True),
    _user("HIDDEN compaction", isCompactSummary=True, isVisibleInTranscriptOnly=True),
    _user("HIDDEN task", origin={"kind": "task-notification"}, promptSource="system"),
    _user("HIDDEN continue", origin={"kind": "auto-continuation"}),
    _user("<local-command-stdout>HIDDEN out</local-command-stdout>"),
    _user("<bash-stdout>HIDDEN</bash-stdout>"),
    _user("real question", origin={"kind": "human"}, promptSource="typed"),
    _assistant({"type": "thinking", "thinking": "SECRET thought", "signature": "sig"}),
    _assistant({"type": "redacted_thinking", "data": "SECRET"}),
    _assistant({"type": "tool_use", "id": "t", "name": "Bash", "input": {"command": "cat .env"}}),
    _user(
        [
            {"type": "tool_result", "tool_use_id": "t", "content": "TOOL_OUTPUT token=abc"},
            {"type": "text", "text": "HIDDEN riding along a tool result"},
        ],
        toolUseResult={"stdout": "TOOL_OUTPUT"},
    ),
    _assistant({"type": "text", "text": "SECRET error"}, isApiErrorMessage=True),
    # Any non-"text" block that happens to carry a text field must still be excluded.
    _assistant(
        {"type": "thinking", "thinking": "SECRET", "text": "SECRET via text field"},
        {"type": "text", "text": "real answer"},
    ),
    _user("HIDDEN sidechain", isSidechain=True),
    _assistant({"type": "text", "text": "HIDDEN sidechain answer"}, isSidechain=True),
    {"type": "user", "message": {"role": "assistant", "content": "HIDDEN role mismatch"}},
    _user([{"type": "image", "source": {}}, {"type": "text", "text": "look at this"}]),
)


def test_claude_allowlist_keeps_only_human_visible_text() -> None:
    preview = ClaudeConversationReader().conversation(CLAUDE_ADVERSARIAL)
    assert _pairs(preview) == [
        ("user", "real question"),
        ("assistant", "real answer"),
        ("user", "look at this"),
    ]
    assert _leaks(preview) == []
    assert preview.issues == ()


def test_claude_child_transcript_previews_its_sidechain_rows() -> None:
    content = _bytes(
        _user("delegated task", isSidechain=True, agentId="b"),
        _assistant({"type": "text", "text": "child answer"}, isSidechain=True, agentId="b"),
    )
    assert _pairs(ClaudeConversationReader().conversation(content)) == [
        ("user", "delegated task"),
        ("assistant", "child answer"),
    ]


def test_real_codex_0_156_1_rollout_shows_only_the_human_turns() -> None:
    content = (FIXTURES / "codex_rollout_0.156.1.jsonl").read_bytes()
    assert b"SECRET_REASONING" in content and b"TOOL_OUTPUT_SECRET" in content  # hazard present
    assert b"environment_context" in content  # injected user response_item present
    preview = CodexConversationReader().conversation(content)
    assert _pairs(preview) == [
        ("user", "HUMAN_PROMPT please run it"),
        ("assistant", "Running a command."),
        ("assistant", "FINAL_ANSWER"),
    ]
    assert _leaks(preview) == []
    assert preview.issues == ()


def test_codex_legacy_events_and_family_lock_never_duplicate() -> None:
    legacy = _bytes(
        {"type": "event_msg", "payload": {"type": "user_message", "message": "hi"}},
        {"type": "event_msg", "payload": {"type": "agent_reasoning", "text": "SECRET"}},
        {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "HIDDEN duplicate"}],
            },
        },
        {"type": "event_msg", "payload": {"type": "agent_message", "message": "hello"}},
    )
    assert _pairs(CodexConversationReader().conversation(legacy)) == [
        ("user", "hi"),
        ("assistant", "hello"),
    ]
    item = {
        "type": "event_msg",
        "payload": {
            "type": "item_completed",
            "item": {
                "type": "AgentMessage",
                "id": "m",
                "content": [{"type": "Text", "text": "once"}],
            },
        },
    }
    mixed = _bytes(
        item,
        item,
        {"type": "event_msg", "payload": {"type": "agent_message", "message": "HIDDEN twice"}},
        {
            "type": "event_msg",
            "payload": {
                "type": "item_completed",
                "item": {"type": "Reasoning", "id": "r", "summary_text": ["SECRET"]},
            },
        },
        {
            "type": "event_msg",
            "payload": {
                "type": "item_completed",
                "item": {
                    "type": "UserMessage",
                    "id": "u",
                    "content": [
                        {"type": "image", "text": "HIDDEN"},
                        {"type": "text", "text": "typed"},
                    ],
                },
            },
        },
    )
    preview = CodexConversationReader().conversation(mixed)
    assert _pairs(preview) == [("assistant", "once"), ("user", "typed")]
    assert _leaks(preview) == []


def test_budget_stops_reading_and_bounds_memory() -> None:
    row = json.dumps(_user("y" * 1000)).encode()
    content = b"\n".join([row] * 12_000)  # ~13 MB, far past the 32K budget
    tracemalloc.start()
    preview = ClaudeConversationReader().conversation(content)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert sum(len(m.text) for m in preview.messages) == PREVIEW_CHAR_LIMIT
    assert preview.truncated
    assert len(preview.messages) == 33  # stopped at the budget, not after 15k rows
    assert peak < 2 * 1024 * 1024, peak


def test_oversized_lines_are_skipped_without_parsing() -> None:
    huge = json.dumps(_user("z" * (MAX_LINE_BYTES + 10))).encode()
    content = huge + b"\n" + _bytes(_user("after"))
    tracemalloc.start()
    preview = ClaudeConversationReader().conversation(content)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert _pairs(preview) == [("user", "after")]
    assert preview.issues == ("line_byte_limit:1",)
    assert peak < MAX_LINE_BYTES // 2, peak


def test_issues_are_bounded() -> None:
    preview = ClaudeConversationReader().conversation(b"bad\n" * 500)
    assert len(preview.issues) == 65 and preview.issues[-1] == "issue_limit"


def _envelope(raw: object, agent: str = "ClaudeCode") -> bytes:
    return json.dumps(
        {"agent": agent, "source_format": "claude-code-jsonl", "session_id": "s", "raw": raw}
    ).encode()


@pytest.mark.parametrize("as_array", [False, True])
def test_envelope_applies_the_same_allowlist(as_array: bool) -> None:
    rows = [_user("HIDDEN", isMeta=True), _user("visible")]
    raw: object = rows if as_array else _bytes(*rows).decode()
    preview = ClaudeConversationReader().conversation_envelope(_envelope(raw))
    assert _pairs(preview) == [("user", "visible")]


def test_envelope_failures_are_issues_not_exceptions() -> None:
    reader = ClaudeConversationReader()
    lone = b'{"agent":"ClaudeCode","source_format":"claude-code-jsonl","session_id":"s",'
    assert reader.conversation_envelope(lone + b'"raw":"\\ud800"}').issues == (
        "invalid_capture_envelope",
    )
    array = lone + b'"raw":[{"t":"\\ud800"},' + _bytes(_user("ok")).strip() + b"]}"
    assert reader.conversation_envelope(array).issues == ("invalid_capture_envelope",)
    # Rows that cannot be re-encoded (reachable only from in-memory input) are
    # reported, never raised, and do not stop later rows.
    rows = list(_envelope_rows([{"t": "\ud800"}, {"n": float("nan")}, _user("ok")]))
    preview = collect(rows, _ClaudeParser(), "v")
    assert _pairs(preview) == [("user", "ok")]
    assert preview.issues == ("invalid_record:1", "invalid_record:2")
    assert reader.conversation_envelope(b"not json").issues == ("invalid_capture_envelope",)
    assert CodexConversationReader().conversation_envelope(_envelope("")).issues == (
        "envelope_harness_mismatch",
    )


def test_bundled_harnesses_expose_conversation_capability() -> None:
    for name in ("claude", "codex"):
        plugin = get_harness(name)
        assert isinstance(plugin, ConversationHarnessPlugin)
        assert plugin.conversation_reader().conversation(b"").messages == ()


def test_reading_stops_as_soon_as_the_budget_is_spent() -> None:
    class Counting:
        calls = 0

        def messages(self, line: bytes) -> tuple[tuple[Literal["user"], str], ...]:
            self.calls += 1
            return (("user", "y" * 1000),)

    parser = Counting()
    lines = ((number, b"{}") for number in range(1, 100_001))
    preview = collect(lines, parser, "v")
    assert preview.truncated
    assert parser.calls == 33  # 32 full messages + 1 partial, then no further parsing
