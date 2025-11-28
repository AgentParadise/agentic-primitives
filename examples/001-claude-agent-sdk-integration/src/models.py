"""Model configuration loader for cost estimation.

Loads model pricing information from providers/models/anthropic/*.yaml
to enable accurate cost calculation for agent sessions.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class ModelConfig:
    """Model configuration with pricing information."""

    id: str
    api_name: str
    display_name: str
    provider: str
    input_per_1m_tokens: float
    output_per_1m_tokens: float
    context_window: int
    max_output_tokens: int
    supports_tools: bool = True
    supports_vision: bool = False
    supports_extended_thinking: bool = False

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

    def estimate_cost_for_context(self, context_fill_ratio: float = 0.5) -> float:
        """Estimate cost for filling context window.

        Args:
            context_fill_ratio: How much of context window to fill (0-1)

        Returns:
            Estimated cost in USD
        """
        estimated_input = int(self.context_window * context_fill_ratio)
        # Assume 20% of context as output
        estimated_output = int(estimated_input * 0.2)
        return self.calculate_cost(estimated_input, estimated_output)


# Path to model configurations relative to this file
MODELS_PATH = Path(__file__).parent.parent.parent.parent / "providers" / "models" / "anthropic"

# Cache for loaded configs
_config_cache: dict[str, ModelConfig] = {}


def load_model_config(api_name: str) -> ModelConfig:
    """Load model configuration by API name.

    Args:
        api_name: The model's API identifier (e.g., "claude-sonnet-4-5-20250929")

    Returns:
        ModelConfig with pricing and capabilities

    Raises:
        FileNotFoundError: If model config not found
        ValueError: If config is malformed
    """
    if api_name in _config_cache:
        return _config_cache[api_name]

    # Try to find the model config file
    config_file = _find_model_config_file(api_name)

    if not config_file or not config_file.exists():
        raise FileNotFoundError(f"Model config not found for: {api_name}")

    with open(config_file) as f:
        data = yaml.safe_load(f)

    # Parse the YAML structure
    config = _parse_model_config(data, api_name)
    _config_cache[api_name] = config
    return config


def _find_model_config_file(api_name: str) -> Optional[Path]:
    """Find the config file for a given API name.

    Model configs can be named with the api_name or a simplified version.
    """
    # Direct match with api_name
    for yaml_file in MODELS_PATH.glob("*.yaml"):
        if yaml_file.name == "config.yaml":
            continue  # Skip provider config

        with open(yaml_file) as f:
            data = yaml.safe_load(f)
            if data.get("api_name") == api_name:
                return yaml_file

    # Try matching by file name patterns
    name_variants = [
        api_name,
        api_name.replace("-", "_"),
        # Strip date suffix for matching
        api_name.rsplit("-", 1)[0] if api_name[-8:].isdigit() else api_name,
    ]

    for variant in name_variants:
        candidate = MODELS_PATH / f"{variant}.yaml"
        if candidate.exists():
            return candidate

    return None


def _parse_model_config(data: dict, api_name: str) -> ModelConfig:
    """Parse YAML data into ModelConfig.

    Handles the provider-specific YAML structure.
    """
    # Get pricing from the pricing section
    pricing = data.get("pricing", {})

    # Handle different pricing formats
    input_price = pricing.get("input_per_1m_tokens", 0)
    output_price = pricing.get("output_per_1m_tokens", 0)

    # If prices are strings with $, parse them
    if isinstance(input_price, str):
        input_price = float(input_price.replace("$", ""))
    if isinstance(output_price, str):
        output_price = float(output_price.replace("$", ""))

    # Get capabilities
    capabilities = data.get("capabilities", {})
    context = data.get("context", {})

    return ModelConfig(
        id=data.get("id", api_name),
        api_name=data.get("api_name", api_name),
        display_name=data.get("display_name", api_name),
        provider=data.get("provider", "anthropic"),
        input_per_1m_tokens=float(input_price),
        output_per_1m_tokens=float(output_price),
        context_window=context.get("window", 200000),
        max_output_tokens=context.get("max_output", 8192),
        supports_tools=capabilities.get("tool_use", True),
        supports_vision=capabilities.get("vision", False),
        supports_extended_thinking=capabilities.get("extended_thinking", False),
    )


def list_available_models() -> list[str]:
    """List all available model API names.

    Returns:
        List of model API names that can be loaded
    """
    models = []
    for yaml_file in MODELS_PATH.glob("*.yaml"):
        if yaml_file.name == "config.yaml":
            continue

        try:
            with open(yaml_file) as f:
                data = yaml.safe_load(f)
                if api_name := data.get("api_name"):
                    models.append(api_name)
        except Exception:
            continue

    return sorted(models)


# Default model for testing (cheaper, latest Haiku)
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
