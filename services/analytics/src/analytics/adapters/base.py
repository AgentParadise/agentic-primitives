"""Base adapter interface for provider-specific event transformations"""

from abc import ABC, abstractmethod
from typing import Any

from analytics.models.hook_input import HookInput


class BaseProviderAdapter(ABC):
    """Abstract base class for provider-specific adapters

    Each provider (Claude, OpenAI, etc.) has different event formats.
    Adapters normalize these differences into a common format.
    """

    @abstractmethod
    def extract_session_id(self, hook_input: HookInput) -> str:
        """Extract session ID from provider-specific format

        Args:
            hook_input: Raw hook input from provider

        Returns:
            str: Normalized session ID
        """
        pass

    @abstractmethod
    def extract_context(self, hook_input: HookInput) -> dict[str, Any]:
        """Extract event context (tool_name, tool_input, etc.)

        Args:
            hook_input: Raw hook input from provider

        Returns:
            dict: Event-specific context data
        """
        pass

    @abstractmethod
    def extract_metadata(self, hook_input: HookInput) -> dict[str, Any]:
        """Extract provider-specific metadata

        Args:
            hook_input: Raw hook input from provider

        Returns:
            dict: Event metadata and provenance
        """
        pass

    def extract_cwd(self, hook_input: HookInput) -> str | None:
        """Extract current working directory (common across providers)

        Args:
            hook_input: Raw hook input from provider

        Returns:
            str | None: Current working directory if available
        """
        return hook_input.data.get("cwd")

