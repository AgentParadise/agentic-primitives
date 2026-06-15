"""Unit tests for agentic_memory.doctor.

Network checks (backend_dns, backend_health) use a hostname that's
guaranteed not to resolve, so no real network call escapes the test.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from agentic_memory.contract import MemoryContract
from agentic_memory.doctor import (
    AdapterExistsCheck,
    BackendDnsCheck,
    BackendHealthCheck,
    CheckStatus,
    ConfigJsonValidCheck,
    EnvContractCheck,
    NamespaceWellFormedCheck,
    ProviderKnownCheck,
    ProviderSpecificCheck,
    main,
    run_checks,
)


# --- contract fixtures --------------------------------------------------------


def _contract(**overrides) -> MemoryContract:
    base = {
        "AGENTIC_MEMORY_PROVIDER": "hindsight",
        "AGENTIC_MEMORY_NAMESPACE": "task-abc",
        "AGENTIC_MEMORY_URL": "http://nonexistent.invalid.example:9999",
    }
    base.update({k: v for k, v in overrides.items()})
    return MemoryContract.from_env(base)


# --- individual check tests ---------------------------------------------------


class TestEnvContractCheck:
    def test_passes_when_all_set(self):
        r = EnvContractCheck().run(_contract())
        assert r.status == CheckStatus.OK

    def test_fails_when_namespace_missing(self):
        r = EnvContractCheck().run(_contract(AGENTIC_MEMORY_NAMESPACE=""))
        assert r.status == CheckStatus.FAIL
        assert "AGENTIC_MEMORY_NAMESPACE" in r.details["missing"]

    def test_fails_when_url_missing(self):
        r = EnvContractCheck().run(_contract(AGENTIC_MEMORY_URL=""))
        assert r.status == CheckStatus.FAIL
        assert "AGENTIC_MEMORY_URL" in r.details["missing"]


class TestNamespaceWellFormedCheck:
    def test_passes_on_clean_namespace(self):
        r = NamespaceWellFormedCheck().run(_contract())
        assert r.status == CheckStatus.OK

    def test_fails_with_spaces(self):
        r = NamespaceWellFormedCheck().run(_contract(AGENTIC_MEMORY_NAMESPACE="bad namespace"))
        assert r.status == CheckStatus.FAIL
        assert r.details["suggested"] == "bad-namespace"

    def test_skips_when_empty(self):
        r = NamespaceWellFormedCheck().run(_contract(AGENTIC_MEMORY_NAMESPACE=""))
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
            _contract(AGENTIC_MEMORY_PROVIDER="../evil")
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
                _contract(AGENTIC_MEMORY_PROVIDER="../evil")
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
        r = ConfigJsonValidCheck().run(_contract(AGENTIC_MEMORY_CONFIG_JSON='{"key": "value"}'))
        assert r.status == CheckStatus.OK
        assert r.details["keys"] == ["key"]

    def test_fails_on_invalid_json(self):
        r = ConfigJsonValidCheck().run(_contract(AGENTIC_MEMORY_CONFIG_JSON="{not valid"))
        assert r.status == CheckStatus.FAIL

    def test_fails_when_json_not_object(self):
        r = ConfigJsonValidCheck().run(_contract(AGENTIC_MEMORY_CONFIG_JSON='[1, 2, 3]'))
        assert r.status == CheckStatus.FAIL
        assert "object" in r.message.lower()


class TestBackendDnsCheck:
    def test_fails_for_unresolvable_host(self):
        r = BackendDnsCheck().run(_contract())
        # nonexistent.invalid.example shouldn't resolve
        assert r.status == CheckStatus.FAIL

    def test_skips_when_url_missing(self):
        r = BackendDnsCheck().run(_contract(AGENTIC_MEMORY_URL=""))
        assert r.status == CheckStatus.SKIPPED


class TestBackendHealthCheck:
    def test_fails_for_unreachable_backend(self):
        # Same unreachable host — verifies error handling, not the wire protocol.
        r = BackendHealthCheck(timeout=2).run(_contract())
        assert r.status == CheckStatus.FAIL

    def test_skips_when_url_missing(self):
        r = BackendHealthCheck().run(_contract(AGENTIC_MEMORY_URL=""))
        assert r.status == CheckStatus.SKIPPED

    def test_rejects_non_http_url_before_opening(self):
        r = BackendHealthCheck().run(_contract(AGENTIC_MEMORY_URL="file:///etc/passwd"))
        assert r.status == CheckStatus.FAIL
        assert "http or https" in r.message


class TestProviderSpecificCheck:
    def test_skips_when_no_doctor_sh(self, tmp_path):
        (tmp_path / "hindsight").mkdir()
        r = ProviderSpecificCheck(registry_root=str(tmp_path)).run(_contract())
        assert r.status == CheckStatus.SKIPPED

    def test_passes_when_script_exits_zero(self, tmp_path):
        adapter = tmp_path / "hindsight"
        adapter.mkdir()
        script = adapter / "doctor.sh"
        script.write_text('#!/bin/sh\necho \'{"ok": true}\'\nexit 0\n')
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
                _contract(AGENTIC_MEMORY_PROVIDER="../evil")
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
        monkeypatch.delenv("AGENTIC_MEMORY_PROVIDER", raising=False)
        exit_code = main([])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "not opted in" in captured.err

    def test_main_with_overrides_can_produce_json(self, capsys):
        exit_code = main(
            [
                "--provider", "definitely-not-a-provider",
                "--namespace", "ok",
                "--url", "http://nonexistent.invalid.example:9999",
                "--json",
            ]
        )
        assert exit_code == 1
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["status"] == "fail"
        assert payload["exit_code"] == 1
        assert len(payload["checks"]) == 8
        # Pretty output still on stderr
        assert "[memory-doctor]" in captured.err

    def test_main_fix_without_apply_is_no_op_message(self, capsys):
        exit_code = main(
            [
                "--provider", "nope",
                "--namespace", "x",
                "--url", "http://nonexistent.invalid.example:9999",
                "--fix",
            ]
        )
        # Still exits 1 because fix doesn't change the underlying state.
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "dry-run" in captured.err.lower() or "not yet implemented" in captured.err.lower()
