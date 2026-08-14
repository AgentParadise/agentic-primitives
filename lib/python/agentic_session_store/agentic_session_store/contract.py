"""Parse the session-store capability contract from the environment.

Every env var name this capability reads is defined exactly once, in `Env`.
Nothing in this package, its doctor, or its tests may spell one as a literal:
a renamed variable must break at import, not at runtime in a container.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

CAPABILITY = "session-store"
"""This capability's registry name, as it appears in AGENTIC_CAPABILITIES."""

PROVIDER_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
DEFAULT_SPOOL = "/spool"


def capability_env_name(capability: str, field: str) -> str:
    """Build an env var name per the ADR-040 rule: AGENTIC_<CAP>_<FIELD>.

    The entrypoint derives the same name in shell (see
    `__capability_env_prefix`), so this function and that shell helper are
    the two implementations of one rule. The conformance test in
    tests/test_contract.py pins them together.
    """
    normalize = lambda part: part.upper().replace("-", "_")  # noqa: E731
    return f"AGENTIC_{normalize(capability)}_{normalize(field)}"


class Env(StrEnum):
    """Every env var the session-store capability reads. Single source of truth.

    Members are `str`, so they pass directly to `env.get()`,
    `monkeypatch.setenv()`, and f-strings without `.value`. Member NAMES are
    the field half of the ADR-040 rule, which is what the conformance test
    checks.
    """

    PROVIDER = "AGENTIC_SESSION_STORE_PROVIDER"
    URL = "AGENTIC_SESSION_STORE_URL"
    AUTH = "AGENTIC_SESSION_STORE_AUTH"
    TAGS = "AGENTIC_SESSION_STORE_TAGS"
    SPOOL = "AGENTIC_SESSION_STORE_SPOOL"
    PARTITION = "AGENTIC_SESSION_STORE_PARTITION"


class ExporterEnv(StrEnum):
    """Env vars this adapter EXPORTS for SeshMagicSessionExporter to read.

    Named here so the doctor can assert on them without restating literals.
    ORIGIN_HOST is deliberately absent: see the adapter's init.sh.
    """

    URL = "SESSION_STORE_URL"
    TOKEN = "SESSIONS_WRITE_TOKEN"
    TAGS = "SESSION_STORE_TAGS"
    CLAUDE_ROOT = "CLAUDE_PROJECTS_ROOT"
    CODEX_ROOT = "CODEX_SESSIONS_ROOT"
    STATE_FILE = "EXPORTER_STATE_FILE"


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


@dataclass(frozen=True)
class SessionStoreContract:
    """The session-store capability's slice of the workspace env contract."""

    provider: str
    url: str
    auth: str | None
    tags: str | None
    spool: str
    partition: str

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> SessionStoreContract | None:
        """Return the contract, or None when the capability is not opted into.

        Raises ValueError when opted in but misconfigured. Opting in is
        opting into loud failure (ADR-036).
        """
        provider = (_clean(env.get(Env.PROVIDER)) or "").strip()
        if not provider or provider.lower() == "none":
            return None

        if not PROVIDER_PATTERN.match(provider) or ".." in provider:
            raise ValueError(
                f"invalid {CAPABILITY} provider name: {provider!r}. "
                "Provider names map to a path under /opt/agentic/capabilities/."
            )

        url = _clean(env.get(Env.URL))
        if not url:
            raise ValueError(f"{Env.URL} is required when a provider is set")

        spool = _clean(env.get(Env.SPOOL)) or DEFAULT_SPOOL
        if not spool.startswith("/") or ".." in spool.split("/"):
            raise ValueError(
                f"invalid {CAPABILITY} spool: {spool!r}. "
                "Must be an absolute path with no '..' segment."
            )

        partition = _clean(env.get(Env.PARTITION)) or _clean(env.get("HOSTNAME"))
        if not partition:
            raise ValueError(f"{Env.PARTITION} is required when HOSTNAME is unset")
        if partition.startswith("/") or ".." in partition.split("/"):
            raise ValueError(
                f"invalid {CAPABILITY} partition: {partition!r}. "
                "Must be a relative path with no '..' segment."
            )

        return cls(
            provider=provider,
            url=url,
            auth=_clean(env.get(Env.AUTH)),
            tags=_clean(env.get(Env.TAGS)),
            spool=spool,
            partition=partition,
        )
