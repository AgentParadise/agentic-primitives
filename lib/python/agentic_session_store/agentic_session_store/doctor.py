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

from agentic_session_store.contract import CAPABILITY, Env, SessionStoreContract

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


def _spool_writable(contract: SessionStoreContract) -> CheckResult:
    target = os.path.join(contract.spool, contract.partition)
    try:
        os.makedirs(target, exist_ok=True)
        probe = os.path.join(target, ".doctor-write-probe")
        with open(probe, "w") as f:
            f.write("")
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
    # The adapter's spool layout (ADR-038) is $SPOOL/$PARTITION/{claude,codex}
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


def _exporter_present(contract: SessionStoreContract) -> CheckResult:  # noqa: ARG001
    path = shutil.which(EXPORTER_BINARY)
    if not path:
        return CheckResult(
            name="exporter_present",
            passed=False,
            detail=f"{EXPORTER_BINARY} not found on PATH",
        )
    try:
        import subprocess  # noqa: PLC0415

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
        req = urllib.request.Request(health_url, method="GET")  # noqa: S310 - controlled URL
        if contract.auth:
            req.add_header("Authorization", f"Bearer {contract.auth}")
        with urllib.request.urlopen(req, timeout=STORE_HEALTH_TIMEOUT_SECONDS) as resp:  # noqa: S310
            status_code = resp.status
    except urllib.error.HTTPError as e:
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
    return CheckResult(name="store_reachable", passed=True, detail=f"{health_url} -> 200")


CHECKS: list[tuple[str, Callable[[SessionStoreContract], CheckResult]]] = [
    ("contract_parses", _contract_parses),
    ("spool_writable", _spool_writable),
    ("symlinks_correct", _symlinks_correct),
    ("exporter_present", _exporter_present),
    ("store_reachable", _store_reachable),
]


def run_checks(contract: SessionStoreContract) -> list[CheckResult]:
    """Run all five checks against a validated contract, in order.

    All five always run, even after an earlier one fails or raises, so a
    single invocation gives the operator the full picture. Each check is
    called through this outer guard: a check that raises (a malformed URL,
    an embedded null byte in a path, anything unanticipated) is converted
    into a failed CheckResult rather than propagating and killing the other
    four checks along with it. Individual checks additionally catch their
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


def _format_pretty(contract: SessionStoreContract | None, results: list[CheckResult]) -> str:
    if contract is None:
        return f"[{CAPABILITY}-doctor] {Env.PROVIDER} unset — not opted in. No checks run.\n"

    lines: list[str] = []
    lines.append(f"[{CAPABILITY}-doctor] Session-store contract diagnostics")
    lines.append(f"  provider:  {contract.provider}")
    lines.append(f"  url:       {contract.url}")
    lines.append(f"  partition: {contract.partition}")
    lines.append("")
    lines.append(f"  Checks ({len(results)}):")
    for r in results:
        marker = "  OK" if r.passed else "FAIL"
        lines.append(f"    [{marker}] {r.name:<20} {r.detail}")
    lines.append("")
    fail_count = sum(1 for r in results if not r.passed)
    if fail_count == 0:
        lines.append("  All checks passed.")
    else:
        lines.append(f"  {fail_count} check(s) failed.")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="agentic-session-store-doctor",
        description="Validate the workspace's session-store contract.",
    )
    p.add_argument("--json", action="store_true", help="JSON to stdout (pretty stays on stderr)")
    args = p.parse_args(argv)

    contract = SessionStoreContract.from_env(os.environ)

    if contract is None:
        # Not opted into; doctor is a no-op. Print nothing, exit 0.
        return 0

    results = run_checks(contract)
    passed = all(r.passed for r in results)
    exit_code = 0 if passed else 1

    sys.stderr.write(_format_pretty(contract, results))
    sys.stderr.flush()

    if args.json:
        payload = {
            "capability": CAPABILITY,
            "passed": passed,
            "checks": [
                {"name": r.name, "passed": r.passed, "detail": r.detail} for r in results
            ],
        }
        sys.stdout.write(json.dumps(payload) + "\n")
        sys.stdout.flush()

    return exit_code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
