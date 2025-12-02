"""Base storage adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hooks_backend.models import HookEventStored


class Storage(ABC):
    """Abstract base class for storage adapters.

    All storage adapters must implement:
    - store(): Store events
    - health_check(): Check storage health
    - connect(): Connect to storage (optional)
    - close(): Close storage connection (optional)
    """

    @abstractmethod
    async def store(self, events: list[HookEventStored]) -> int:
        """Store events in the backend.

        Args:
            events: List of events to store.

        Returns:
            Number of events successfully stored.

        Raises:
            Exception: If storage fails.
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if storage is healthy.

        Returns:
            True if storage is accessible and working.
        """
        ...

    async def connect(self) -> None:  # noqa: B027
        """Connect to the storage backend.

        Override if storage needs initialization.
        Default implementation is a no-op.
        """

    async def close(self) -> None:  # noqa: B027
        """Close storage connection.

        Override if storage needs cleanup.
        Default implementation is a no-op.
        """

    @property
    def name(self) -> str:
        """Storage adapter name."""
        return self.__class__.__name__
