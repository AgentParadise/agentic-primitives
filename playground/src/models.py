"""Model alias resolution for playground scenarios.

Resolves version-agnostic model aliases to full API names.

Resolution chain:
    claude-haiku → claude-4-5-haiku → claude-haiku-4-5-20251001

Supports three input formats:
    1. Simple alias: "claude-haiku" → resolves via current_models → model YAML
    2. Model ID: "claude-4-5-haiku" → resolves via model YAML
    3. Full API name: "claude-haiku-4-5-20251001" → passthrough (no resolution)
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import yaml

# Root of agentic-primitives repo (relative to this file)
REPO_ROOT = Path(__file__).parent.parent.parent


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file safely."""
    with path.open() as f:
        return yaml.safe_load(f) or {}


@functools.lru_cache(maxsize=1)
def _load_anthropic_config() -> dict[str, Any]:
    """Load the Anthropic provider config (cached)."""
    config_path = REPO_ROOT / "providers" / "models" / "anthropic" / "config.yaml"
    if not config_path.exists():
        return {}
    return _load_yaml(config_path)


@functools.lru_cache(maxsize=32)
def _load_model_config(model_id: str) -> dict[str, Any] | None:
    """Load a specific model's YAML config (cached).

    Args:
        model_id: Model ID like "claude-4-5-haiku"

    Returns:
        Model config dict or None if not found
    """
    model_path = REPO_ROOT / "providers" / "models" / "anthropic" / f"{model_id}.yaml"
    if not model_path.exists():
        return None
    return _load_yaml(model_path)


def _looks_like_api_name(model: str) -> bool:
    """Check if a model string looks like a full API name.

    API names have date suffixes like: claude-haiku-4-5-20251001

    Args:
        model: Model string to check

    Returns:
        True if it looks like a full API name
    """
    # API names end with YYYYMMDD date pattern
    if len(model) < 8:
        return False

    # Check if last 8 chars are all digits (date)
    suffix = model[-8:]
    return suffix.isdigit()


def resolve_model(model: str) -> str:
    """Resolve a model alias to its full API name.

    Supports three input formats:
        1. Simple alias: "claude-haiku" → resolves via current_models → model YAML
        2. Model ID: "claude-4-5-haiku" → resolves via model YAML
        3. Full API name: "claude-haiku-4-5-20251001" → passthrough

    Args:
        model: Model alias, ID, or full API name

    Returns:
        Full API name for use with Claude CLI --model flag

    Raises:
        ValueError: If the model cannot be resolved
    """
    if not model:
        raise ValueError("Model cannot be empty")

    # Format 3: Full API name - passthrough
    if _looks_like_api_name(model):
        return model

    # Try Format 1: Simple alias (claude-haiku → claude-4-5-haiku)
    config = _load_anthropic_config()
    current_models = config.get("current_models", {})

    model_id = current_models.get(model)
    if model_id:
        # Alias found, now get the API name from model config
        model_config = _load_model_config(model_id)
        if model_config and "api_name" in model_config:
            return model_config["api_name"]

    # Try Format 2: Model ID directly (claude-4-5-haiku → api_name)
    model_config = _load_model_config(model)
    if model_config and "api_name" in model_config:
        return model_config["api_name"]

    # Nothing matched - raise helpful error
    available_aliases = list(current_models.keys())
    raise ValueError(
        f"Unknown model: '{model}'. "
        f"Available aliases: {', '.join(sorted(available_aliases))}"
    )


def get_available_aliases() -> list[str]:
    """Get list of available model aliases.

    Returns:
        List of available aliases like ['claude-haiku', 'claude-sonnet', 'claude-opus']
    """
    config = _load_anthropic_config()
    current_models = config.get("current_models", {})
    return sorted(current_models.keys())
