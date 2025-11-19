"""Provider adapters for event normalization

Each adapter handles provider-specific event format transformations.
"""

from analytics.adapters.base import BaseProviderAdapter
from analytics.adapters.claude import ClaudeAdapter
from analytics.adapters.openai import OpenAIAdapter

__all__ = ["BaseProviderAdapter", "ClaudeAdapter", "OpenAIAdapter"]

