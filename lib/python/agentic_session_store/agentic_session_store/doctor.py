"""Session-store doctor — preflight validation for the session-store contract.

The doctor runs at container start, before the agent starts. A failure hard
stops the workspace (ADR-036: opting into a provider is opting into loud
failure). It is also invocable on demand: `python -m
agentic_session_store.doctor [--json]`.

Output shape: pretty summary to stderr, one JSON object to stdout in
--json mode, exit 0 when every check passes (or the capability is not
opted into), exit 1 otherwise. This shape currently differs from
`agentic_memory.doctor`'s JSON payload (memory predates this shape and
has not been reconciled to it): the only field guaranteed common to
both is `capability`, so an audit-log reader can attribute a record but
must not assume a shared schema beyond that.

Every env var name this module touches comes from `Env` in contract.py.
Nothing here may spell one as a string literal.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

from agentic_session_store.contract import (
    CAPABILITY,
    Env,
    SessionStoreContract,
    init_marker_path,
)

EXPORTER_BINARY = "SeshMagicSessionExporter"
"""Name of the exporter binary this capability expects on PATH."""

STORE_HEALTH_TIMEOUT_SECONDS = 5
"""How long to wait for GET $URL/healthz before giving up."""

EXPORTER_VERSION_TIMEOUT_SECONDS = 5
"""How long to wait for `<exporter> --version` before giving up."""

CLAUDE_PROJECTS_DIR = os.path.expanduser("~/.claude/projects")
CODEX_SESSIONS_DIR = os.path.expanduser("~/.codex/sessions")


@dataclass
class CheckResult:
    """The outcome of a single check."""

    name: str
    passed: bool
    detail: str = ""


def _contract_parses(contract: SessionStoreContract) -> CheckResult:
    # By the time we get here contract is a validated SessionStoreContract
    # instance (from_env already raised on misconfiguration), so this check
    # exists to record that fact in the audit log, not to re-derive it.
    return CheckResult(
        name="contract_parses",
        passed=True,
        detail=f"provider={contract.provider} partition={contract.partition}",
    )


INIT_MARKER_READ_BYTES = 4096
"""How much of the marker to read. It holds one short token and a newline."""


def _init_complete(contract: SessionStoreContract) -> CheckResult:
    """Fail unless THIS run's init.sh reached its last line.

    WHY A DOCTOR NEEDS THIS AT ALL. entrypoint.sh 5.6 sources each adapter's
    init.sh as the condition of an `if` and, on failure, warns and carries on
    in the belief that this doctor will name the cause. That belief was never
    verified, and it is not free-standing: it holds only for the failures the
    other checks happen to observe. Everything init.sh does that no other
    check looks at (writing `.capture-env`, for one) could fail with every
    other check still green.

    WHY A TOKEN AND NOT JUST A FILE. The spool outlives the container, on
    purpose. A marker that only had to EXIST would be satisfied by the one a
    previous run left behind, so a run whose init died before writing
    anything would pass on its predecessor's word, which is the same
    stale-state failure this check exists to remove, one layer up. So the
    marker carries the value of Env.INIT_TOKEN, which init.sh mints fresh
    (and exports) at its first line, and this compares the two. A marker from
    any other run holds another run's token and fails here.

    WHAT THIS DOES NOT PROVE: that the marker was written by the adapter.
    Anything that can write inside the reserved namespace can write this file
    too, and it would have to know this run's token to write a passing one.
    That is not a boundary this check defends; the namespace's ownership
    marker is what governs who writes there.
    """
    marker = init_marker_path(contract.spool, contract.partition)
    token = os.environ.get(Env.INIT_TOKEN, "").strip()
    if not token:
        return CheckResult(
            name="init_complete",
            passed=False,
            detail=(
                f"{Env.INIT_TOKEN} is unset, so the {contract.provider} adapter's "
                "init.sh never ran or died before its first line. Look for "
                f"[{CAPABILITY}] messages earlier in the container's stderr."
            ),
        )
    try:
        with open(marker, encoding="utf-8", errors="replace") as handle:
            recorded = handle.read(INIT_MARKER_READ_BYTES).strip()
    except OSError as e:
        return CheckResult(
            name="init_complete",
            passed=False,
            detail=(
                f"{marker} is absent or unreadable ({e}), so the "
                f"{contract.provider} adapter's init.sh did not finish: it writes "
                "that file as its last act. The workspace would run with whatever "
                "spool layout and correlation tags a previous run left behind. Look "
                f"for [{CAPABILITY}] messages earlier in the container's stderr."
            ),
        )
    if recorded != token:
        return CheckResult(
            name="init_complete",
            passed=False,
            detail=(
                f"{marker} records a DIFFERENT run's token, so it was left by an "
                f"earlier container and the {contract.provider} adapter's init.sh "
                "did not finish this time. The spool outlives the container, so a "
                "stale marker is expected here; what is not expected is this run "
                "failing to replace it. Look for "
                f"[{CAPABILITY}] messages earlier in the container's stderr."
            ),
        )
    return CheckResult(name="init_complete", passed=True, detail=marker)


def _spool_writable(contract: SessionStoreContract) -> CheckResult:
    target = os.path.join(contract.spool, contract.partition)
    try:
        os.makedirs(target, exist_ok=True)
        # The probe is written into the TRANSCRIPT partition, because that is
        # the directory whose writability is in question, and the operator may
        # own it. So it is created with O_EXCL under a name unique to this
        # process: a fixed name opened "w" would truncate and then DELETE a
        # file of the operator's that happened to share it, which is the same
        # class of defect as the adapter's unnamespaced metadata writes. O_EXCL
        # cannot open an existing file at all, so the only file this ever
        # removes is one it just created.
        probe = os.path.join(target, f".doctor-write-probe.{os.getpid()}")
        fd = os.open(probe, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, b"")
        finally:
            os.close(fd)
        os.remove(probe)
    except (OSError, ValueError) as e:
        return CheckResult(
            name="spool_writable",
            passed=False,
            detail=f"{target} is not writable: {e}",
        )
    return CheckResult(name="spool_writable", passed=True, detail=target)


def _resolves_to(link_path: str, expected_dir: str) -> tuple[bool, str]:
    if not os.path.exists(link_path):
        return False, f"{link_path} does not exist"
    resolved = os.path.realpath(link_path)
    expected = os.path.realpath(expected_dir)
    if resolved != expected:
        return False, f"{link_path} resolves to {resolved}, expected {expected}"
    return True, f"{link_path} -> {resolved}"


def _symlinks_correct(contract: SessionStoreContract) -> CheckResult:
    # The adapter's spool layout (ADR-040) is $SPOOL/$PARTITION/{claude,codex}
    # — two distinct subdirectories, not a single shared partition root. See
    # the seshmagic adapter's init.sh, which symlinks each harness's
    # transcript root to its own subdirectory.
    partition_dir = os.path.join(contract.spool, contract.partition)
    claude_dir = os.path.join(partition_dir, "claude")
    codex_dir = os.path.join(partition_dir, "codex")
    claude_ok, claude_detail = _resolves_to(CLAUDE_PROJECTS_DIR, claude_dir)
    codex_ok, codex_detail = _resolves_to(CODEX_SESSIONS_DIR, codex_dir)
    passed = claude_ok and codex_ok
    detail = f"claude: {claude_detail}; codex: {codex_detail}"
    return CheckResult(name="symlinks_correct", passed=passed, detail=detail)


def _exporter_present(contract: SessionStoreContract) -> CheckResult:
    path = shutil.which(EXPORTER_BINARY)
    if not path:
        return CheckResult(
            name="exporter_present",
            passed=False,
            detail=f"{EXPORTER_BINARY} not found on PATH",
        )
    try:
        import subprocess

        result = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=EXPORTER_VERSION_TIMEOUT_SECONDS,
            check=False,
        )
    except Exception as e:  # noqa: BLE001 - a doctor must not crash
        return CheckResult(
            name="exporter_present",
            passed=False,
            detail=f"{path} --version raised: {e}",
        )
    if result.returncode != 0:
        return CheckResult(
            name="exporter_present",
            passed=False,
            detail=f"{path} --version exited {result.returncode}",
        )
    return CheckResult(name="exporter_present", passed=True, detail=path)


# --- Credential-safe HTTP -----------------------------------------------------
#
# DUPLICATED, DELIBERATELY. The same three definitions exist in
# agentic_memory/doctor.py, as `_origin`, `SameOriginRedirect` and
# `SAME_ORIGIN_OPENER`. The two packages ship as separate wheels with
# `dependencies = []` and neither imports the other, so there is no module
# either one can import today; the only shared home would be a fourth
# distribution, which means a new wheel in scripts/build-provider.py, a new
# entry in scripts/python_qa.py and the CI matrix, and a dependency edge in
# two images, for one class and one function. That cost was judged not worth
# paying for this fix.
#
# The cost of NOT paying it is drift, which is exactly what happened here:
# this guard was written for this doctor and scoped to this doctor, so the
# memory doctor sent AGENTIC_MEMORY_AUTH through the stock redirect handler
# for as long as this comment did not exist. So each copy names the other.
# If you change one, change both.


def _origin(url: str) -> tuple[str, str, int | None]:
    """The (scheme, host, port) triple two URLs must share to be same-origin.

    Scheme and host are lowercased by urlsplit already; the port is taken
    from `port`, which returns None when the URL relies on the scheme
    default, so `https://h` and `https://h:443` compare equal only after the
    default is filled in below.
    """
    parsed = urllib.parse.urlsplit(url)
    default_ports = {"http": 80, "https": 443}
    port = parsed.port if parsed.port is not None else default_ports.get(parsed.scheme)
    return (parsed.scheme, parsed.hostname or "", port)


class _SameOriginRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect handler that follows same-origin hops and nothing else.

    `urllib.request.urlopen` follows redirects by default, and the stock
    HTTPRedirectHandler copies the ORIGINAL request's headers onto the
    redirected one, `Authorization` included, WITHOUT checking that the new
    URL is even the same host. Verified directly:

        HTTPRedirectHandler().redirect_request(
            req_to_a.example, None, 302, "Found", {}, "http://evil.example/y")
        -> redirected headers: {'Authorization': 'Bearer SECRET'}

    So a store that is compromised, misconfigured, or merely sitting behind a
    redirecting proxy harvests the write credential from a health check.

    REFUSING EVERY REDIRECT OVER-CORRECTS. A store that canonicalises
    `/healthz` to `/healthz/` is an ordinary deployment, and refusing that
    fails preflight and blocks the workspace from starting for a store that
    is perfectly healthy. The property that actually matters is narrower: the
    credential must never reach a DIFFERENT origin.

    So a hop to the same (scheme, host, port) is followed, and any other hop
    is declined. The comparison is made PER HOP, against `req.full_url`,
    which is the URL of the request being answered rather than the one the
    operator configured: on `A -> A -> evil`, the second hop compares evil
    against A and stops there. Declining returns None, which leaves the 3xx to
    HTTPDefaultErrorHandler and surfaces as an HTTPError carrying the real
    status code, so a cross-origin redirect is a FAILED check rather than
    something silently passed. urllib resolves a relative Location against the
    current request before calling this, so a relative hop is same-origin by
    construction.

    urllib's own redirect limits (max_repeats, max_redirections) still apply,
    so a same-origin redirect loop terminates rather than spinning.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if _origin(req.full_url) != _origin(newurl):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_SAME_ORIGIN_OPENER = urllib.request.build_opener(_SameOriginRedirect)
"""Opener used for every credential-bearing request this doctor makes.

`build_opener` skips its default HTTPRedirectHandler when handed a subclass
of it, so this opener has exactly one redirect handler and it is this one.
"""


def _store_reachable(contract: SessionStoreContract) -> CheckResult:
    health_url = contract.url.rstrip("/") + "/healthz"
    parsed = urllib.parse.urlparse(health_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return CheckResult(
            name="store_reachable",
            passed=False,
            detail=f"{health_url} is not a valid http(s) URL (missing scheme or host)",
        )
    try:
        req = urllib.request.Request(health_url, method="GET")
        if contract.auth:
            req.add_header("Authorization", f"Bearer {contract.auth}")
        with _SAME_ORIGIN_OPENER.open(
            req, timeout=STORE_HEALTH_TIMEOUT_SECONDS
        ) as resp:
            status_code = resp.status
    except urllib.error.HTTPError as e:
        if 300 <= e.code < 400:
            # The redirect target is deliberately NOT echoed. It is
            # attacker-controllable input on exactly the path this check
            # exists to refuse, and this string is appended to the durable
            # doctor audit file.
            return CheckResult(
                name="store_reachable",
                passed=False,
                detail=(
                    f"{health_url} returned HTTP {e.code} (a redirect to a "
                    "DIFFERENT origin, which is NOT followed: the store "
                    "credential may only ever be sent to the configured scheme, "
                    "host and port. A same-origin redirect is followed and is "
                    "not reported here). Point the URL at the store directly."
                ),
            )
        return CheckResult(
            name="store_reachable",
            passed=False,
            detail=f"{health_url} returned HTTP {e.code}",
        )
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        return CheckResult(
            name="store_reachable",
            passed=False,
            detail=f"{health_url} unreachable: {e}",
        )
    if status_code != 200:
        return CheckResult(
            name="store_reachable",
            passed=False,
            detail=f"{health_url} returned status {status_code}",
        )
    return CheckResult(
        name="store_reachable", passed=True, detail=f"{health_url} -> 200"
    )


CHECKS: list[tuple[str, Callable[[SessionStoreContract], CheckResult]]] = [
    ("contract_parses", _contract_parses),
    ("init_complete", _init_complete),
    ("spool_writable", _spool_writable),
    ("symlinks_correct", _symlinks_correct),
    ("exporter_present", _exporter_present),
    ("store_reachable", _store_reachable),
]


def run_checks(contract: SessionStoreContract) -> list[CheckResult]:
    """Run every check in CHECKS against a validated contract, in order.

    All of them always run, even after an earlier one fails or raises, so a
    single invocation gives the operator the full picture. Each check is
    called through this outer guard: a check that raises (a malformed URL,
    an embedded null byte in a path, anything unanticipated) is converted
    into a failed CheckResult rather than propagating and killing the rest
    along with it. Individual checks additionally catch their
    own expected failure modes so the detail string is specific rather than
    a generic "raised: ..." message.
    """
    results: list[CheckResult] = []
    for name, check in CHECKS:
        try:
            results.append(check(contract))
        except Exception as e:  # noqa: BLE001 - a doctor must not crash
            results.append(
                CheckResult(
                    name=name,
                    passed=False,
                    detail=f"check raised {type(e).__name__}: {e}",
                )
            )
    return results


CONTRACT_FAILURE_DETAIL = "not run: the contract did not parse"
"""Detail recorded for the checks a malformed contract never reaches."""


def _contract_failure_results(message: str) -> list[CheckResult]:
    """Build the full result list for a contract that would not parse.

    The list is the SAME length and order as a normal run: contract_parses
    carries the parser's own message, and the others are reported as
    failed-but-not-run rather than omitted. An audit-log reader then parses
    one schema instead of two, and `passed: false` on a check that never
    executed is honest -- nothing about the adapter's completion, the spool,
    symlinks, exporter, or store was verified.
    """
    return [
        CheckResult(
            name=name,
            passed=False,
            detail=message if name == "contract_parses" else CONTRACT_FAILURE_DETAIL,
        )
        for name, _ in CHECKS
    ]


def _format_pretty(
    contract: SessionStoreContract | None, results: list[CheckResult]
) -> str:
    if contract is None:
        return f"[{CAPABILITY}-doctor] {Env.PROVIDER} unset — not opted in. No checks run.\n"

    lines: list[str] = []
    lines.append(f"[{CAPABILITY}-doctor] Session-store contract diagnostics")
    lines.append(f"  provider:  {contract.provider}")
    lines.append(f"  url:       {contract.url}")
    lines.append(f"  partition: {contract.partition}")
    lines.append("")
    lines.extend(_format_check_lines(results))
    return "\n".join(lines) + "\n"


def _format_check_lines(results: list[CheckResult]) -> list[str]:
    lines = [f"  Checks ({len(results)}):"]
    for r in results:
        marker = "  OK" if r.passed else "FAIL"
        lines.append(f"    [{marker}] {r.name:<20} {r.detail}")
    lines.append("")
    fail_count = sum(1 for r in results if not r.passed)
    if fail_count == 0:
        lines.append("  All checks passed.")
    else:
        lines.append(f"  {fail_count} check(s) failed.")
    return lines


def _format_contract_failure(message: str, results: list[CheckResult]) -> str:
    lines = [
        f"[{CAPABILITY}-doctor] Session-store contract did NOT parse",
        f"  {message}",
        "",
    ]
    lines.extend(_format_check_lines(results))
    return "\n".join(lines) + "\n"


def _emit(results: list[CheckResult], pretty: str, as_json: bool) -> int:
    """Write the pretty summary to stderr, the JSON object to stdout, return the code.

    Single exit path for every outcome that ran at all, so a malformed
    contract and a failed check produce byte-compatible JSON shapes.
    """
    passed = all(r.passed for r in results)

    sys.stderr.write(pretty)
    sys.stderr.flush()

    if as_json:
        payload = {
            "capability": CAPABILITY,
            "passed": passed,
            "checks": [
                {"name": r.name, "passed": r.passed, "detail": r.detail}
                for r in results
            ],
        }
        sys.stdout.write(json.dumps(payload) + "\n")
        sys.stdout.flush()

    return 0 if passed else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="agentic-session-store-doctor",
        description="Validate the workspace's session-store contract.",
    )
    p.add_argument(
        "--json", action="store_true", help="JSON to stdout (pretty stays on stderr)"
    )
    args = p.parse_args(argv)

    # A MALFORMED CONTRACT IS A DOCTOR RESULT, NOT A CRASH.
    #
    # entrypoint.sh 5.7 runs this with --json and appends stdout to an audit
    # log. An uncaught exception prints a traceback to stderr and writes ZERO
    # bytes to that log, which is indistinguishable from "the doctor never
    # ran" -- the one thing a preflight tool must never be ambiguous about.
    #
    # ValueError is the complete set, verified by reading contract.py rather
    # than assumed: every failure path in `from_env` is an explicit `raise
    # ValueError` (bad provider name, missing URL, bad spool, missing or bad
    # partition), and the only other operations it performs are `Mapping.get`
    # with `Env` keys, `str.strip`, `str.split`, and a match against a
    # precompiled pattern, none of which raise on a `str` value out of
    # `os.environ`. So this deliberately does NOT catch bare `Exception` the
    # way run_checks does: any other exception type escaping from_env is a
    # bug in this package, and swallowing it into a tidy JSON object would
    # hide it. Loud is correct there; this handler covers the configuration
    # errors that are the operator's to fix.
    try:
        contract = SessionStoreContract.from_env(os.environ)
    except ValueError as e:
        message = str(e)
        results = _contract_failure_results(message)
        return _emit(results, _format_contract_failure(message, results), args.json)

    if contract is None:
        # Not opted into; doctor is a no-op. Print nothing, exit 0. There is
        # nothing to audit: the workspace did not ask for this capability.
        return 0

    results = run_checks(contract)
    return _emit(results, _format_pretty(contract, results), args.json)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
