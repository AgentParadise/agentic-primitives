"""Parse the session-store capability contract from the environment.

Every env var name this capability reads is defined exactly once, in `Env`.
Nothing in this package, its doctor, or its tests may spell one as a literal:
a renamed variable must break at import, not at runtime in a container.
"""

from __future__ import annotations

import re
import urllib.parse
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
    normalize = lambda part: part.upper().replace("-", "_")
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


URL_ORIGIN_ONLY_MESSAGE = (
    "must be an ORIGIN and nothing else: scheme://host[:port], with no "
    "userinfo, no path, no query and no fragment. Every one of those can "
    f"carry a credential. Put the store credential in {Env.AUTH}, which is "
    "never printed. The offending value is deliberately NOT echoed here, "
    "because this message reaches stderr and the durable doctor audit file."
)
"""Why a URL that is more than an origin is refused, without repeating it.

ALLOWLIST, NOT BLOCKLIST. This started as a blocklist and lost twice: it
rejected userinfo, then gained query and fragment, and a later review found
`https://store.example/token/hunter2` and its percent-encoded twin sailing
through the path, which no entry covered. A blocklist keeps losing that way
because each round can only name the channel just found. Scheme, host and
port is the complete set of things the store endpoint needs, so accepting
exactly that cannot be outflanked: an unanticipated URL component is refused
by default rather than carried.

The failure mode inverts too. A subpath deployment (a store behind a reverse
proxy at `/api`) now breaks loudly at preflight, before any agent work, with
a message naming the variable and the fix. The previous shape failed by
letting a credential travel silently into a durable audit file.

REJECT, NOT REDACT. The value arrives from the orchestrator as configuration
and there is exactly one supported place for the store credential, `AUTH`, so
a URL carrying one is a misconfiguration with a specific fix rather than a
shape to be tolerated. Redacting instead would keep the credential flowing
through the workspace and turn "no credential material reaches stderr or the
audit file" into an obligation on every present and future print site: the
doctor's pretty output, five check details, the JSON payload, and anything
added later. That is an invariant nobody can hold. Rejecting is one gate,
in one place, that a test can pin, and it fires at preflight before any agent
work has happened, which is where ADR-036 says a misconfigured capability
should die.

The message itself is the trap this exists to avoid, so it names no part of
the value.
"""


def _require_origin_only_url(url: str) -> None:
    """Raise unless the store URL is exactly scheme://host[:port].

    Checks the raw characters as well as the parsed fields: an empty-but-
    present fragment or query (`http://store/#`) parses to a falsy field
    while still being a URL shape this refuses to carry.
    """
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        # urlsplit raises on a few malformed forms (an unterminated IPv6
        # literal, for one). Its own message does not repeat the URL, but
        # this does not chain it: nothing about a value that may hold a
        # credential is worth forwarding into the audit file.
        raise ValueError(f"{Env.URL} could not be parsed as a URL") from None

    # `parsed.port` raises ValueError on a non-numeric or out-of-range port,
    # and that message quotes the port back; catch it rather than let a piece
    # of the value escape into the audit file.
    try:
        parsed.port
    except ValueError:
        raise ValueError(f"{Env.URL} has an invalid port") from None

    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"{Env.URL} must use the http or https scheme")

    if not parsed.hostname:
        raise ValueError(f"{Env.URL} must name a host")

    if (
        parsed.username
        or parsed.password
        or "@" in parsed.netloc
        # A trailing "/" is the same origin written two ways, and rstrip'ing
        # it is what every caller does anyway. Anything else in the path is a
        # channel that has already carried a credential past this gate.
        or parsed.path not in ("", "/")
        or "?" in url
        or "#" in url
    ):
        raise ValueError(f"{Env.URL} {URL_ORIGIN_ONLY_MESSAGE}")


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

    def __post_init__(self) -> None:
        """Enforce the URL invariant for the TYPE, not for one constructor.

        This validation used to live only in `from_env`, which made the
        invariant "a contract built one particular way carries no
        credentials" rather than "a contract carries no credentials".
        `SessionStoreContract(url="https://user:pass@store.example", ...)`
        constructed cleanly, and so would `dataclasses.replace`, a test, or
        any future caller. A frozen dataclass whose validity depends on which
        constructor was used documents a convention; it does not enforce an
        invariant.

        `__post_init__` runs on every construction path, including
        `dataclasses.replace`, so there is no permissive default path left.
        There is deliberately no unvalidated alternate constructor: nothing in
        this package needs one. If a caller ever does, it belongs here as a
        NAMED classmethod that says what it is skipping, never as a widening
        of this one.

        ValueError, the same exception type `from_env` has always raised, so
        the doctor's contract-failure handling (one JSON object, five checks,
        `contract_parses` carrying the message) is unchanged.
        """
        _require_origin_only_url(self.url)

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
        # The URL's own shape is checked by __post_init__, which every
        # construction path runs. What stays here is the one thing a
        # constructor cannot say: that the variable was missing entirely.

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
