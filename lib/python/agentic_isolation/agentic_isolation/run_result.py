"""RunResult: the outcome contract for a completed RunSpec execution.

Implements Plan 1b Task 2 of the RunSpec/RunResult contract work: a
`RunResult` is what an isolation provider hands back after executing
a `RunSpec` (see `run_spec.py`) - whether the run succeeded, what
artifacts it produced, and the raw session log.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class RunOutcome(BaseModel):
    """Whether a run succeeded and a short human-readable summary."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    success: bool
    summary: str = Field(min_length=1)


class ObservabilityBundle(BaseModel):
    """Placeholder for the observability payload attached to a RunResult.

    Minimal shape for Plan 1b Task 2: a `session_id` correlating this
    bundle back to the run, and an opaque `metrics` bag. Plan 3 will
    replace this with the full observability contract (tool traces,
    token usage timelines, cost breakdown) once it lands.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: str = Field(min_length=1)
    metrics: dict[str, float] = Field(default_factory=dict)


class RunResult(BaseModel):
    """The outcome of executing a RunSpec.

    `result` carries the pass/fail summary, `output_artifacts` lists
    any files the run produced, and `session_log` is the raw
    harness transcript (e.g. JSONL stdout). `observability` is an
    optional placeholder bundle (see `ObservabilityBundle`).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    result: RunOutcome
    # Tuple (not list) for real immutability on this frozen model - a list
    # field is only shallow-frozen. Pydantic coerces list input to a tuple.
    output_artifacts: tuple[Path, ...] = Field(default_factory=tuple)
    session_log: str
    observability: ObservabilityBundle | None = None
