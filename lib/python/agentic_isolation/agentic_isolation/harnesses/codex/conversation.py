"""Codex rollout rows -> human-visible user/assistant text.

The source is the rollout's EVENT stream, not ``response_item`` rows: in a real
codex-cli 0.156.1 rollout (``tests/fixtures/codex_rollout_0.156.1.jsonl``,
generated offline) the ``response_item`` user messages include injected
``<environment_context>`` and the developer/skills instructions, none of which a
human saw. ALLOWLIST:

* 0.156.x: ``event_msg`` / ``item_completed`` whose ``item.type`` is
  ``UserMessage`` (read ``text`` parts) or ``AgentMessage`` (read ``Text``
  parts). Items are de-duplicated by ``item.id``.
* earlier rollouts: ``event_msg`` / ``user_message`` and ``agent_message`` with
  a string ``message``.

The first family seen locks the document, so a rollout that carries both can
never show a message twice. Reasoning, commands, tool calls/output, token
counts and every ``response_item`` are ignored by construction.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from pydantic import JsonValue

from agentic_isolation.harnesses.conversation import (
    ConversationPreview,
    Role,
    read_envelope,
    read_native,
)
from agentic_isolation.harnesses.evidence import WireModel

VERSION = "codex-conversation-preview/2"

_ITEM_PARTS: dict[str, tuple[Role, str]] = {
    "UserMessage": ("user", "text"),
    "AgentMessage": ("assistant", "Text"),
}
_LEGACY: dict[str, Role] = {"user_message": "user", "agent_message": "assistant"}


class _Part(WireModel):
    type: str = ""
    text: JsonValue = None


class _Item(WireModel):
    type: str = ""
    id: str | None = None
    content: list[_Part] | JsonValue = None


class _Event(WireModel):
    type: str = ""
    item: _Item | JsonValue = None
    message: JsonValue = None


class _Row(WireModel):
    type: str = ""
    payload: _Event | JsonValue = None


class _Parser:
    def __init__(self) -> None:
        self._family: Literal["items", "legacy"] | None = None
        self._seen: set[str] = set()

    def _lock(self, family: Literal["items", "legacy"]) -> bool:
        if self._family is None:
            self._family = family
        return self._family == family

    def _item(self, item: _Item) -> Iterable[tuple[Role, str]]:
        allowed = _ITEM_PARTS.get(item.type)
        if allowed is None or not isinstance(item.content, list) or not self._lock("items"):
            return ()
        if item.id is not None:
            if item.id in self._seen:
                return ()
            self._seen.add(item.id)
        role, part_type = allowed
        text = "\n".join(
            part.text
            for part in item.content
            if part.type == part_type and isinstance(part.text, str)
        )
        return ((role, text),) if text else ()

    def messages(self, line: bytes) -> Iterable[tuple[Role, str]]:
        row = _Row.model_validate_json(line)
        event = row.payload
        if row.type != "event_msg" or not isinstance(event, _Event):
            return ()
        if event.type == "item_completed" and isinstance(event.item, _Item):
            return self._item(event.item)
        role = _LEGACY.get(event.type)
        if role is None or not isinstance(event.message, str) or not event.message:
            return ()
        return ((role, event.message),) if self._lock("legacy") else ()


class CodexConversationReader:
    def conversation_envelope(self, content: bytes) -> ConversationPreview:
        return read_envelope(
            content, _Parser(), VERSION, agent="Codex", source_format="codex-rollout-jsonl"
        )

    def conversation(self, content: bytes) -> ConversationPreview:
        return read_native(content, _Parser(), VERSION)
