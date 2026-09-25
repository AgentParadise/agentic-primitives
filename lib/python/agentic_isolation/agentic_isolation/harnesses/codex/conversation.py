"""Codex rollout rows -> user/assistant text for preview.

Only ``response_item`` rows whose payload is a ``message`` carry conversation.
Developer/system messages and the (often very large) ``session_meta``
instructions are omitted.
"""

from __future__ import annotations

from agentic_isolation.harnesses.conversation import (
    ConversationMessage,
    ConversationPreview,
    bounded,
    conversation_from_envelope,
)
from agentic_isolation.harnesses.evidence import WireModel, read_rows

VERSION = "codex-conversation-preview/1"


class _Part(WireModel):
    type: str = ""
    text: str | None = None


class _Payload(WireModel):
    type: str = ""
    role: str | None = None
    content: list[_Part] | str | None = None


class _Row(WireModel):
    type: str = ""
    payload: _Payload | None = None


def _text(payload: _Payload) -> str:
    if isinstance(payload.content, str):
        return payload.content
    if not payload.content:
        return ""
    return "\n".join(part.text for part in payload.content if part.text)


class CodexConversationReader:
    def conversation_envelope(self, content: bytes) -> ConversationPreview:
        return conversation_from_envelope(
            content, self, agent="Codex", source_format="codex-rollout-jsonl"
        )

    def conversation(self, content: bytes) -> ConversationPreview:
        rows, issues = read_rows(content, _Row)
        messages: list[ConversationMessage] = []
        for line, row in rows:
            payload = row.payload
            if row.type != "response_item" or payload is None or payload.type != "message":
                continue
            if payload.role not in ("user", "assistant"):
                continue
            text = _text(payload)
            if text:
                role = "user" if payload.role == "user" else "assistant"
                messages.append(ConversationMessage(role, text, line))
        return bounded(messages, issues, VERSION)
