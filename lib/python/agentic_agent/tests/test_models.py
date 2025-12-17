"""Tests for model pricing."""

import pytest

from agentic_agent.models import (
    ModelPricing,
    get_model_pricing,
    list_models,
    ANTHROPIC_MODELS,
    DEFAULT_MODEL,
)


class TestModelPricing:
    """Tests for ModelPricing class."""

    def test_calculate_cost_basic(self) -> None:
        """Should calculate cost correctly."""
        pricing = ModelPricing(
            api_name="test-model",
            display_name="Test Model",
            provider="test",
            input_per_1m_tokens=3.0,
            output_per_1m_tokens=15.0,
        )

        # 1M input tokens = $3, 1M output tokens = $15
        cost = pricing.calculate_cost(1_000_000, 1_000_000)
        assert cost == 18.0

        # 1K tokens
        cost = pricing.calculate_cost(1000, 1000)
        assert cost == pytest.approx(0.018, rel=0.01)

    def test_calculate_cost_zero(self) -> None:
        """Should handle zero tokens."""
        pricing = get_model_pricing(DEFAULT_MODEL)
        cost = pricing.calculate_cost(0, 0)
        assert cost == 0.0

    def test_known_models_have_pricing(self) -> None:
        """All known models should have valid pricing."""
        for api_name, pricing in ANTHROPIC_MODELS.items():
            assert pricing.api_name == api_name
            assert pricing.input_per_1m_tokens > 0
            assert pricing.output_per_1m_tokens > 0
            assert pricing.context_window > 0


class TestGetModelPricing:
    """Tests for get_model_pricing function."""

    def test_exact_match(self) -> None:
        """Should find model by exact name."""
        pricing = get_model_pricing("claude-sonnet-4-20250514")
        assert pricing.api_name == "claude-sonnet-4-20250514"
        assert "sonnet" in pricing.display_name.lower()

    def test_partial_match(self) -> None:
        """Should find model by partial name."""
        pricing = get_model_pricing("sonnet")
        assert "sonnet" in pricing.api_name.lower()

    def test_unknown_model_returns_default_pricing(self) -> None:
        """Should return default pricing for unknown models."""
        pricing = get_model_pricing("unknown-model-xyz")
        assert pricing.api_name == "unknown-model-xyz"
        assert pricing.provider == "unknown"
        # Should have reasonable default pricing
        assert pricing.input_per_1m_tokens > 0
        assert pricing.output_per_1m_tokens > 0


class TestListModels:
    """Tests for list_models function."""

    def test_returns_known_models(self) -> None:
        """Should return list of known model names."""
        models = list_models()
        assert len(models) > 0
        assert all(isinstance(m, str) for m in models)
        assert "claude-sonnet-4-20250514" in models


class TestDefaultModel:
    """Tests for DEFAULT_MODEL constant."""

    def test_default_model_exists(self) -> None:
        """Default model should be loadable."""
        pricing = get_model_pricing(DEFAULT_MODEL)
        assert pricing.api_name == DEFAULT_MODEL
