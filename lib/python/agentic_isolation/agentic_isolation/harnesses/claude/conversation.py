"""Claude Code transcript rows -> human-visible user/assistant text.

ALLOWLIST (observed in Claude Code 2.1.x transcripts):

* row ``type`` is ``user`` or ``assistant`` and ``message.role`` matches it;
* not ``isMeta``, ``isCompactSummary``, ``isVisibleInTranscriptOnly`` or
  ``isApiErrorMessage`` (injected context, compaction summaries, replays and
  synthetic errors);
* a user row with an ``origin`` must be ``origin.kind == "human"`` (excludes
  task notifications and auto-continuations); a user row carrying any
  ``tool_result`` block is tool output, not a human turn;
* only ``text`` blocks (or a plain string) are read, so ``thinking``,
  ``redacted_thinking``, ``tool_use`` and ``tool_result`` never leak;
* user text wrapped as command/tool output is excluded;
* sidechain membership is locked by the first accepted row, so a root
  transcript never mixes in inline sidechain rows while a child transcript
  (all rows sidechain) still previews.

Every other row type (summary, system, attachment, file snapshots, ...) is
ignored by construction.
"""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import Field, JsonValue

from agentic_isolation.harnesses.conversation import (
    ConversationPreview,
    Role,
    read_envelope,
    read_native,
)
from agentic_isolation.harnesses.evidence import WireModel

VERSION = "claude-conversation-preview/2"

_OUTPUT_WRAPPERS = (
    "<local-command-stdout>",
    "<local-command-stderr>",
    "<bash-stdout>",
    "<bash-stderr>",
    "<task-notification>",
)


class _Part(WireModel):
    type: str = ""
    text: JsonValue = None


class _Message(WireModel):
    role: str | None = None
    content: list[_Part] | str | None = None


class _Origin(WireModel):
    kind: str | None = None


class _Row(WireModel):
    type: str = ""
    message: _Message | JsonValue = None
    is_meta: bool | None = Field(default=None, alias="isMeta")
    compact: bool | None = Field(default=None, alias="isCompactSummary")
    transcript_only: bool | None = Field(default=None, alias="isVisibleInTranscriptOnly")
    api_error: bool | None = Field(default=None, alias="isApiErrorMessage")
    sidechain: bool | None = Field(default=None, alias="isSidechain")
    origin: _Origin | JsonValue = None


def _text(message: _Message) -> str:
    if isinstance(message.content, str):
        return message.content
    if not message.content:
        return ""
    return "\n".join(
        part.text for part in message.content if part.type == "text" and isinstance(part.text, str)
    )


def _is_tool_output(message: _Message) -> bool:
    return isinstance(message.content, list) and any(
        part.type == "tool_result" for part in message.content
    )


class _Parser:
    def __init__(self) -> None:
        self._sidechain: bool | None = None

    def messages(self, line: bytes) -> Iterable[tuple[Role, str]]:
        row = _Row.model_validate_json(line)
        message = row.message
        if row.type not in ("user", "assistant") or not isinstance(message, _Message):
            return ()
        if message.role != row.type:
            return ()
        if row.is_meta or row.compact or row.transcript_only or row.api_error:
            return ()
        role: Role = "user" if row.type == "user" else "assistant"
        if role == "user":
            if row.origin is not None and not (
                isinstance(row.origin, _Origin) and row.origin.kind == "human"
            ):
                return ()
            if _is_tool_output(message):
                return ()
        text = _text(message)
        if not text or (role == "user" and text.lstrip().startswith(_OUTPUT_WRAPPERS)):
            return ()
        sidechain = bool(row.sidechain)
        if self._sidechain is None:
            self._sidechain = sidechain
        elif sidechain != self._sidechain:
            return ()
        return ((role, text),)


class ClaudeConversationReader:
    def conversation_envelope(self, content: bytes) -> ConversationPreview:
        return read_envelope(
            content, _Parser(), VERSION, agent="ClaudeCode", source_format="claude-code-jsonl"
        )

    def conversation(self, content: bytes) -> ConversationPreview:
        return read_native(content, _Parser(), VERSION)
