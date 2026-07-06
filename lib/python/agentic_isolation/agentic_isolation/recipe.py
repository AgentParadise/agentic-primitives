"""Agent recipe contract models.

Implements the schema defined by the APSS Agent Recipe Standard
(EXP-V1-0003-agent-recipe, v0.1.0): a declarative, harness-neutral
description of which agent harness to run, which model and reasoning
effort to configure it with, which skills to inject, and what system
instructions to apply.

A recipe MUST NOT contain task-specific input, credentials, or
infrastructure configuration - see section 1.2 of the spec.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ModelSpec(BaseModel):
    """Model selection for an agent recipe (spec section 3.4).

    `name` is an opaque, provider-qualified string, e.g.
    "anthropic/claude-opus-4-8". `effort` is a coarse reasoning-effort
    level that a harness adapter translates into its own native
    parameter (Claude's `thinking_level`, Codex's reasoning effort).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    effort: Literal["low", "medium", "high"]


class SystemInstructions(BaseModel):
    """Additional system instructions for an agent recipe (spec section 3.6).

    `mode: append` causes the harness's own default system prompt (if
    any) to be used first, with `content` appended after it. `mode:
    replace` causes `content` to be used in place of the default
    system prompt.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Literal["append", "replace"]
    content: str = Field(min_length=1)


class AgentRecipe(BaseModel):
    """A declarative agent recipe (spec section 2.1 and 3.2).

    Identifies which harness to run (`agent`), which model and
    reasoning effort to configure it with (`model`), which skills to
    inject (`skills`), and what system instructions to apply
    (`system_instructions`).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    agent: Literal["claude", "codex"]
    model: ModelSpec
    skills: list[str] = Field(default_factory=list)
    system_instructions: SystemInstructions | None = None

    @field_validator("skills")
    @classmethod
    def _skills_non_empty(cls, skills: list[str]) -> list[str]:
        """Each skill reference MUST be a non-empty string (spec section 3.5)."""
        if any(not skill for skill in skills):
            raise ValueError("each skill reference must be a non-empty string")
        return skills
