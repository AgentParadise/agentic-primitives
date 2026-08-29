"""Unit tests for agentic_memory.doctor.

Network checks (backend_dns, backend_health) use a hostname that's
guaranteed not to resolve, so no real network call escapes the test.
"""

from __future__ import annotations

import http.server
import json
import pathlib
import stat
import threading
import urllib.request
from typing import ClassVar

from agentic_memory.contract import (
    CAPABILITY,
    Env,
    MemoryContract,
    init_marker_path,
)
from agentic_memory.doctor import (
    AdapterExistsCheck,
    BackendDnsCheck,
    BackendHealthCheck,
    CheckStatus,
    ConfigJsonValidCheck,
    EnvContractCheck,
    InitCompleteCheck,
    NamespaceWellFormedCheck,
    ProviderKnownCheck,
    ProviderSpecificCheck,
    main,
    run_checks,
)

# --- contract fixtures --------------------------------------------------------


def _contract(overrides: dict[Env, str] | None = None) -> MemoryContract:
    """Build a contract from a base env, overridden by `Env`-keyed entries.

    Deliberately takes a dict (not **kwargs): a kwarg name is a bare Python
    identifier, so `_contract({Env.NAMESPACE: ""})` would spell the
    env var name as a literal outside `Env` — exactly what the literal
    guard in test_contract.py exists to prevent, and kwarg syntax evades
    its regex entirely. Callers pass `_contract({Env.NAMESPACE: ""})`.
    """
    base = {
        Env.PROVIDER: "hindsight",
        Env.NAMESPACE: "task-abc",
        Env.URL: "http://nonexistent.invalid.example:9999",
    }
    base.update(overrides or {})
    return MemoryContract.from_env(base)


# --- individual check tests ---------------------------------------------------


class TestEnvContractCheck:
    def test_passes_when_all_set(self):
        r = EnvContractCheck().run(_contract())
        assert r.status == CheckStatus.OK

    def test_fails_when_namespace_missing(self):
        r = EnvContractCheck().run(_contract({Env.NAMESPACE: ""}))
        assert r.status == CheckStatus.FAIL
        assert Env.NAMESPACE in r.details["missing"]

    def test_fails_when_url_missing(self):
        r = EnvContractCheck().run(_contract({Env.URL: ""}))
        assert r.status == CheckStatus.FAIL
        assert Env.URL in r.details["missing"]


class TestNamespaceWellFormedCheck:
    def test_passes_on_clean_namespace(self):
        r = NamespaceWellFormedCheck().run(_contract())
        assert r.status == CheckStatus.OK

    def test_fails_with_spaces(self):
        r = NamespaceWellFormedCheck().run(_contract({Env.NAMESPACE: "bad namespace"}))
        assert r.status == CheckStatus.FAIL
        assert r.details["suggested"] == "bad-namespace"

    def test_skips_when_empty(self):
        r = NamespaceWellFormedCheck().run(_contract({Env.NAMESPACE: ""}))
        assert r.status == CheckStatus.SKIPPED


class TestProviderKnownCheck:
    def test_passes_when_dir_exists(self, tmp_path):
        (tmp_path / "hindsight").mkdir()
        r = ProviderKnownCheck(registry_root=str(tmp_path)).run(_contract())
        assert r.status == CheckStatus.OK

    def test_fails_when_dir_missing(self, tmp_path):
        r = ProviderKnownCheck(registry_root=str(tmp_path)).run(_contract())
        assert r.status == CheckStatus.FAIL
        assert r.details["known_providers"] == []

    def test_lists_known_providers_on_failure(self, tmp_path):
        (tmp_path / "lossless-claw").mkdir()
        r = ProviderKnownCheck(registry_root=str(tmp_path)).run(_contract())
        assert r.status == CheckStatus.FAIL
        assert "lossless-claw" in r.details["known_providers"]

    def test_rejects_provider_path_traversal(self, tmp_path):
        r = ProviderKnownCheck(registry_root=str(tmp_path)).run(
            _contract({Env.PROVIDER: "../evil"})
        )
        assert r.status == CheckStatus.FAIL
        assert "provider name" in r.message


class TestAdapterExistsCheck:
    def test_passes_when_init_sh_is_executable(self, tmp_path):
        adapter = tmp_path / "hindsight" / "init.sh"
        adapter.parent.mkdir()
        adapter.write_text("#!/bin/sh\nexit 0\n")
        adapter.chmod(adapter.stat().st_mode | stat.S_IXUSR)

        r = AdapterExistsCheck(registry_root=str(tmp_path)).run(_contract())
        assert r.status == CheckStatus.OK

    def test_fails_when_init_sh_missing(self, tmp_path):
        (tmp_path / "hindsight").mkdir()
        r = AdapterExistsCheck(registry_root=str(tmp_path)).run(_contract())
        assert r.status == CheckStatus.FAIL
        assert "missing" in r.message.lower()

    def test_fails_when_init_sh_not_executable(self, tmp_path):
        adapter = tmp_path / "hindsight" / "init.sh"
        adapter.parent.mkdir()
        adapter.write_text("#!/bin/sh\n")
        # Make it explicitly non-executable
        adapter.chmod(0o644)

        r = AdapterExistsCheck(registry_root=str(tmp_path)).run(_contract())
        assert r.status == CheckStatus.FAIL
        assert "not executable" in r.message.lower()

    def test_rejects_provider_path_traversal(self, tmp_path):
        escaped = tmp_path.parent / f"evil-{tmp_path.name}"
        escaped.mkdir()
        try:
            adapter = escaped / "init.sh"
            adapter.write_text("#!/bin/sh\nexit 0\n")
            adapter.chmod(0o755)

            r = AdapterExistsCheck(registry_root=str(tmp_path)).run(
                _contract({Env.PROVIDER: "../evil"})
            )
            assert r.status == CheckStatus.FAIL
            assert "provider name" in r.message
        finally:
            adapter.unlink(missing_ok=True)
            escaped.rmdir()


class TestConfigJsonValidCheck:
    def test_skips_when_unset(self):
        r = ConfigJsonValidCheck().run(_contract())
        assert r.status == CheckStatus.SKIPPED

    def test_passes_on_valid_json_object(self):
        r = ConfigJsonValidCheck().run(_contract({Env.CONFIG_JSON: '{"key": "value"}'}))
        assert r.status == CheckStatus.OK
        assert r.details["keys"] == ["key"]

    def test_fails_on_invalid_json(self):
        r = ConfigJsonValidCheck().run(_contract({Env.CONFIG_JSON: "{not valid"}))
        assert r.status == CheckStatus.FAIL

    def test_fails_when_json_not_object(self):
        r = ConfigJsonValidCheck().run(_contract({Env.CONFIG_JSON: "[1, 2, 3]"}))
        assert r.status == CheckStatus.FAIL
        assert "object" in r.message.lower()


class TestBackendDnsCheck:
    def test_fails_for_unresolvable_host(self):
        r = BackendDnsCheck().run(_contract())
        # nonexistent.invalid.example shouldn't resolve
        assert r.status == CheckStatus.FAIL

    def test_skips_when_url_missing(self):
        r = BackendDnsCheck().run(_contract({Env.URL: ""}))
        assert r.status == CheckStatus.SKIPPED


class TestBackendHealthCheck:
    def test_fails_for_unreachable_backend(self):
        # Same unreachable host — verifies error handling, not the wire protocol.
        r = BackendHealthCheck(timeout=2).run(_contract())
        assert r.status == CheckStatus.FAIL

    def test_skips_when_url_missing(self):
        r = BackendHealthCheck().run(_contract({Env.URL: ""}))
        assert r.status == CheckStatus.SKIPPED

    def test_rejects_non_http_url_before_opening(self):
        r = BackendHealthCheck().run(_contract({Env.URL: "file:///etc/passwd"}))
        assert r.status == CheckStatus.FAIL
        assert "http or https" in r.message


class TestInitCompleteCheck:
    """A failed init must not look like a successful one.

    entrypoint.sh 5.6 sources init.sh as the condition of an `if` and, on
    failure, warns and carries on because "the doctor in 5.7 will surface
    the cause". That holds only for the failures some other check happens
    to observe: with a read-only ~/.hindsight the adapter's config write
    fails, and config_json_valid, backend_health and the provider's own
    doctor.sh are all still green. These pin the check that closes it.
    """

    def _marker(self, tmp_path, token):
        marker = pathlib.Path(init_marker_path(str(tmp_path)))
        marker.write_text(f"{token}\n")
        return marker

    def test_passes_when_the_marker_holds_this_runs_token(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv(Env.INIT_TOKEN, "token-for-this-run")
        self._marker(tmp_path, "token-for-this-run")

        r = InitCompleteCheck().run(_contract())
        assert r.status == CheckStatus.OK, r.message

    def test_fails_when_the_marker_is_absent(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv(Env.INIT_TOKEN, "token-for-this-run")

        r = InitCompleteCheck().run(_contract())
        assert r.status == CheckStatus.FAIL
        assert "did not finish" in r.message

    def test_fails_on_a_marker_left_by_a_previous_run(self, tmp_path, monkeypatch):
        """THE hazard: $HOME can be persisted across containers."""
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv(Env.INIT_TOKEN, "token-for-this-run")
        self._marker(tmp_path, "token-from-the-container-before-this-one")

        r = InitCompleteCheck().run(_contract())
        assert r.status == CheckStatus.FAIL
        assert "DIFFERENT run's token" in r.message

    def test_fails_when_no_token_was_minted(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv(Env.INIT_TOKEN, raising=False)
        self._marker(tmp_path, "some-token")

        r = InitCompleteCheck().run(_contract())
        assert r.status == CheckStatus.FAIL
        assert str(Env.INIT_TOKEN) in r.message

    def test_does_not_raise_on_an_unreadable_marker(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv(Env.INIT_TOKEN, "token-for-this-run")
        pathlib.Path(init_marker_path(str(tmp_path))).mkdir()

        r = InitCompleteCheck().run(_contract())
        assert r.status == CheckStatus.FAIL
        assert "absent or unreadable" in r.message


class TestProviderSpecificCheck:
    def test_skips_when_no_doctor_sh(self, tmp_path):
        (tmp_path / "hindsight").mkdir()
        r = ProviderSpecificCheck(registry_root=str(tmp_path)).run(_contract())
        assert r.status == CheckStatus.SKIPPED

    def test_passes_when_script_exits_zero(self, tmp_path):
        adapter = tmp_path / "hindsight"
        adapter.mkdir()
        script = adapter / "doctor.sh"
        script.write_text("#!/bin/sh\necho '{\"ok\": true}'\nexit 0\n")
        script.chmod(0o755)

        r = ProviderSpecificCheck(registry_root=str(tmp_path)).run(_contract())
        assert r.status == CheckStatus.OK
        assert r.details.get("ok") is True

    def test_fails_when_script_exits_nonzero(self, tmp_path):
        adapter = tmp_path / "hindsight"
        adapter.mkdir()
        script = adapter / "doctor.sh"
        script.write_text('#!/bin/sh\necho "bad config" >&2\nexit 1\n')
        script.chmod(0o755)

        r = ProviderSpecificCheck(registry_root=str(tmp_path)).run(_contract())
        assert r.status == CheckStatus.FAIL

    def test_rejects_provider_path_traversal_without_executing(self, tmp_path):
        escaped = tmp_path.parent / f"evil-{tmp_path.name}"
        marker = tmp_path / "executed"
        escaped.mkdir()
        try:
            script = escaped / "doctor.sh"
            script.write_text(f"#!/bin/sh\ntouch {marker}\nexit 0\n")
            script.chmod(0o755)

            r = ProviderSpecificCheck(registry_root=str(tmp_path)).run(
                _contract({Env.PROVIDER: "../evil"})
            )
            assert r.status == CheckStatus.FAIL
            assert "provider name" in r.message
            assert not marker.exists()
        finally:
            script.unlink(missing_ok=True)
            escaped.rmdir()


# --- runner tests -------------------------------------------------------------


class TestRunChecks:
    def test_no_contract_is_noop(self):
        results, exit_code = run_checks(None)
        assert results == []
        assert exit_code == 0

    def test_failing_checks_produce_exit_1(self):
        # Real contract pointing at an unresolvable backend produces multiple FAILs.
        results, exit_code = run_checks(_contract())
        assert exit_code == 1
        assert any(r.status == CheckStatus.FAIL for r in results)


# --- CLI tests ----------------------------------------------------------------


class TestCli:
    def test_main_no_provider_returns_zero(self, monkeypatch, capsys):
        monkeypatch.delenv(Env.PROVIDER, raising=False)
        exit_code = main([])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "not opted in" in captured.err

    def test_main_with_overrides_can_produce_json(self, capsys):
        exit_code = main(
            [
                "--provider",
                "definitely-not-a-provider",
                "--namespace",
                "ok",
                "--url",
                "http://nonexistent.invalid.example:9999",
                "--json",
            ]
        )
        assert exit_code == 1
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["status"] == "fail"
        assert payload["exit_code"] == 1
        assert len(payload["checks"]) == 9
        # capability attribution: with AGENTIC_CAPABILITY_AUDIT_DIR shared
        # across capabilities, this is the only field that lets a reader
        # attribute a record back to memory (see ADR-040 fix wave).
        assert payload["capability"] == CAPABILITY == "memory"
        # Pretty output still on stderr
        assert "[memory-doctor]" in captured.err

    def test_main_fix_without_apply_is_no_op_message(self, capsys):
        exit_code = main(
            [
                "--provider",
                "nope",
                "--namespace",
                "x",
                "--url",
                "http://nonexistent.invalid.example:9999",
                "--fix",
            ]
        )
        # Still exits 1 because fix doesn't change the underlying state.
        assert exit_code == 1
        captured = capsys.readouterr()
        assert (
            "dry-run" in captured.err.lower()
            or "not yet implemented" in captured.err.lower()
        )


# --- The credential must not travel to a host the operator did not configure ---
#
# These mirror the same-origin redirect tests in
# agentic_session_store/tests/test_doctor.py. The guard is duplicated in the
# two doctors (see the comment above SameOriginRedirect for why), so its
# tests are duplicated too: a guard covered by only one package's suite is
# how the guard came to exist in only one package.


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


class TestBackendHealthRedirects:
    def test_the_stock_handler_would_leak_the_credential(self):
        """Pin the upstream behaviour this guard exists to override.

        If a future Python changes `HTTPRedirectHandler` to drop
        `Authorization` on a cross-origin hop, this assertion fails and tells
        the reader the guard may be redundant. Until then it documents that
        the leak is real and is the default.
        """
        secret = "s3cr3t-memory-token"  # a test fixture, not a real credential
        req = urllib.request.Request("http://a.example/x")
        req.add_header("Authorization", f"Bearer {secret}")
        redirected = urllib.request.HTTPRedirectHandler().redirect_request(
            req, None, 302, "Found", {}, "http://evil.example/y"
        )
        assert redirected is not None
        assert secret in str(redirected.headers)

    def test_does_not_send_the_credential_across_a_cross_origin_redirect(self):
        """A redirecting backend must not be able to harvest the auth token.

        Two loopback servers stand in for the two hosts, reached under two
        different host strings (127.0.0.1 and localhost) so the hop is
        cross-origin by name as well as by port. The redirect target records
        every Authorization header it sees; it must record none, because it
        must never be contacted at all.
        """
        secret = "s3cr3t-memory-token"  # a test fixture, not a real credential

        class _Target(_RecordingHandler):
            received: ClassVar[list[str | None]] = []

        target_server, _ = _serve(_Target)
        target_port = target_server.server_port

        class _Redirector(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302)
                # A different host STRING, not just a different port.
                self.send_header("Location", f"http://localhost:{target_port}/health")
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *args):
                return

        redirect_server, redirect_url = _serve(_Redirector)
        try:
            contract = _contract({Env.URL: redirect_url, Env.AUTH: secret})
            result = BackendHealthCheck(timeout=5).run(contract)
        finally:
            redirect_server.shutdown()
            target_server.shutdown()

        assert _Target.received == [], (
            "the health check followed a cross-host redirect and sent the "
            f"memory credential to it: {_Target.received}"
        )
        assert result.status == CheckStatus.FAIL, (
            "a cross-origin redirect must be a failed check, never a pass"
        )
        assert "302" in result.message, result.message
        reported = result.message + json.dumps(result.details)
        assert secret not in reported, reported
        # The target URL is attacker-controlled input on the one path this
        # check exists to refuse, and both fields land in the audit file.
        assert str(target_port) not in reported, reported

    def test_follows_a_same_origin_redirect(self):
        """A backend that canonicalises /health to /health/ must still pass.

        Refusing EVERY redirect would over-correct: canonicalising a health
        path is an ordinary deployment, and failing preflight on it blocks
        the workspace from starting for a backend that is entirely healthy.
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
            contract = _contract({Env.URL: url, Env.AUTH: "tok"})
            result = BackendHealthCheck(timeout=5).run(contract)
        finally:
            server.shutdown()

        assert result.status == CheckStatus.OK, result.message
        assert [p for p, _ in _Canonicalising.seen] == ["/health", "/health/"]
        # The credential travelled on both hops, which is fine: same origin.
        assert [a for _, a in _Canonicalising.seen] == ["Bearer tok", "Bearer tok"]

    def test_stops_at_the_hop_that_changes_origin(self):
        """A -> A -> evil must stop at the SECOND hop.

        Comparing the new URL against the ORIGINALLY configured one would be
        enough for a single hop and useless for a chain; comparing per hop is
        what makes a same-origin first hop safe to follow.
        """

        class _Target(_RecordingHandler):
            received: ClassVar[list[str | None]] = []

        target_server, _ = _serve(_Target)
        target_port = target_server.server_port

        class _TwoHop(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/health":
                    # Same origin: this hop is legitimately followed.
                    location = "/health/"
                else:
                    # And this one is where it turns cross-origin.
                    location = f"http://localhost:{target_port}/health"
                self.send_response(302)
                self.send_header("Location", location)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *args):
                return

        hop_server, hop_url = _serve(_TwoHop)
        try:
            contract = _contract(
                # a test fixture, not a real credential
                {Env.URL: hop_url, Env.AUTH: "s3cr3t-memory-token"}
            )
            result = BackendHealthCheck(timeout=5).run(contract)
        finally:
            hop_server.shutdown()
            target_server.shutdown()

        assert _Target.received == [], (
            "the second hop changed origin and was followed anyway"
        )
        assert result.status == CheckStatus.FAIL
        assert "302" in result.message, result.message
        reported = result.message + json.dumps(result.details)
        assert str(target_port) not in reported, reported

    def test_still_passes_without_a_redirect(self):
        """The same-origin opener must not break the ordinary healthy case."""

        class _Healthy(_RecordingHandler):
            received: ClassVar[list[str | None]] = []

        server, url = _serve(_Healthy)
        try:
            contract = _contract({Env.URL: url, Env.AUTH: "tok"})
            result = BackendHealthCheck(timeout=5).run(contract)
        finally:
            server.shutdown()

        assert result.status == CheckStatus.OK, result.message
        assert _Healthy.received == ["Bearer tok"]
