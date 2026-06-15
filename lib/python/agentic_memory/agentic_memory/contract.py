"""Memory contract — env-var parsing and validation.

The memory contract is six env vars (three required, three optional). This
module parses them into a `MemoryContract` dataclass and validates the
namespace shape.

See spec: docs/superpowers/specs/2026-05-13-memory-primitive-and-doctor-design.md
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from enum import Enum


NAMESPACE_PATTERN = re.compile(r"^[a-zA-Z0-9._:-]+$")
"""Allowed characters in AGENTIC_MEMORY_NAMESPACE — letters, digits, dot,
underscore, colon, hyphen. No spaces, no slashes, no shell metacharacters."""

PROVIDER_PATTERN = re.compile(r"^[a-zA-Z0-9._-]+$")
"""Allowed characters in AGENTIC_MEMORY_PROVIDER — provider names map to
directories under /opt/agentic/memory, so slashes and shell metacharacters are
not allowed."""


class NamespaceKind(str, Enum):
    """Semantic hint about what an AGENTIC_MEMORY_NAMESPACE represents.

    Adapters MAY use this to influence bank-id prefixing, log labels, etc.
    Adapters MUST NOT change isolation semantics based on this value —
    namespace isolation is always per `AGENTIC_MEMORY_NAMESPACE` regardless
    of kind.
    """

    TASK = "task"
    DOMAIN = "domain"
    WORKFLOW = "workflow"
    USER = "user"
    SESSION = "session"
    PROJECT = "project"
    CUSTOM = "custom"

    @classmethod
    def parse(cls, value: str | None) -> "NamespaceKind":
        if not value:
            return cls.TASK
        try:
            return cls(value.lower())
        except ValueError:
            return cls.CUSTOM


@dataclass(frozen=True)
class MemoryContract:
    """Parsed AGENTIC_MEMORY_* env vars.

    Use `MemoryContract.from_env()` to construct. The contract is intentionally
    immutable — once parsed, it's a value object that can be passed around.
    Adapters that need to mutate downstream state should produce new env vars
    in the process's environment, not rewrite this object.
    """

    provider: str
    namespace: str
    url: str | None
    namespace_kind: NamespaceKind = NamespaceKind.TASK
    auth: str | None = None
    config_json: str | None = None
    config_dict: dict | None = field(default=None, compare=False)

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "MemoryContract | None":
        """Parse contract from env vars. Returns None if AGENTIC_MEMORY_PROVIDER
        is unset or set to 'none' — i.e. the contract has not been opted into.

        Does NOT validate completeness — that's the doctor's job. This just
        produces the parsed value; missing required vars surface as empty
        strings / None and the doctor reports them.
        """
        e = env if env is not None else os.environ

        provider = e.get("AGENTIC_MEMORY_PROVIDER", "").strip()
        if not provider or provider.lower() == "none":
            return None

        config_json = e.get("AGENTIC_MEMORY_CONFIG_JSON")
        config_dict: dict | None = None
        if config_json:
            try:
                parsed = json.loads(config_json)
                if isinstance(parsed, dict):
                    config_dict = parsed
            except (json.JSONDecodeError, TypeError):
                config_dict = None  # doctor's `config_json_valid` check will catch this

        return cls(
            provider=provider,
            namespace=e.get("AGENTIC_MEMORY_NAMESPACE", "").strip(),
            url=e.get("AGENTIC_MEMORY_URL", "").strip() or None,
            namespace_kind=NamespaceKind.parse(e.get("AGENTIC_MEMORY_NAMESPACE_KIND")),
            auth=e.get("AGENTIC_MEMORY_AUTH") or None,
            config_json=config_json,
            config_dict=config_dict,
        )


def is_namespace_well_formed(namespace: str) -> bool:
    """True if the namespace string contains only allowed characters and is
    non-empty. See NAMESPACE_PATTERN."""
    return bool(namespace) and bool(NAMESPACE_PATTERN.match(namespace))


def is_provider_well_formed(provider: str) -> bool:
    """True if the provider string is a plain provider name, not a path."""
    return (
        bool(provider)
        and bool(PROVIDER_PATTERN.match(provider))
        and not provider.startswith(".")
        and ".." not in provider
    )


def sanitize_namespace(namespace: str) -> str:
    """Replace any disallowed characters with hyphens, collapse runs, strip
    leading/trailing hyphens. Returns 'unnamed' if the result is empty."""
    cleaned = re.sub(r"[^a-zA-Z0-9._:-]+", "-", namespace).strip("-")
    return cleaned or "unnamed"
