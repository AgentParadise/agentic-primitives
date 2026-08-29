"""Parse the session-store capability contract from the environment.

Every env var name this capability reads is defined exactly once, in `Env`.
Nothing in this package, its doctor, or its tests may spell one as a literal:
a renamed variable must break at import, not at runtime in a container.
"""

from __future__ import annotations

import os
import re
import urllib.parse
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

CAPABILITY = "session-store"
"""This capability's registry name, as it appears in AGENTIC_CAPABILITIES."""

PROVIDER_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
DEFAULT_SPOOL = "/spool"

METADATA_NAMESPACE = ".agentic-session-store"
"""The reserved directory the adapter writes its own metadata under.

Restated from the apss adapter's init.sh (`__META_ROOT`) and its
finalize.sh (`__RESERVED_SEGMENT`), which are shell and cannot import this.
The three spellings must agree; `init_marker_path` below is the only reason
this package needs the name at all.
"""

INIT_MARKER_NAME = ".init-complete"
"""Basename of the adapter's init-completion marker, inside METADATA_NAMESPACE.

Written by init.sh as its LAST act, and only once every step before it
succeeded. Read by the doctor's `init_complete` check. The file holds the
value of `Env.INIT_TOKEN` for the run that wrote it, so a marker left behind
by an earlier container does not vouch for this one.
"""


def init_marker_path(spool: str, partition: str) -> str:
    """Where this run's init-completion marker lives for a given contract.

    Same construction as the adapter's `${META_DIR}/.init-complete`: the
    reserved namespace under the spool, then the partition components, then
    the marker name.
    """
    return os.path.join(spool, METADATA_NAMESPACE, partition, INIT_MARKER_NAME)


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
    # NOT operator input. The adapter's init.sh generates a fresh value for
    # this on every run and exports it; the doctor reads it back and compares
    # it with the marker on disk. It sits in Env because the doctor READS it
    # and this enum is where every name this package reads is spelled, next to
    # the same lifecycle's AGENTIC_<CAP>_READY, which entrypoint.sh 5.6
    # exports on the same event. A value inherited from outside the container
    # cannot make a failed init look complete: init.sh overwrites it before it
    # does anything else, so the doctor never compares against a value the
    # adapter did not just mint.
    INIT_TOKEN = "AGENTIC_SESSION_STORE_INIT_TOKEN"
    # Optional operator override naming the exporter executable. The capability
    # depends on the APS-V1-0004 Exporter PROFILE, not on one client, so any
    # conformant binary under any name can be pointed at with this.
    EXPORTER_BIN = "AGENTIC_SESSION_STORE_EXPORTER_BIN"
    # OPTIONAL deployment identity (APS-V1-0004 2.0.0 `origin.deployment`):
    # WHICH deployment produced a session, as distinct from the runtime CLASS.
    # Every containerised run reports the same class, so without this a
    # multi-tier install is unattributable in a shared corpus.
    DEPLOYMENT = "AGENTIC_SESSION_STORE_DEPLOYMENT"


class ExporterEnv(StrEnum):
    """Env vars this adapter EXPORTS for the exporter to read.

    Named here so the doctor can assert on them without restating literals.
    ORIGIN_HOST is deliberately absent: see the adapter's init.sh.
    """

    URL = "SESSION_STORE_URL"
    TOKEN = "SESSIONS_WRITE_TOKEN"
    TAGS = "SESSION_STORE_TAGS"
    CLAUDE_ROOT = "CLAUDE_PROJECTS_ROOT"
    CODEX_ROOT = "CODEX_SESSIONS_ROOT"
    STATE_FILE = "EXPORTER_STATE_FILE"
    #: The exporter's own name for the deployment identity, translated from
    #: Env.DEPLOYMENT by init.sh.
    ORIGIN_DEPLOYMENT = "SESSION_STORE_ORIGIN_DEPLOYMENT"


URL_ORIGIN_ONLY_MESSAGE = (
    "must be an ORIGIN and nothing else: scheme://host[:port], with no "
    "userinfo, no path, no query and no fragment, in any encoding. Every one "
    f"of those can carry a credential. Put the store credential in {Env.AUTH}, which is "
    "never printed. The offending value is deliberately NOT echoed here, "
    "because this message reaches stderr and the durable doctor audit file."
)
"""Why a URL that is more than an origin is refused, without repeating it.

ALLOWLIST, NOT BLOCKLIST. This started as a blocklist and lost three times:
it rejected userinfo, then gained query and fragment, then a review found
`https://store.example/token/hunter2` sailing through the path, and then
`https://user%3Asecret%40store.example` sailing through a hostname that
`urlsplit` had normalised into looking clean. Each round could only name the
channel just found. Scheme, host and port is the complete set of things the
store endpoint needs, so accepting exactly that, spelled as a grammar over
the raw text, cannot be outflanked: an unanticipated URL component or
encoding is refused by default rather than carried. See AUTHORITY_PATTERN for
why the check reads raw characters rather than parser fields.

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


AUTHORITY_PATTERN = re.compile(
    r"^(?:[A-Za-z0-9._-]+|\[[0-9A-Fa-f:.]+\])(?::[0-9]{1,5})?$"
)
"""The complete grammar the RAW authority substring must match.

RAW TEXT, NOT PARSED FIELDS. The previous gate read `urlsplit()` fields, and
`urlsplit` treats a percent-encoded userinfo delimiter as ordinary reg-name
text: `https://user%3Asecret%40store.example` has a `hostname` of
`user%3asecret%40store.example`, an empty `username`, an empty `password` and
no `@` anywhere in `netloc`, so every field-based test reports a clean
origin while the value still carries a credential. Any check that runs after
a parser has normalised the text can only see what the parser chose to
expose. This one runs before, on the characters the operator actually wrote.

WHY THIS CLOSES THE CLASS. The set of allowed characters contains no `%`, so
there is no way to spell an encoded delimiter at all. `%3A`, `%3a`, `%40`,
`%2540` and `%253A` are rejected for the same single reason as `:` and `@`
in userinfo position: they are not in the grammar. Double encoding does not
help, because it adds a `%` rather than removing one, and case does not help,
because the rule never looks at what follows the `%`. A future encoding
nobody has thought of is rejected by default too, which is the property the
last four rounds of this fix did not have.

Brackets and inner colons are admitted only inside an IPv6 literal, which is
the one legitimate authority form that needs them.
"""


def _split_raw_authority(url: str) -> tuple[str, str]:
    """Return (authority, remainder) from the RAW url text, undecoded.

    The authority is everything between `://` and the first `/`, `?` or `#`,
    per RFC 3986's own delimiter set. The remainder is whatever followed it,
    so a caller can require that to be empty (or a bare `/`) and cover path,
    query and fragment with one rule instead of three.

    Raises ValueError when there is no `://` at all, which is the same
    outcome a non-http scheme gets and is checked by the caller.
    """
    marker = "://"
    index = url.find(marker)
    if index < 0:
        raise ValueError(f"{Env.URL} must use the http or https scheme")
    rest = url[index + len(marker) :]
    end = len(rest)
    for delimiter in "/?#":
        found = rest.find(delimiter)
        if found != -1:
            end = min(end, found)
    return rest[:end], rest[end:]


def _require_origin_only_url(url: str) -> None:
    """Raise unless the store URL is exactly scheme://host[:port].

    The grammar is checked on the raw text: the authority substring must
    match AUTHORITY_PATTERN before any decoding, and nothing may follow it
    except at most a single `/`. That covers userinfo, path, query and
    fragment, in every encoding, with one positive rule.

    `urlsplit` is still consulted afterwards, for the port range and for the
    handful of malformed forms it rejects outright. It is a second gate, not
    the gate.
    """
    raw_authority, remainder = _split_raw_authority(url)

    if not AUTHORITY_PATTERN.match(raw_authority):
        raise ValueError(f"{Env.URL} {URL_ORIGIN_ONLY_MESSAGE}")

    # A trailing "/" is the same origin written two ways, and rstrip'ing it is
    # what every caller does anyway. Anything else here is a path, a query or
    # a fragment, each of which has already carried a credential past an
    # earlier version of this gate.
    if remainder not in ("", "/"):
        raise ValueError(f"{Env.URL} {URL_ORIGIN_ONLY_MESSAGE}")

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
    # of the value escape into the audit file. The access exists for that
    # exception and the result is deliberately discarded, so it is assigned to
    # `_` rather than left bare: a bare attribute access reads as dead code to
    # a human and to a linter, and this line is load-bearing.
    try:
        _ = parsed.port
    except ValueError:
        raise ValueError(f"{Env.URL} has an invalid port") from None

    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"{Env.URL} must use the http or https scheme")

    if not parsed.hostname:
        raise ValueError(f"{Env.URL} must name a host")

    # Unreachable while AUTHORITY_PATTERN runs first: a value that reaches
    # here has an authority containing neither "@" nor "%" nor any character
    # outside the reg-name set, and a remainder of "" or "/". These are kept
    # deliberately, as a second gate, so that a future loosening of the
    # pattern cannot silently restore userinfo, path, query or fragment
    # without also deleting an explicit refusal of each.
    if (
        parsed.username
        or parsed.password
        or "@" in parsed.netloc
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
