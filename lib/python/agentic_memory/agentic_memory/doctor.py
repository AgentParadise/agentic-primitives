"""Memory doctor — preflight validation for the memory contract.

The doctor runs at container start (entrypoint section 5.7) and is also
invocable on demand. It performs eight standard checks plus optional
provider-specific checks delegated to the adapter's `doctor.sh`.

Hard-fail on any failure. Setting `AGENTIC_MEMORY_PROVIDER` is opting into
hard-fail; there is no soft-fail mode.

See ADR-036 and the design spec.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from urllib.parse import urlparse

from agentic_memory.contract import (
    CAPABILITY,
    Env,
    MemoryContract,
    is_namespace_well_formed,
    is_provider_well_formed,
    sanitize_namespace,
)

PROVIDER_REGISTRY_ROOT = "/opt/agentic/capabilities/memory"
"""Where per-provider adapter directories live in the workspace image."""

BACKEND_HEALTH_TIMEOUT_SECONDS = 5
"""How long to wait for backend /health before giving up."""


# --- Credential-safe HTTP -----------------------------------------------------
#
# DUPLICATED, DELIBERATELY. The same three definitions exist in
# agentic_session_store/doctor.py, as `_origin`, `_SameOriginRedirect` and
# `_SAME_ORIGIN_OPENER`. The two packages ship as separate wheels with
# `dependencies = []` and neither imports the other, so there is no module
# either one can import today; the only shared home would be a fourth
# distribution, which means a new wheel in scripts/build-provider.py, a new
# entry in scripts/python_qa.py and the CI matrix, and a dependency edge in
# two images, for one class and one function. That cost was judged not worth
# paying for this fix.
#
# The cost of NOT paying it is drift, which is exactly how this defect
# reached this file: the guard was written once, in the session-store doctor,
# and scoped to that one doctor rather than to every credential-bearing
# health check. So each copy names the other. If you change one, change both.


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


class SameOriginRedirect(urllib.request.HTTPRedirectHandler):
    """A redirect handler that follows same-origin hops and nothing else.

    `urllib.request.urlopen` follows redirects by default, and the stock
    HTTPRedirectHandler copies the ORIGINAL request's headers onto the
    redirected one, `Authorization` included, WITHOUT checking that the new
    URL is even the same host. Verified directly:

        HTTPRedirectHandler().redirect_request(
            req_to_a.example, None, 302, "Found", {}, "http://evil.example/y")
        -> redirected headers: {'Authorization': 'Bearer SECRET'}

    So a backend that is compromised, misconfigured, or merely sitting behind
    a redirecting proxy harvests AGENTIC_MEMORY_AUTH from a health check.

    REFUSING EVERY REDIRECT OVER-CORRECTS. A backend that canonicalises
    `/health` to `/health/` is an ordinary deployment, and refusing that
    fails preflight and blocks the workspace from starting for a backend that
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


SAME_ORIGIN_OPENER = urllib.request.build_opener(SameOriginRedirect)
"""Opener used for every credential-bearing request this doctor makes.

`build_opener` skips its default HTTPRedirectHandler when handed a subclass
of it, so this opener has exactly one redirect handler and it is this one.
"""


class CheckStatus(str, Enum):
    OK = "ok"
    FAIL = "fail"
    SKIPPED = "skipped"


@dataclass
class CheckResult:
    """The outcome of a single check. JSON-serializable."""

    name: str
    status: CheckStatus
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class Check:
    """A single doctor check.

    Subclass and override `run(contract)`. The doctor instantiates each
    check class once and calls `run` in order.
    """

    name: str

    def run(
        self, contract: MemoryContract
    ) -> CheckResult:  # pragma: no cover - abstract
        raise NotImplementedError


# --- Standard checks ----------------------------------------------------------


class EnvContractCheck(Check):
    """Verify all required env vars are present and non-empty."""

    def __init__(self) -> None:
        super().__init__(name="env_contract")

    def run(self, contract: MemoryContract) -> CheckResult:
        missing = []
        if not contract.provider:
            missing.append(Env.PROVIDER)
        if not contract.namespace:
            missing.append(Env.NAMESPACE)
        if not contract.url:
            missing.append(Env.URL)

        if missing:
            return CheckResult(
                name=self.name,
                status=CheckStatus.FAIL,
                message=f"Missing required env vars: {', '.join(missing)}",
                details={"missing": missing},
            )
        return CheckResult(
            name=self.name,
            status=CheckStatus.OK,
            message="All required env vars set.",
        )


class NamespaceWellFormedCheck(Check):
    """Verify namespace matches the allowed character set."""

    def __init__(self) -> None:
        super().__init__(name="namespace_well_formed")

    def run(self, contract: MemoryContract) -> CheckResult:
        if not contract.namespace:
            return CheckResult(
                name=self.name,
                status=CheckStatus.SKIPPED,
                message=f"{Env.NAMESPACE} is unset (covered by env_contract).",
            )

        if is_namespace_well_formed(contract.namespace):
            return CheckResult(
                name=self.name,
                status=CheckStatus.OK,
                details={"value": contract.namespace},
            )

        sanitized = sanitize_namespace(contract.namespace)
        return CheckResult(
            name=self.name,
            status=CheckStatus.FAIL,
            message=(
                f"Namespace contains illegal characters (allowed: letters, digits, "
                f"dot, underscore, colon, hyphen). Suggested sanitization: '{sanitized}'."
            ),
            details={"value": contract.namespace, "suggested": sanitized},
        )


class ProviderKnownCheck(Check):
    """Verify the provider directory exists under /opt/agentic/capabilities/memory/."""

    def __init__(self, registry_root: str = PROVIDER_REGISTRY_ROOT) -> None:
        super().__init__(name="provider_known")
        self.registry_root = registry_root

    def run(self, contract: MemoryContract) -> CheckResult:
        if not contract.provider:
            return CheckResult(
                name=self.name,
                status=CheckStatus.SKIPPED,
                message=f"{Env.PROVIDER} unset.",
            )

        if not is_provider_well_formed(contract.provider):
            return CheckResult(
                name=self.name,
                status=CheckStatus.FAIL,
                message=f"{Env.PROVIDER} must be a provider name, not a path.",
                details={"provider": contract.provider},
            )

        provider_dir = os.path.join(self.registry_root, contract.provider)
        if not os.path.isdir(provider_dir):
            try:
                known = sorted(
                    name
                    for name in os.listdir(self.registry_root)
                    if os.path.isdir(os.path.join(self.registry_root, name))
                )
            except OSError:
                known = []
            return CheckResult(
                name=self.name,
                status=CheckStatus.FAIL,
                message=f"Provider '{contract.provider}' not found under {self.registry_root}.",
                details={"provider": contract.provider, "known_providers": known},
            )
        return CheckResult(
            name=self.name,
            status=CheckStatus.OK,
            details={"provider": contract.provider, "path": provider_dir},
        )


class AdapterExistsCheck(Check):
    """Verify init.sh exists and is executable for the provider."""

    def __init__(self, registry_root: str = PROVIDER_REGISTRY_ROOT) -> None:
        super().__init__(name="adapter_exists")
        self.registry_root = registry_root

    def run(self, contract: MemoryContract) -> CheckResult:
        if not contract.provider:
            return CheckResult(
                name=self.name,
                status=CheckStatus.SKIPPED,
                message=f"{Env.PROVIDER} unset.",
            )

        if not is_provider_well_formed(contract.provider):
            return CheckResult(
                name=self.name,
                status=CheckStatus.FAIL,
                message=f"{Env.PROVIDER} must be a provider name, not a path.",
                details={"provider": contract.provider},
            )

        adapter = os.path.join(self.registry_root, contract.provider, "init.sh")
        if not os.path.isfile(adapter):
            return CheckResult(
                name=self.name,
                status=CheckStatus.FAIL,
                message=f"Adapter init.sh missing at {adapter}",
                details={"path": adapter},
            )
        if not os.access(adapter, os.X_OK):
            return CheckResult(
                name=self.name,
                status=CheckStatus.FAIL,
                message=f"Adapter init.sh exists but is not executable at {adapter}",
                details={"path": adapter},
            )
        return CheckResult(
            name=self.name,
            status=CheckStatus.OK,
            details={"path": adapter},
        )


class ConfigJsonValidCheck(Check):
    """Verify AGENTIC_MEMORY_CONFIG_JSON parses as JSON (when set)."""

    def __init__(self) -> None:
        super().__init__(name="config_json_valid")

    def run(self, contract: MemoryContract) -> CheckResult:
        if contract.config_json is None:
            return CheckResult(
                name=self.name,
                status=CheckStatus.SKIPPED,
                message=f"{Env.CONFIG_JSON} not set.",
            )
        try:
            parsed = json.loads(contract.config_json)
        except (json.JSONDecodeError, TypeError) as e:
            return CheckResult(
                name=self.name,
                status=CheckStatus.FAIL,
                message=f"{Env.CONFIG_JSON} does not parse: {e}",
                details={"error": str(e)},
            )
        if not isinstance(parsed, dict):
            return CheckResult(
                name=self.name,
                status=CheckStatus.FAIL,
                message=f"{Env.CONFIG_JSON} must be a JSON object.",
                details={"type": type(parsed).__name__},
            )
        return CheckResult(
            name=self.name,
            status=CheckStatus.OK,
            details={"keys": sorted(parsed.keys())},
        )


class BackendDnsCheck(Check):
    """Verify the backend URL hostname resolves."""

    def __init__(self) -> None:
        super().__init__(name="backend_dns")

    def run(self, contract: MemoryContract) -> CheckResult:
        if not contract.url:
            return CheckResult(
                name=self.name,
                status=CheckStatus.SKIPPED,
                message=f"{Env.URL} unset (covered by env_contract).",
            )
        host = urlparse(contract.url).hostname
        if not host:
            return CheckResult(
                name=self.name,
                status=CheckStatus.FAIL,
                message=f"Could not parse hostname from URL: {contract.url}",
                details={"url": contract.url},
            )
        try:
            resolved = socket.gethostbyname(host)
        except socket.gaierror as e:
            return CheckResult(
                name=self.name,
                status=CheckStatus.FAIL,
                message=f"DNS lookup failed for {host}: {e}",
                details={"host": host, "error": str(e)},
            )
        return CheckResult(
            name=self.name,
            status=CheckStatus.OK,
            details={"host": host, "resolved_to": resolved},
        )


class BackendHealthCheck(Check):
    """Verify GET <url>/health returns 200."""

    def __init__(self, timeout: int = BACKEND_HEALTH_TIMEOUT_SECONDS) -> None:
        super().__init__(name="backend_health")
        self.timeout = timeout

    def run(self, contract: MemoryContract) -> CheckResult:
        if not contract.url:
            return CheckResult(
                name=self.name,
                status=CheckStatus.SKIPPED,
                message=f"{Env.URL} unset (covered by env_contract).",
            )
        parsed = urlparse(contract.url)
        if parsed.scheme not in {"http", "https"}:
            return CheckResult(
                name=self.name,
                status=CheckStatus.FAIL,
                message=f"{Env.URL} must use http or https.",
                details={"url": contract.url, "scheme": parsed.scheme},
            )
        if not parsed.hostname:
            return CheckResult(
                name=self.name,
                status=CheckStatus.FAIL,
                message=f"Could not parse hostname from URL: {contract.url}",
                details={"url": contract.url},
            )
        health_url = contract.url.rstrip("/") + "/health"

        req = urllib.request.Request(health_url, method="GET")
        if contract.auth:
            req.add_header("Authorization", f"Bearer {contract.auth}")

        start = time.monotonic()
        try:
            with SAME_ORIGIN_OPENER.open(req, timeout=self.timeout) as resp:
                status_code = resp.status
                body_preview = resp.read(200).decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            if 300 <= e.code < 400:
                # The redirect target is deliberately NOT echoed, in the
                # message or in the details. It is attacker-controllable
                # input on exactly the path this check exists to refuse, and
                # both fields land in the durable doctor audit file.
                return CheckResult(
                    name=self.name,
                    status=CheckStatus.FAIL,
                    message=(
                        f"Backend /health returned HTTP {e.code} (a redirect to "
                        "a DIFFERENT origin, which is NOT followed: the memory "
                        "credential may only ever be sent to the configured "
                        "scheme, host and port. A same-origin redirect is "
                        f"followed and is not reported here). Point {Env.URL} "
                        "at the backend directly."
                    ),
                    details={"url": health_url, "status_code": e.code},
                    duration_ms=(time.monotonic() - start) * 1000,
                )
            return CheckResult(
                name=self.name,
                status=CheckStatus.FAIL,
                message=f"Backend /health returned HTTP {e.code}",
                details={"url": health_url, "status_code": e.code},
                duration_ms=(time.monotonic() - start) * 1000,
            )
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            return CheckResult(
                name=self.name,
                status=CheckStatus.FAIL,
                message=f"Backend unreachable at {health_url}: {e}",
                details={"url": health_url, "error": str(e)},
                duration_ms=(time.monotonic() - start) * 1000,
            )
        duration_ms = (time.monotonic() - start) * 1000

        if status_code != 200:
            return CheckResult(
                name=self.name,
                status=CheckStatus.FAIL,
                message=f"Backend /health returned status {status_code}",
                details={
                    "url": health_url,
                    "status_code": status_code,
                    "body_preview": body_preview,
                },
                duration_ms=duration_ms,
            )
        return CheckResult(
            name=self.name,
            status=CheckStatus.OK,
            details={
                "url": health_url,
                "status_code": status_code,
                "response_time_ms": round(duration_ms, 1),
            },
            duration_ms=duration_ms,
        )


class ProviderSpecificCheck(Check):
    """Delegate to <provider>/doctor.sh if present.

    The doctor.sh script is invoked with the contract's env vars already set.
    It must emit JSON to stdout describing its findings and exit 0/1.
    """

    def __init__(
        self, registry_root: str = PROVIDER_REGISTRY_ROOT, timeout: int = 10
    ) -> None:
        super().__init__(name="provider_specific")
        self.registry_root = registry_root
        self.timeout = timeout

    def run(self, contract: MemoryContract) -> CheckResult:
        if not contract.provider:
            return CheckResult(
                name=self.name,
                status=CheckStatus.SKIPPED,
                message=f"{Env.PROVIDER} unset.",
            )
        if not is_provider_well_formed(contract.provider):
            return CheckResult(
                name=self.name,
                status=CheckStatus.FAIL,
                message=f"{Env.PROVIDER} must be a provider name, not a path.",
                details={"provider": contract.provider},
            )
        script = os.path.join(self.registry_root, contract.provider, "doctor.sh")
        if not os.path.isfile(script):
            return CheckResult(
                name=self.name,
                status=CheckStatus.SKIPPED,
                message=f"No provider-specific doctor.sh at {script}.",
                details={"path": script},
            )
        if not os.access(script, os.X_OK):
            return CheckResult(
                name=self.name,
                status=CheckStatus.FAIL,
                message=f"Provider doctor.sh exists but is not executable: {script}",
                details={"path": script},
            )

        start = time.monotonic()
        try:
            result = subprocess.run(
                [script],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
                env=os.environ.copy(),
            )
        except subprocess.TimeoutExpired:
            return CheckResult(
                name=self.name,
                status=CheckStatus.FAIL,
                message=f"Provider doctor.sh timed out after {self.timeout}s",
                duration_ms=self.timeout * 1000,
            )
        duration_ms = (time.monotonic() - start) * 1000

        # Parse JSON details from stdout if present; otherwise carry the raw output.
        details: dict[str, Any] = {
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
        try:
            parsed = json.loads(result.stdout)
            if isinstance(parsed, dict):
                details = parsed
        except (json.JSONDecodeError, TypeError):
            pass

        if result.returncode != 0:
            return CheckResult(
                name=self.name,
                status=CheckStatus.FAIL,
                message=f"Provider doctor.sh exit {result.returncode}",
                details=details,
                duration_ms=duration_ms,
            )
        return CheckResult(
            name=self.name,
            status=CheckStatus.OK,
            details=details,
            duration_ms=duration_ms,
        )


# --- Runner -------------------------------------------------------------------


DEFAULT_CHECKS: list[Check] = [
    EnvContractCheck(),
    NamespaceWellFormedCheck(),
    ProviderKnownCheck(),
    AdapterExistsCheck(),
    ConfigJsonValidCheck(),
    BackendDnsCheck(),
    BackendHealthCheck(),
    ProviderSpecificCheck(),
]


def run_checks(
    contract: MemoryContract | None,
    checks: list[Check] | None = None,
) -> tuple[list[CheckResult], int]:
    """Run all checks against a contract. Returns (results, exit_code).

    Exit codes:
        0 — all checks pass (no FAIL)
        1 — one or more checks failed
    """
    if contract is None:
        # Contract is not opted into; doctor is a no-op.
        return ([], 0)

    if checks is None:
        checks = DEFAULT_CHECKS

    results: list[CheckResult] = []
    for c in checks:
        start = time.monotonic()
        try:
            r = c.run(contract)
            if not r.duration_ms:
                r.duration_ms = (time.monotonic() - start) * 1000
        except Exception as e:  # noqa: BLE001
            r = CheckResult(
                name=c.name,
                status=CheckStatus.FAIL,
                message=f"Check raised: {e}",
                details={"error": str(e), "type": type(e).__name__},
                duration_ms=(time.monotonic() - start) * 1000,
            )
        results.append(r)

    exit_code = 1 if any(r.status == CheckStatus.FAIL for r in results) else 0
    return (results, exit_code)


# --- CLI ----------------------------------------------------------------------


def _redact(s: str) -> str:
    """Redact obviously-sensitive values for verbose output."""
    if not s:
        return ""
    if len(s) < 8:
        return "***"
    return s[:4] + "..." + s[-3:]


def _format_pretty(
    contract: MemoryContract | None, results: list[CheckResult], verbose: bool
) -> str:
    """Human-readable report to stderr."""
    if contract is None:
        return f"[{CAPABILITY}-doctor] {Env.PROVIDER} unset — memory not opted in. No checks run.\n"

    lines: list[str] = []
    lines.append("[memory-doctor] Memory contract diagnostics")
    lines.append(f"  provider:  {contract.provider}")
    lines.append(f"  namespace: {contract.namespace or '(unset)'}")
    lines.append(f"  url:       {contract.url or '(unset)'}")
    if verbose:
        lines.append(f"  kind:      {contract.namespace_kind.value}")
        if contract.auth:
            lines.append(f"  auth:      {_redact(contract.auth)}")
        if contract.config_json:
            lines.append(f"  config:    {len(contract.config_json)} chars")
    lines.append("")
    lines.append(f"  Checks ({len(results)}):")
    for r in results:
        marker = {
            CheckStatus.OK: "  OK",
            CheckStatus.FAIL: "FAIL",
            CheckStatus.SKIPPED: "SKIP",
        }[r.status]
        msg = r.message or ""
        lines.append(f"    [{marker}] {r.name:<28} {msg}")
        if verbose and r.details:
            for k, v in r.details.items():
                lines.append(f"             {k}: {v}")
    lines.append("")
    fail_count = sum(1 for r in results if r.status == CheckStatus.FAIL)
    if fail_count == 0:
        lines.append("  All checks passed.")
    else:
        lines.append(f"  {fail_count} check(s) failed.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="agentic-memory-doctor",
        description="Validate the workspace's memory contract.",
    )
    p.add_argument(
        "--json", action="store_true", help="JSON to stdout (pretty stays on stderr)"
    )
    p.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Include extra detail in pretty output",
    )
    p.add_argument(
        "--provider",
        help="Override AGENTIC_MEMORY_PROVIDER for this run (testing).",
    )
    p.add_argument(
        "--namespace",
        help="Override AGENTIC_MEMORY_NAMESPACE for this run (testing).",
    )
    p.add_argument(
        "--url",
        help="Override AGENTIC_MEMORY_URL for this run (testing).",
    )
    p.add_argument(
        "--fix",
        action="store_true",
        help="Apply auto-correctable fixes (dry-run unless --apply).",
    )
    p.add_argument(
        "--apply",
        action="store_true",
        help="Commit --fix changes (no-op without --fix). NOT YET IMPLEMENTED.",
    )
    args = p.parse_args(argv)

    # Apply CLI overrides into env before parsing the contract.
    env = os.environ.copy()
    if args.provider is not None:
        env[Env.PROVIDER] = args.provider
    if args.namespace is not None:
        env[Env.NAMESPACE] = args.namespace
    if args.url is not None:
        env[Env.URL] = args.url

    contract = MemoryContract.from_env(env)
    results, exit_code = run_checks(contract)

    pretty = _format_pretty(contract, results, args.verbose)
    sys.stderr.write(pretty)
    sys.stderr.flush()

    if args.json:
        payload = {
            "doctor_version": "1.0",
            "capability": CAPABILITY,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "provider": contract.provider if contract else None,
            "namespace": contract.namespace if contract else None,
            "status": "ok" if exit_code == 0 else "fail",
            "checks": [r.to_dict() for r in results],
            "exit_code": exit_code,
        }
        sys.stdout.write(json.dumps(payload) + "\n")
        sys.stdout.flush()

    if args.fix and not args.apply:
        sys.stderr.write(
            "[memory-doctor] --fix --dry-run: no changes applied (--apply not yet implemented)\n"
        )

    return exit_code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
