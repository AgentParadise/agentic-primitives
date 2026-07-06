"""Tests for AgentRecipe models (APSS EXP-V1-0003 Agent Recipe Standard)."""

from typing import Any

import pytest
from pydantic import ValidationError

from agentic_isolation.recipe import AgentRecipe, ModelSpec, SystemInstructions

# Mirrors examples/valid/full.yaml from EXP-V1-0003-agent-recipe.
FULL_RECIPE: dict[str, Any] = {
    "name": "pr-reviewer",
    "agent": "claude",
    "model": {
        "name": "anthropic/claude-opus-4-8",
        "effort": "high",
    },
    "skills": ["code-review", "security-review"],
    "system_instructions": {
        "mode": "append",
        "content": (
            "Focus exclusively on correctness and security issues.\n"
            "Do not comment on style unless it affects readability of a "
            "security-relevant path.\n"
        ),
    },
}

# Mirrors examples/valid/minimal.yaml from EXP-V1-0003-agent-recipe.
MINIMAL_RECIPE: dict[str, Any] = {
    "name": "quick-fix",
    "agent": "codex",
    "model": {
        "name": "openai/gpt-5-codex",
        "effort": "low",
    },
}


class TestAgentRecipeValid:
    def test_full_recipe_round_trips(self) -> None:
        recipe = AgentRecipe.model_validate(FULL_RECIPE)

        assert recipe.name == "pr-reviewer"
        assert recipe.agent == "claude"
        assert recipe.model == ModelSpec(name="anthropic/claude-opus-4-8", effort="high")
        assert recipe.skills == ["code-review", "security-review"]
        assert recipe.system_instructions == SystemInstructions(
            mode="append",
            content=FULL_RECIPE["system_instructions"]["content"],
        )

        # Round-trip: dump then re-validate should be equivalent (4.3 Round-Tripping).
        dumped = recipe.model_dump(mode="json")
        assert AgentRecipe.model_validate(dumped) == recipe

    def test_minimal_recipe_defaults(self) -> None:
        recipe = AgentRecipe.model_validate(MINIMAL_RECIPE)

        assert recipe.name == "quick-fix"
        assert recipe.agent == "codex"
        assert recipe.model == ModelSpec(name="openai/gpt-5-codex", effort="low")
        # skills defaults to empty list when omitted (spec 3.5).
        assert recipe.skills == []
        # system_instructions is optional (spec 3.2).
        assert recipe.system_instructions is None

    def test_recipe_is_frozen(self) -> None:
        recipe = AgentRecipe.model_validate(MINIMAL_RECIPE)

        with pytest.raises(ValidationError):
            recipe.name = "renamed"  # type: ignore[misc]


class TestAgentRecipeInvalid:
    def test_unknown_top_level_field_rejected(self) -> None:
        # Mirrors examples/invalid/unknown-field.yaml (AGENT_RECIPE_UNKNOWN_FIELD).
        payload = {**FULL_RECIPE, "temperature": 0.7}

        with pytest.raises(ValidationError):
            AgentRecipe.model_validate(payload)

    def test_unknown_nested_field_rejected(self) -> None:
        payload = {
            **MINIMAL_RECIPE,
            "model": {**MINIMAL_RECIPE["model"], "temperature": 0.7},
        }

        with pytest.raises(ValidationError):
            AgentRecipe.model_validate(payload)

    def test_unknown_agent_rejected(self) -> None:
        # Mirrors examples/invalid/unknown-agent.yaml (AGENT_RECIPE_UNKNOWN_AGENT).
        payload = {
            "name": "bad-recipe",
            "agent": "gemini",
            "model": {"name": "google/gemini-3-pro", "effort": "medium"},
        }

        with pytest.raises(ValidationError):
            AgentRecipe.model_validate(payload)

    def test_invalid_effort_and_mode_rejected(self) -> None:
        # Mirrors examples/invalid/invalid-effort-and-mode.yaml.
        payload = {
            "name": "bad-recipe",
            "agent": "claude",
            "model": {"name": "anthropic/claude-opus-4-8", "effort": "extreme"},
            "system_instructions": {"mode": "overwrite", "content": "do the thing"},
        }

        with pytest.raises(ValidationError):
            AgentRecipe.model_validate(payload)

    def test_missing_required_fields_rejected(self) -> None:
        # Mirrors examples/invalid/missing-required-fields.yaml.
        with pytest.raises(ValidationError):
            AgentRecipe.model_validate({"name": ""})

    def test_missing_agent_rejected(self) -> None:
        payload = {
            "name": "bad-recipe",
            "model": {"name": "anthropic/claude-opus-4-8", "effort": "high"},
        }

        with pytest.raises(ValidationError):
            AgentRecipe.model_validate(payload)

    def test_missing_model_rejected(self) -> None:
        payload = {"name": "bad-recipe", "agent": "claude"}

        with pytest.raises(ValidationError):
            AgentRecipe.model_validate(payload)

    def test_missing_model_name_rejected(self) -> None:
        payload = {
            "name": "bad-recipe",
            "agent": "claude",
            "model": {"effort": "high"},
        }

        with pytest.raises(ValidationError):
            AgentRecipe.model_validate(payload)

    def test_empty_model_name_rejected(self) -> None:
        # AGENT_RECIPE_MISSING_MODEL_NAME (spec section 5): model.name MUST be non-empty.
        payload = {
            "name": "bad-recipe",
            "agent": "claude",
            "model": {"name": "", "effort": "high"},
        }

        with pytest.raises(ValidationError):
            AgentRecipe.model_validate(payload)

    def test_empty_skill_ref_rejected(self) -> None:
        # AGENT_RECIPE_INVALID_SKILL_REF (spec section 5): each skill entry MUST be non-empty.
        payload = {**MINIMAL_RECIPE, "skills": ["code-review", ""]}

        with pytest.raises(ValidationError):
            AgentRecipe.model_validate(payload)

    def test_empty_instructions_content_rejected(self) -> None:
        # AGENT_RECIPE_EMPTY_INSTRUCTIONS_CONTENT (spec section 5).
        payload = {
            **MINIMAL_RECIPE,
            "system_instructions": {"mode": "append", "content": ""},
        }

        with pytest.raises(ValidationError):
            AgentRecipe.model_validate(payload)


class TestModelSpec:
    def test_valid_efforts(self) -> None:
        for effort in ("low", "medium", "high"):
            spec = ModelSpec.model_validate({"name": "anthropic/claude-opus-4-8", "effort": effort})
            assert spec.effort == effort

    def test_invalid_effort_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ModelSpec.model_validate({"name": "anthropic/claude-opus-4-8", "effort": "extreme"})

    def test_unknown_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ModelSpec.model_validate(
                {"name": "anthropic/claude-opus-4-8", "effort": "high", "temperature": 0.7}
            )


class TestSystemInstructions:
    def test_valid_modes(self) -> None:
        for mode in ("append", "replace"):
            instructions = SystemInstructions.model_validate({"mode": mode, "content": "text"})
            assert instructions.mode == mode

    def test_invalid_mode_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SystemInstructions.model_validate({"mode": "overwrite", "content": "text"})

    def test_unknown_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SystemInstructions.model_validate(
                {"mode": "append", "content": "text", "extra": "nope"}
            )
