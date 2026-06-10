"""Lazy-loading tests for the interactive-tmux provider.

The driver (providers/workspaces/interactive-tmux/driver/interactive_tmux.py)
is NOT packaged inside the agentic-isolation wheel: pyproject only ships the
`agentic_isolation` package. Importing `agentic_isolation` (or any of its
provider modules) must therefore never load the driver; only constructing or
using `InteractiveTmuxProvider` may, and a missing driver must surface as a
clear ImportError at that point, not at import time.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator

import pytest


def _matching_module_names() -> list[str]:
    return [
        name
        for name in sys.modules
        if name == "interactive_tmux" or name.startswith("agentic_isolation")
    ]


@pytest.fixture
def fresh_modules() -> Iterator[None]:
    """Drop agentic_isolation (and the driver) from sys.modules, restore after."""
    saved = {name: sys.modules[name] for name in _matching_module_names()}
    for name in saved:
        del sys.modules[name]
    try:
        yield
    finally:
        for name in _matching_module_names():
            del sys.modules[name]
        sys.modules.update(saved)


class TestLazyDriverImport:
    def test_import_package_does_not_load_driver(self, fresh_modules: None) -> None:
        """`import agentic_isolation` must not pull in the external driver."""
        import agentic_isolation  # noqa: F401
        import agentic_isolation.providers  # noqa: F401

        assert "interactive_tmux" not in sys.modules

    def test_provider_class_lazy_export(self, fresh_modules: None) -> None:
        """The provider class is importable without loading the driver."""
        from agentic_isolation.providers import InteractiveTmuxProvider

        assert InteractiveTmuxProvider.__name__ == "InteractiveTmuxProvider"
        assert "interactive_tmux" not in sys.modules

    def test_unknown_provider_attr_raises(self, fresh_modules: None) -> None:
        import agentic_isolation.providers as providers

        with pytest.raises(AttributeError):
            providers.NoSuchProvider  # noqa: B018

    def test_import_succeeds_with_driver_absent(
        self, fresh_modules: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With the driver unreachable, import works; first use raises ImportError."""
        monkeypatch.setenv(
            "AGENTIC_INTERACTIVE_TMUX_DRIVER", "/nonexistent/interactive_tmux.py"
        )

        import agentic_isolation  # noqa: F401
        from agentic_isolation.providers import interactive_tmux as adapter

        # Constructing the provider is the first driver use.
        with pytest.raises(ImportError):
            adapter.InteractiveTmuxProvider()

        # Re-exported driver names are also lazy and fail the same way.
        with pytest.raises(ImportError):
            adapter.InteractiveTmuxWorkspace  # noqa: B018


class TestProviderRegistry:
    def test_interactive_tmux_resolves_lazily(self, fresh_modules: None) -> None:
        from agentic_isolation.workspace import _resolve_provider_class

        provider_class = _resolve_provider_class("interactive-tmux")
        assert provider_class.__name__ == "InteractiveTmuxProvider"

    def test_unknown_provider_still_raises(self, fresh_modules: None) -> None:
        from agentic_isolation.workspace import _resolve_provider_class

        with pytest.raises(ValueError, match="Unknown provider"):
            _resolve_provider_class("definitely-not-a-provider")
