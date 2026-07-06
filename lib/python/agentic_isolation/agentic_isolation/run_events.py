"""RunEvent: the live event stream emitted while executing a RunSpec.

Implements Plan 1b Task 2 of the RunSpec/RunResult contract work: a
discriminated union of event variants a harness adapter emits during
a run (tool lifecycle, token usage, session end), plus the
`EventCallback` signature callers register to observe them and a
`CancelMode` used to request cancellation of an in-flight run.

This is the live-streaming counterpart to the terminal `RunResult`
(see `run_result.py`); `RunResult.observability` is the
after-the-fact summary, `RunEvent` is the moment-by-moment feed.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

CancelMode = Literal["graceful", "hard"]


class ToolStartEvent(BaseModel):
    """A tool invocation has started."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["tool_start"] = "tool_start"
    tool_name: str = Field(min_length=1)
    tool_use_id: str = Field(min_length=1)


class ToolEndEvent(BaseModel):
    """A tool invocation has finished."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["tool_end"] = "tool_end"
    tool_name: str = Field(min_length=1)
    tool_use_id: str = Field(min_length=1)
    success: bool


class TokenUsageEvent(BaseModel):
    """A token usage sample for the in-progress run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["token_usage"] = "token_usage"
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class SessionEndEvent(BaseModel):
    """The run's session has ended."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["session_end"] = "session_end"
    success: bool


RunEvent = Annotated[
    ToolStartEvent | ToolEndEvent | TokenUsageEvent | SessionEndEvent,
    Field(discriminator="type"),
]


class RunEventEnvelope(BaseModel):
    """Wraps a `RunEvent` so the discriminated union can be validated
    directly (pydantic v2 requires a `BaseModel` field to trigger
    union discrimination outside of a `TypeAdapter`).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    event: RunEvent


EventCallback = Callable[[RunEvent], None]
