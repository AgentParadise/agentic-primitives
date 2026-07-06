"""RunSpec: task-specific invocation contract for an agent recipe.

Implements Plan 1b Task 2 of the RunSpec/RunResult contract work: a
`RunSpec` pairs a harness-neutral `AgentRecipe` (see `recipe.py`) with
the task-specific input, credentials, and limits needed to actually
execute a run. Recipes stay reusable and credential-free; `RunSpec` is
the per-invocation envelope.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from agentic_isolation.recipe import AgentRecipe


class RunLimits(BaseModel):
    """Resource limits for a single run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    timeout_s: float | None = None
    token_budget: int | None = None


class ClaudeCredentials(BaseModel):
    """Credentials for the `claude` harness.

    `oauth_token` corresponds to the `CLAUDE_CODE_OAUTH_TOKEN`
    environment variable consumed by the Claude Code CLI.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    oauth_token: str = Field(min_length=1)


class CodexCredentials(BaseModel):
    """Credentials for the `codex` harness.

    `auth_json` holds the raw contents of `~/.codex/auth.json` (not a
    filesystem path). Callers read the file once and pass its
    contents through; the isolation layer writes it into the
    workspace at execution time. This avoids leaking host filesystem
    paths into a contract that may cross a process or network
    boundary.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    auth_json: str = Field(min_length=1)


class RunCredentials(BaseModel):
    """Per-harness credentials for a run, keyed by harness name.

    Only known harnesses (`claude`, `codex`) are accepted as keys;
    `extra="forbid"` rejects any other harness name at validation
    time rather than silently ignoring it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    claude: ClaudeCredentials | None = None
    codex: CodexCredentials | None = None


class ObservabilityExporter(BaseModel):
    """Placeholder for an observability exporter configuration.

    Minimal shape for Plan 1b Task 2: a `name` identifying the
    exporter and an opaque `config` bag. Plan 3 will replace this
    with a fully typed, per-exporter model (e.g. OTLP endpoint,
    headers, sampling) once the observability contract is designed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    config: dict[str, str] = Field(default_factory=dict)


class RunSpec(BaseModel):
    """A single task-specific invocation of an agent recipe.

    Pairs a harness-neutral `recipe` with the `task` description,
    optional `input_artifacts`, per-harness `credentials`, and
    resource `limits`. `observability` is a placeholder list of
    exporters (see `ObservabilityExporter`).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    recipe: AgentRecipe
    task: str = Field(min_length=1)
    input_artifacts: list[Path] = Field(default_factory=list)
    credentials: RunCredentials
    observability: list[ObservabilityExporter] = Field(default_factory=list)
    limits: RunLimits | None = None
