"""Claude Code transcript rows -> user/assistant text for preview."""

from __future__ import annotations

from agentic_isolation.harnesses.conversation import (
    ConversationMessage,
    ConversationPreview,
    bounded,
    conversation_from_envelope,
)
from agentic_isolation.harnesses.evidence import WireModel, read_rows

VERSION = "claude-conversation-preview/1"


class _Part(WireModel):
    type: str = ""
    text: str | None = None


class _Message(WireModel):
    role: str | None = None
    content: list[_Part] | str | None = None


class _Row(WireModel):
    message: _Message | None = None


def _text(message: _Message) -> str:
    if isinstance(message.content, str):
        return message.content
    if not message.content:
        return ""
    return "\n".join(part.text for part in message.content if part.text)


class ClaudeConversationReader:
    def conversation_envelope(self, content: bytes) -> ConversationPreview:
        return conversation_from_envelope(
            content, self, agent="ClaudeCode", source_format="claude-code-jsonl"
        )

    def conversation(self, content: bytes) -> ConversationPreview:
        rows, issues = read_rows(content, _Row)
        messages: list[ConversationMessage] = []
        for line, row in rows:
            message = row.message
            if message is None or message.role not in ("user", "assistant"):
                continue
            text = _text(message)
            if text:
                role = "user" if message.role == "user" else "assistant"
                messages.append(ConversationMessage(role, text, line))
        return bounded(messages, issues, VERSION)
