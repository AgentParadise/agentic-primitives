"""Event normalization logic for converting provider-specific events to standard format"""

from datetime import UTC, datetime

from analytics.adapters.base import BaseProviderAdapter
from analytics.adapters.claude import ClaudeAdapter
from analytics.adapters.openai import OpenAIAdapter
from analytics.models.events import (
    HOOK_EVENT_TO_ANALYTICS_EVENT,
    EventMetadata,
    NormalizedEvent,
)
from analytics.models.hook_input import HookInput


class EventNormalizer:
    """Normalizes provider-specific hook events into standardized analytics events

    Uses adapter pattern to delegate provider-specific logic to adapter classes.
    This allows the system to be provider-agnostic and easily extensible.
    """

    def __init__(self) -> None:
        """Initialize normalizer with provider adapters"""
        self._adapters: dict[str, BaseProviderAdapter] = {
            "claude": ClaudeAdapter(),
            "openai": OpenAIAdapter(),
        }

    def normalize(self, hook_input: HookInput) -> NormalizedEvent:
        """Normalize a hook input event into a standardized analytics event

        Args:
            hook_input: Provider-specific hook input event

        Returns:
            NormalizedEvent: Normalized analytics event

        Raises:
            ValueError: If event type is unknown
            pydantic.ValidationError: If data validation fails
        """
        # Get provider adapter (or use Claude as default fallback)
        adapter = self._adapters.get(hook_input.provider.lower())
        if adapter is None:
            # For unknown providers, try Claude adapter as fallback
            # This provides best-effort normalization for future providers
            adapter = self._adapters["claude"]

        # Extract common fields using adapter
        session_id = adapter.extract_session_id(hook_input)
        context = adapter.extract_context(hook_input)
        metadata_dict = adapter.extract_metadata(hook_input)
        cwd = adapter.extract_cwd(hook_input)

        # Map hook event to analytics event type
        hook_event_name = hook_input.data.get("hook_event_name", hook_input.event)
        event_type = HOOK_EVENT_TO_ANALYTICS_EVENT.get(hook_event_name)

        if event_type is None:
            raise ValueError(
                f"Unknown hook event type: {hook_event_name}. "
                f"Supported types: {list(HOOK_EVENT_TO_ANALYTICS_EVENT.keys())}"
            )

        # Generate timestamp (ISO 8601 UTC)
        timestamp = datetime.now(UTC)

        # Construct normalized event
        normalized_event = NormalizedEvent(
            event_type=event_type,
            timestamp=timestamp,
            session_id=session_id,
            provider=hook_input.provider,
            context=context,
            metadata=EventMetadata.model_validate(metadata_dict),
            cwd=cwd,
        )

        return normalized_event

    def register_adapter(self, provider: str, adapter: BaseProviderAdapter) -> None:
        """Register a custom provider adapter

        Allows extending the normalizer with new provider adapters at runtime.

        Args:
            provider: Provider name (e.g., "gemini", "anthropic")
            adapter: Provider adapter instance
        """
        self._adapters[provider.lower()] = adapter

    def get_supported_providers(self) -> list[str]:
        """Get list of supported provider names

        Returns:
            list[str]: List of registered provider names
        """
        return list(self._adapters.keys())
