import http.server
import json
import subprocess
import sys
import threading
from typing import ClassVar

import agentic_session_store.doctor as doctor_module
from agentic_session_store.contract import CAPABILITY, Env, SessionStoreContract
from agentic_session_store.doctor import run_checks


def _contract(tmp_path, url="http://unreachable.invalid"):
    return SessionStoreContract(
        provider="seshmagic",
        url=url,
        auth=None,
        tags=None,
        spool=str(tmp_path),
        partition="w1/p2",
    )


def test_spool_writable_creates_partition(tmp_path):
    results = run_checks(_contract(tmp_path))
    by_name = {r.name: r for r in results}
    assert by_name["spool_writable"].passed
    assert (tmp_path / "w1" / "p2").is_dir()


def test_unreachable_store_fails_that_check_only(tmp_path):
    results = run_checks(_contract(tmp_path))
    by_name = {r.name: r for r in results}
    assert not by_name["store_reachable"].passed
    assert by_name["spool_writable"].passed


def test_json_mode_emits_parseable_object_and_exits_nonzero(tmp_path, monkeypatch):
    monkeypatch.setenv(Env.PROVIDER, "seshmagic")
    monkeypatch.setenv(Env.URL, "http://unreachable.invalid")
    monkeypatch.setenv(Env.SPOOL, str(tmp_path))
    monkeypatch.setenv(Env.PARTITION, "w1/p2")
    proc = subprocess.run(
        [sys.executable, "-m", "agentic_session_store.doctor", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload["capability"] == CAPABILITY
    assert payload["passed"] is False


def test_no_contract_is_clean_exit_zero(monkeypatch):
    monkeypatch.delenv(Env.PROVIDER, raising=False)
    proc = subprocess.run(
        [sys.executable, "-m", "agentic_session_store.doctor", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0


def test_malformed_url_is_a_contract_failure_and_still_emits_all_five(
    tmp_path, monkeypatch
):
    """A URL with no scheme must not crash the doctor or short-circuit the run.

    Regression test: `urllib.request.Request(...)` raises ValueError at
    construction for a scheme-less URL, which previously escaped
    store_reachable's except tuple and killed the whole process before any
    JSON was written.

    The origin-only URL rule now catches this earlier, at contract parse, so
    it reports as a contract failure rather than as one failed check. That is
    the same shape an audit reader parses either way, which is what this test
    exists to pin: one JSON object, five checks, exit 1, no traceback.
    """
    monkeypatch.setenv(Env.PROVIDER, "seshmagic")
    monkeypatch.setenv(Env.URL, "store-internal-host")
    monkeypatch.setenv(Env.SPOOL, str(tmp_path))
    monkeypatch.setenv(Env.PARTITION, "w1/p2")
    proc = subprocess.run(
        [sys.executable, "-m", "agentic_session_store.doctor", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
    assert proc.stdout.strip(), f"no JSON on stdout; stderr was:\n{proc.stderr}"
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload["capability"] == CAPABILITY
    assert payload["passed"] is False
    assert len(payload["checks"]) == 5
    by_name = {c["name"]: c for c in payload["checks"]}
    assert by_name["contract_parses"]["passed"] is False
    assert str(Env.URL) in by_name["contract_parses"]["detail"]
    # The other four are reported as failed-but-not-run, never omitted.
    assert by_name["store_reachable"]["passed"] is False
    assert by_name["spool_writable"]["passed"] is False
    assert doctor_module.CONTRACT_FAILURE_DETAIL == by_name["spool_writable"]["detail"]
    assert "Traceback" not in proc.stderr, proc.stderr


def test_symlinks_correct_passes_when_each_link_targets_its_own_subdir(
    tmp_path, monkeypatch
):
    """~/.claude/projects and ~/.codex/sessions must resolve to their OWN
    claude/ and codex/ subdirectories under the partition, matching the
    layout the seshmagic adapter's init.sh actually creates. Needs no
    store, no container.
    """
    partition_dir = tmp_path / "spool" / "w1" / "p2"
    claude_dir = partition_dir / "claude"
    codex_dir = partition_dir / "codex"
    claude_dir.mkdir(parents=True)
    codex_dir.mkdir(parents=True)

    claude_link = tmp_path / "home" / ".claude" / "projects"
    codex_link = tmp_path / "home" / ".codex" / "sessions"
    claude_link.parent.mkdir(parents=True)
    codex_link.parent.mkdir(parents=True)
    claude_link.symlink_to(claude_dir)
    codex_link.symlink_to(codex_dir)

    monkeypatch.setattr(doctor_module, "CLAUDE_PROJECTS_DIR", str(claude_link))
    monkeypatch.setattr(doctor_module, "CODEX_SESSIONS_DIR", str(codex_link))

    result = doctor_module._symlinks_correct(
        _contract(tmp_path / "spool", url="http://unreachable.invalid")
    )
    assert result.passed is True


def test_symlinks_correct_fails_when_both_links_point_at_the_partition_root(
    tmp_path, monkeypatch
):
    """Regression test for the shipped defect: comparing both symlinks
    against the SAME partition root (instead of each against its own
    claude/ or codex/ subdirectory) can never fail even when the layout
    is wrong in exactly this way. Both links resolving to the bare
    partition directory (not a per-harness subdirectory) must FAIL.
    """
    partition_dir = tmp_path / "spool" / "w1" / "p2"
    partition_dir.mkdir(parents=True)

    claude_link = tmp_path / "home" / ".claude" / "projects"
    codex_link = tmp_path / "home" / ".codex" / "sessions"
    claude_link.parent.mkdir(parents=True)
    codex_link.parent.mkdir(parents=True)
    claude_link.symlink_to(partition_dir)
    codex_link.symlink_to(partition_dir)

    monkeypatch.setattr(doctor_module, "CLAUDE_PROJECTS_DIR", str(claude_link))
    monkeypatch.setattr(doctor_module, "CODEX_SESSIONS_DIR", str(codex_link))

    result = doctor_module._symlinks_correct(
        _contract(tmp_path / "spool", url="http://unreachable.invalid")
    )
    assert result.passed is False


def _doctor_json(monkeypatch, **env):
    """Run the doctor as a subprocess with `env` applied, return (proc, payload).

    payload is None when stdout held no JSON, which is itself the defect
    these tests exist to catch.
    """
    for name, value in env.items():
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    proc = subprocess.run(
        [sys.executable, "-m", "agentic_session_store.doctor", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    payload = (
        json.loads(proc.stdout.strip().splitlines()[-1])
        if proc.stdout.strip()
        else None
    )
    return proc, payload


def _assert_contract_failure(proc, payload, expected_in_detail):
    """Every malformed-contract case must produce the SAME structured shape.

    The audit log at entrypoint.sh 5.7 appends this object; a traceback and
    an empty file are indistinguishable from "the doctor never ran".
    """
    assert proc.returncode == 1
    assert "Traceback" not in proc.stderr, proc.stderr
    assert payload is not None, f"no JSON on stdout; stderr was:\n{proc.stderr}"
    assert payload["capability"] == CAPABILITY
    assert payload["passed"] is False
    checks = {c["name"]: c for c in payload["checks"]}
    assert checks["contract_parses"]["passed"] is False
    assert expected_in_detail in checks["contract_parses"]["detail"]
    # Same shape as a normal run: an audit reader parses one schema, not two.
    assert len(payload["checks"]) == 5


def test_missing_url_emits_json_and_exits_1(tmp_path, monkeypatch):
    """A raising contract must become a failed structured result, not a traceback."""
    proc, payload = _doctor_json(
        monkeypatch,
        **{
            Env.PROVIDER: "seshmagic",
            Env.URL: None,  # required, so from_env raises
            Env.SPOOL: str(tmp_path),
            Env.PARTITION: "w1/p2",
        },
    )
    _assert_contract_failure(proc, payload, Env.URL)


def test_invalid_partition_emits_json_and_exits_1(tmp_path, monkeypatch):
    proc, payload = _doctor_json(
        monkeypatch,
        **{
            Env.PROVIDER: "seshmagic",
            Env.URL: "http://unreachable.invalid",
            Env.SPOOL: str(tmp_path),
            Env.PARTITION: "../escape",
        },
    )
    _assert_contract_failure(proc, payload, "partition")


def test_invalid_spool_emits_json_and_exits_1(monkeypatch):
    proc, payload = _doctor_json(
        monkeypatch,
        **{
            Env.PROVIDER: "seshmagic",
            Env.URL: "http://unreachable.invalid",
            Env.SPOOL: "not/an/absolute/path",
            Env.PARTITION: "w1/p2",
        },
    )
    _assert_contract_failure(proc, payload, "spool")


def test_run_checks_converts_a_raising_check_into_a_failed_result(
    tmp_path, monkeypatch
):
    """run_checks must never let an individual check's exception propagate."""

    def _boom(contract):
        raise ValueError("embedded \x00 null byte or some other unanticipated failure")

    monkeypatch.setattr(doctor_module, "CHECKS", [("exploding_check", _boom)])

    results = run_checks(_contract(tmp_path))

    assert len(results) == 1
    assert results[0].name == "exploding_check"
    assert results[0].passed is False
    assert "ValueError" in results[0].detail


# --- The credential must not travel to a host the operator did not configure ---


class _RecordingHandler(http.server.BaseHTTPRequestHandler):
    """Records the Authorization header of every request it receives."""

    received: ClassVar[list[str | None]] = []

    def do_GET(self):  # BaseHTTPRequestHandler's own naming
        type(self).received.append(self.headers.get("Authorization"))
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):  # silence the test output
        return


def _serve(handler_cls):
    """Start handler_cls on an ephemeral loopback port; yield its base URL."""
    server = http.server.HTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_port}"


def test_store_reachable_does_not_send_the_credential_across_a_redirect():
    """A redirecting store must not be able to harvest the write token.

    `urllib.request.urlopen` follows redirects, and the stock
    HTTPRedirectHandler copies `Authorization` onto the redirected request
    even when the target is a DIFFERENT host. So a store that is
    compromised, misconfigured, or merely behind a redirecting proxy could
    bounce this health check at any host it liked and read the credential
    out of the second request.

    Two loopback servers stand in for the two hosts, reached under two
    different host strings (127.0.0.1 and localhost) so the hop is
    cross-origin by name as well as by port. The redirect target records
    every Authorization header it sees; it must record none, because it must
    never be contacted at all.
    """
    secret = "s3cr3t-write-token"  # a test fixture, not a real credential

    class _Target(_RecordingHandler):
        received: ClassVar[list[str | None]] = []

    target_server, _ = _serve(_Target)
    target_port = target_server.server_port

    class _Redirector(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(302)
            # A different host STRING, not just a different port.
            self.send_header("Location", f"http://localhost:{target_port}/healthz")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            return

    redirect_server, redirect_url = _serve(_Redirector)
    try:
        contract = SessionStoreContract(
            provider="seshmagic",
            url=redirect_url,
            auth=secret,
            tags=None,
            spool="/spool",
            partition="w1/p2",
        )
        result = doctor_module._store_reachable(contract)
    finally:
        redirect_server.shutdown()
        target_server.shutdown()

    assert _Target.received == [], (
        "the health check followed a cross-host redirect and sent the store "
        f"credential to it: {_Target.received}"
    )
    assert result.passed is False, "a redirect must be a failed check, never a pass"
    assert "302" in result.detail, result.detail
    assert secret not in result.detail
    # The target URL is attacker-controlled input on the one path this check
    # exists to refuse, and details land in the durable audit file.
    assert str(target_port) not in result.detail, result.detail


def test_store_reachable_follows_a_same_origin_redirect():
    """A store that canonicalises /healthz to /healthz/ must still pass.

    Refusing EVERY redirect over-corrected: canonicalising a health path is
    an ordinary deployment, and failing preflight on it blocks the workspace
    from starting for a store that is entirely healthy. The property that
    matters is narrower than "no redirects": the credential must never reach
    a different origin. Same scheme, host and port is the same origin, so the
    hop is followed and the credential goes where the operator pointed it.
    """

    class _Canonicalising(http.server.BaseHTTPRequestHandler):
        seen: ClassVar[list[tuple[str, str | None]]] = []

        def do_GET(self):
            type(self).seen.append((self.path, self.headers.get("Authorization")))
            if not self.path.endswith("/"):
                self.send_response(301)
                self.send_header("Location", self.path + "/")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *args):
            return

    server, url = _serve(_Canonicalising)
    try:
        contract = SessionStoreContract(
            provider="seshmagic",
            url=url,
            auth="tok",
            tags=None,
            spool="/spool",
            partition="w1/p2",
        )
        result = doctor_module._store_reachable(contract)
    finally:
        server.shutdown()

    assert result.passed is True, result.detail
    assert [p for p, _ in _Canonicalising.seen] == ["/healthz", "/healthz/"]
    # The credential travelled on both hops, which is fine: same origin.
    assert [a for _, a in _Canonicalising.seen] == ["Bearer tok", "Bearer tok"]


def test_store_reachable_stops_at_the_hop_that_changes_origin():
    """A -> A -> evil must stop at the SECOND hop.

    Comparing the new URL against the ORIGINALLY configured one would be
    enough for a single hop and useless for a chain; comparing per hop is
    what makes a same-origin first hop safe to follow. The cross-origin
    target must never be contacted at all.
    """

    class _Target(_RecordingHandler):
        received: ClassVar[list[str | None]] = []

    target_server, _ = _serve(_Target)
    target_port = target_server.server_port

    class _TwoHop(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/healthz":
                # Same origin: this hop is legitimately followed.
                location = "/healthz/"
            else:
                # And this one is where it turns cross-origin.
                location = f"http://localhost:{target_port}/healthz"
            self.send_response(302)
            self.send_header("Location", location)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            return

    hop_server, hop_url = _serve(_TwoHop)
    try:
        contract = SessionStoreContract(
            provider="seshmagic",
            url=hop_url,
            auth="s3cr3t-write-token",  # a test fixture, not a real credential
            tags=None,
            spool="/spool",
            partition="w1/p2",
        )
        result = doctor_module._store_reachable(contract)
    finally:
        hop_server.shutdown()
        target_server.shutdown()

    assert _Target.received == [], (
        "the second hop changed origin and was followed anyway"
    )
    assert result.passed is False, "a cross-origin redirect must fail the check"
    assert "302" in result.detail, result.detail
    assert str(target_port) not in result.detail, result.detail


def test_store_reachable_still_passes_without_a_redirect():
    """The no-redirect opener must not break the ordinary healthy case."""

    class _Healthy(_RecordingHandler):
        received: ClassVar[list[str | None]] = []

    server, url = _serve(_Healthy)
    try:
        contract = SessionStoreContract(
            provider="seshmagic",
            url=url,
            auth="tok",
            tags=None,
            spool="/spool",
            partition="w1/p2",
        )
        result = doctor_module._store_reachable(contract)
    finally:
        server.shutdown()

    assert result.passed is True, result.detail
    assert _Healthy.received == ["Bearer tok"]


def test_credentialed_url_never_reaches_stderr_or_the_audit_json(tmp_path, monkeypatch):
    """A URL carrying a credential must produce the standard failure shape
    with NO credential material anywhere in the output.

    entrypoint.sh 5.7 appends this stdout to /var/agentic/<cap>-doctor/
    <date>.jsonl, which is the one artifact in the system designed to
    persist, and it echoes the pretty summary to stderr. Before the contract
    rejected these URLs, both copied the value verbatim: the doctor printed
    `url: https://user:pass@host` and the health check's detail carried the
    same string into every failed-check line.

    The schema is asserted alongside it, because the fix must not change the
    shape an audit reader parses: one object, five checks, capability set,
    passed false.
    """
    secret = "hunter2-store-write"  # a test fixture, not a real credential
    proc, payload = _doctor_json(
        monkeypatch,
        **{
            Env.PROVIDER: "seshmagic",
            Env.URL: f"https://svc:{secret}@store.example",
            Env.SPOOL: str(tmp_path),
            Env.PARTITION: "w1/p2",
        },
    )
    _assert_contract_failure(proc, payload, str(Env.URL))
    assert secret not in proc.stdout, proc.stdout
    assert secret not in proc.stderr, proc.stderr
    assert "store.example" not in proc.stdout, proc.stdout
    assert "store.example" not in proc.stderr, proc.stderr
