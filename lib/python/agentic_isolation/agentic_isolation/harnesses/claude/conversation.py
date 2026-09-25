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
* harness-injected tagged segments (``HARNESS_INJECTED_TAGS``) are removed
  from user text WHEREVER they appear, not only as a prefix; a row left empty
  shows nothing;
* the document's own identity decides whose turns are shown: a root
  transcript shows only non-sidechain rows, a child transcript
  (``agent-<agentId>``, the native identity ``ClaudeNativeEvidenceReader``
  assigns) shows only its own sidechain rows. Identity comes from the caller,
  the capture envelope, or a bounded identity pre-pass, never from row order.

Every other row type (summary, system, attachment, file snapshots, ...) is
ignored by construction.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from pydantic import Field, JsonValue, ValidationError

from agentic_isolation.harnesses.conversation import (
    MAX_DOCUMENT_BYTES,
    ConversationPreview,
    Role,
    collect,
    native_lines,
    read_envelope,
)
from agentic_isolation.harnesses.evidence import WireModel

VERSION = "claude-conversation-preview/3"
CHILD_PREFIX = "agent-"

#: Tagged segments Claude Code inserts into USER message text that the human
#: did not type: reminders/context it injects, and captured command/tool output.
HARNESS_INJECTED_TAGS = (
    "system-reminder",
    "local-command-stdout",
    "local-command-stderr",
    "local-command-caveat",
    "bash-stdout",
    "bash-stderr",
    "task-notification",
    "user-prompt-submit-hook",
)
_TAGS = "|".join(re.escape(tag) for tag in HARNESS_INJECTED_TAGS)
# A closed segment, or an unclosed one running to the end (never leak a tail).
_INJECTED = re.compile(rf"<({_TAGS})(?:\s[^>]*)?>.*?(?:</\1\s*>|\Z)", re.DOTALL)


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
    agent_id: JsonValue = Field(default=None, alias="agentId")
    origin: _Origin | JsonValue = None


class _IdentityRow(WireModel):
    session_id: JsonValue = Field(default=None, alias="sessionId")
    agent_id: JsonValue = Field(default=None, alias="agentId")
    sidechain: JsonValue = Field(default=None, alias="isSidechain")


def strip_injected(text: str) -> str:
    return _INJECTED.sub("", text).strip()


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


def document_identity(content: bytes) -> str | None:
    """The transcript's own native identity, by ClaudeNativeEvidenceReader's rule.

    One bounded streaming pass over a tiny row model: nothing is retained but
    the distinct ids. None when the document is not one transcript.
    """
    roots: set[str] = set()
    children: set[str] = set()
    for _, line in native_lines(content):
        if line is None or not line.strip():
            continue
        try:
            row = _IdentityRow.model_validate_json(line)
        except (ValidationError, ValueError, RecursionError):
            continue
        if isinstance(row.session_id, str) and row.session_id:
            roots.add(row.session_id)
        if row.sidechain is True and isinstance(row.agent_id, str) and row.agent_id:
            children.add(row.agent_id)
        if len(roots) > 1 or len(children) > 1:
            return None
    if len(roots) != 1:
        return None
    return CHILD_PREFIX + next(iter(children)) if children else next(iter(roots))


class _Parser:
    def __init__(self, native_id: str | None) -> None:
        child = native_id is not None and native_id.startswith(CHILD_PREFIX)
        self._child_agent = native_id[len(CHILD_PREFIX) :] if child and native_id else None

    def _belongs(self, row: _Row) -> bool:
        if self._child_agent is None:
            return not row.sidechain
        return bool(row.sidechain) and row.agent_id == self._child_agent

    def messages(self, line: bytes) -> Iterable[tuple[Role, str]]:
        row = _Row.model_validate_json(line)
        message = row.message
        if row.type not in ("user", "assistant") or not isinstance(message, _Message):
            return ()
        if message.role != row.type or not self._belongs(row):
            return ()
        if row.is_meta or row.compact or row.transcript_only or row.api_error:
            return ()
        role: Role = "user" if row.type == "user" else "assistant"
        text = _text(message)
        if role == "user":
            if row.origin is not None and not (
                isinstance(row.origin, _Origin) and row.origin.kind == "human"
            ):
                return ()
            if _is_tool_output(message):
                return ()
            text = strip_injected(text)
        return ((role, text),) if text else ()


class ClaudeConversationReader:
    def conversation_envelope(
        self, content: bytes, native_id: str | None = None
    ) -> ConversationPreview:
        return read_envelope(
            content,
            _Parser,
            VERSION,
            agent="ClaudeCode",
            source_format="claude-code-jsonl",
            native_id=native_id,
        )

    def conversation(self, content: bytes, native_id: str | None = None) -> ConversationPreview:
        if len(content) > MAX_DOCUMENT_BYTES:
            return ConversationPreview(issues=("document_byte_limit",), reader_version=VERSION)
        identity = native_id or document_identity(content)
        return collect(native_lines(content), _Parser(identity), VERSION)
