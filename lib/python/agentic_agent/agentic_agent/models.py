"""Model pricing configuration for cost estimation.

Provides built-in pricing data for common models.
No external YAML files required.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True)
class ModelPricing:
    """Pricing information for a model."""

    api_name: str
    display_name: str
    provider: str
    input_per_1m_tokens: float
    output_per_1m_tokens: float
    context_window: int = 200_000
    max_output_tokens: int = 8192

    def calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost in USD for given token counts.

        Args:
            input_tokens: Number of input tokens used
            output_tokens: Number of output tokens generated

        Returns:
            Cost in USD
        """
        input_cost = (input_tokens / 1_000_000) * self.input_per_1m_tokens
        output_cost = (output_tokens / 1_000_000) * self.output_per_1m_tokens
        return input_cost + output_cost


# Built-in pricing for common models (as of Dec 2025)
ANTHROPIC_MODELS: dict[str, ModelPricing] = {
    # Claude 4 Opus
    "claude-opus-4-20250514": ModelPricing(
        api_name="claude-opus-4-20250514",
        display_name="Claude 4 Opus",
        provider="anthropic",
        input_per_1m_tokens=15.0,
        output_per_1m_tokens=75.0,
        context_window=200_000,
        max_output_tokens=32_000,
    ),
    # Claude 4 Sonnet
    "claude-sonnet-4-20250514": ModelPricing(
        api_name="claude-sonnet-4-20250514",
        display_name="Claude 4 Sonnet",
        provider="anthropic",
        input_per_1m_tokens=3.0,
        output_per_1m_tokens=15.0,
        context_window=200_000,
        max_output_tokens=64_000,
    ),
    # Claude 3.5 Sonnet (legacy)
    "claude-3-5-sonnet-20241022": ModelPricing(
        api_name="claude-3-5-sonnet-20241022",
        display_name="Claude 3.5 Sonnet",
        provider="anthropic",
        input_per_1m_tokens=3.0,
        output_per_1m_tokens=15.0,
        context_window=200_000,
        max_output_tokens=8192,
    ),
    # Claude 3.5 Haiku
    "claude-3-5-haiku-20241022": ModelPricing(
        api_name="claude-3-5-haiku-20241022",
        display_name="Claude 3.5 Haiku",
        provider="anthropic",
        input_per_1m_tokens=0.80,
        output_per_1m_tokens=4.0,
        context_window=200_000,
        max_output_tokens=8192,
    ),
    # Claude 4.5 Haiku (cheapest)
    "claude-haiku-4-5-20251001": ModelPricing(
        api_name="claude-haiku-4-5-20251001",
        display_name="Claude 4.5 Haiku",
        provider="anthropic",
        input_per_1m_tokens=1.0,
        output_per_1m_tokens=5.0,
        context_window=200_000,
        max_output_tokens=8192,
    ),
}

# Default model for testing (cheap and fast)
DEFAULT_MODEL = "claude-sonnet-4-20250514"


def get_model_pricing(model_name: str) -> ModelPricing:
    """Get pricing for a model by name.

    Args:
        model_name: Model API name or short name

    Returns:
        ModelPricing for the model

    Raises:
        ValueError: If model not found
    """
    # Exact match
    if model_name in ANTHROPIC_MODELS:
        return ANTHROPIC_MODELS[model_name]

    # Try partial match (e.g., "sonnet" -> latest sonnet)
    model_lower = model_name.lower()
    for api_name, pricing in ANTHROPIC_MODELS.items():
        if model_lower in api_name.lower():
            return pricing

    # Return a default pricing if unknown model
    # This allows using new models before pricing is added
    return ModelPricing(
        api_name=model_name,
        display_name=model_name,
        provider="unknown",
        input_per_1m_tokens=3.0,  # Assume mid-tier pricing
        output_per_1m_tokens=15.0,
    )


def list_models() -> list[str]:
    """List all known model API names."""
    return list(ANTHROPIC_MODELS.keys())
