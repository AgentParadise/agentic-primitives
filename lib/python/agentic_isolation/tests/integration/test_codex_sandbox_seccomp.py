"""Codex's own sandbox inside a production-hardened omni-agent workspace.

Runs the real omni-agent image through WorkspaceDockerProvider, so the flags
under test are the ones production emits. With the Codex sandbox seccomp
profile, `codex sandbox` (bubblewrap) works: writes inside the workspace
succeed and writes outside it are denied, while --cap-drop=ALL,
no-new-privileges and --read-only stay in force. Without the profile, the
entrypoint probe records the sandbox as unavailable and syn-delegate refuses
to launch Codex, recording launch_failed. On AppArmor hosts the paired
AppArmor profile must be loaded first (sudo apparmor_parser -r, see
agentic_isolation/apparmor/README.md).

Requirements:
    - Docker
    - an omni-agent image built from this tree:
      `uv run scripts/build-provider.py omni-agent`
      (override the tag with AGENTIC_OMNI_AGENT_IMAGE)

Run with: pytest tests/integration/test_codex_sandbox_seccomp.py -v
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from agentic_isolation import (
    CODEX_SANDBOX_APPARMOR_PROFILE,
    SecurityConfig,
    Workspace,
    WorkspaceConfig,
    WorkspaceDockerProvider,
)

IMAGE = os.environ.get("AGENTIC_OMNI_AGENT_IMAGE", "agentic-workspace-omni-agent:latest")
STATUS = "/var/agentic/codex-sandbox.json"
# Scoped to the cwd; _docker_exec runs in /workspace. (`-C` needs a
# --permission-profile on codex 0.156.1.)
SANDBOX = ["codex", "sandbox", "-c", 'sandbox_mode="workspace-write"', "--"]


def _image_available() -> bool:
    try:
        result = subprocess.run(
            ["docker", "image", "inspect", IMAGE], capture_output=True, check=False
        )
    except FileNotFoundError:
        return False
    return result.returncode == 0


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _image_available(),
        reason=f"Docker or {IMAGE} not available; "
        "run `uv run scripts/build-provider.py omni-agent`",
    ),
]


def _docker_exec(
    container: str, argv: list[str], env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    command = ["docker", "exec", "-w", "/workspace"]
    for key, value in (env or {}).items():
        command.extend(["-e", f"{key}={value}"])
    return subprocess.run(
        [*command, container, *argv], capture_output=True, text=True, timeout=120, check=False
    )


def _status(container: str) -> dict[str, object]:
    # The entrypoint writes the record before exec'ing the keep-alive CMD.
    waited = _docker_exec(
        container,
        [
            "bash",
            "-c",
            f"for _ in $(seq 150); do [ -f {STATUS} ] && exec cat {STATUS}; "
            "sleep 0.2; done; exit 1",
        ],
    )
    assert waited.returncode == 0, f"no probe record: {waited.stderr}"
    document: dict[str, object] = json.loads(waited.stdout)
    return document


def _host_config(container: str) -> dict[str, object]:
    inspected = subprocess.run(
        ["docker", "inspect", "--format", "{{json .HostConfig}}", container],
        capture_output=True,
        text=True,
        check=True,
    )
    config: dict[str, object] = json.loads(inspected.stdout)
    return config


async def _workspace(security: SecurityConfig) -> AsyncIterator[tuple[str, Workspace]]:
    security.use_gvisor = False
    provider = WorkspaceDockerProvider(default_image=IMAGE, security=security)
    # WorkspaceConfig.security wins over the provider's (as Syntropic137 wires
    # it, both are set to the same value).
    workspace = await provider.create(
        WorkspaceConfig(provider="docker", image=IMAGE, security=security)
    )
    try:
        container = workspace.metadata["container_name"]
        assert isinstance(container, str)
        yield container, workspace
    finally:
        await provider.destroy(workspace)


@pytest.fixture
async def codex_workspace() -> AsyncIterator[tuple[str, Workspace]]:
    async for item in _workspace(SecurityConfig.production(codex_sandbox=True)):
        yield item


@pytest.fixture
async def default_workspace() -> AsyncIterator[tuple[str, Workspace]]:
    async for item in _workspace(SecurityConfig.production()):
        yield item


def _delegate_env() -> dict[str, str]:
    return {
        "AGENTIC_SESSION_STORE_PROVIDER": "local",
        "AGENTIC_SESSION_STORE_SPOOL": "/spool",
        "AGENTIC_SESSION_STORE_PARTITION": "run",
        "AGENTIC_INVOCATION_ID": "invocation",
        "AGENTIC_ATTEMPT_ID": "attempt",
        "AGENTIC_PARENT_HARNESS": "claude",
        "AGENTIC_PARENT_NATIVE_ID": "parent",
    }


def _delegate(container: str) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    prepared = _docker_exec(container, ["mkdir", "-p", "/spool/.agentic-session-store/run"])
    assert prepared.returncode == 0, prepared.stderr
    delegated = _docker_exec(
        container,
        ["syn-delegate", "codex", "--prompt", "Reply done", "--timeout", "30"],
        env=_delegate_env(),
    )
    exported = _docker_exec(
        container,
        [
            "python",
            "-m",
            "agentic_session_store.child_export",
            "/spool/.agentic-session-store/run/children.sqlite",
        ],
    )
    assert exported.returncode == 0, exported.stderr
    changes = json.loads(exported.stdout)["page"]["changes"]
    assert changes, "syn-delegate recorded no intent"
    intent: dict[str, object] = changes[-1]["intent"]
    return delegated, intent


class TestWithCodexSandboxProfile:
    @pytest.mark.asyncio
    async def test_hardening_flags_survive_the_opt_in(
        self, codex_workspace: tuple[str, Workspace]
    ) -> None:
        container, _ = codex_workspace
        config = _host_config(container)
        assert config["CapDrop"] == ["ALL"]
        assert config["ReadonlyRootfs"] is True
        security_opt = config["SecurityOpt"]
        assert isinstance(security_opt, list)
        assert "no-new-privileges" in security_opt
        assert any(str(opt).startswith("seccomp=") for opt in security_opt)
        assert not config.get("CapAdd")
        apparmor = subprocess.run(
            ["docker", "inspect", "--format", "{{.AppArmorProfile}}", container],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        if SecurityConfig.detect_apparmor():
            assert apparmor == CODEX_SANDBOX_APPARMOR_PROFILE
        else:
            assert apparmor == ""
        assert config.get("Privileged") is False
        uid = _docker_exec(container, ["id", "-u"])
        assert uid.stdout.strip() == "1000"

    @pytest.mark.asyncio
    async def test_probe_reports_available(self, codex_workspace: tuple[str, Workspace]) -> None:
        container, _ = codex_workspace
        status = _status(container)
        assert status["schema_version"] == 1
        assert status["available"] is True, status

    @pytest.mark.asyncio
    async def test_workspace_write_allowed_outside_denied(
        self, codex_workspace: tuple[str, Workspace]
    ) -> None:
        container, workspace = codex_workspace
        inside = _docker_exec(
            container, [*SANDBOX, "sh", "-c", "echo inside > /workspace/inside.txt"]
        )
        assert inside.returncode == 0, inside.stderr
        host_dir = workspace.metadata["workspace_dir"]
        assert isinstance(host_dir, str)
        assert (Path(host_dir) / "inside.txt").read_text() == "inside\n"

        outside = _docker_exec(
            container, [*SANDBOX, "sh", "-c", "echo outside > /home/agent/outside.txt"]
        )
        assert outside.returncode != 0, outside.stdout
        assert "bwrap" not in outside.stderr, outside.stderr
        leaked = _docker_exec(container, ["test", "-e", "/home/agent/outside.txt"])
        assert leaked.returncode != 0, "sandboxed write escaped the workspace"

        # The same write without Codex's sandbox succeeds (home is a writable
        # tmpfs), so the denial above is the sandbox, not the filesystem.
        control = _docker_exec(container, ["sh", "-c", "echo ok > /home/agent/control.txt"])
        assert control.returncode == 0, control.stderr

    @pytest.mark.asyncio
    async def test_syn_delegate_passes_the_sandbox_gate(
        self, codex_workspace: tuple[str, Workspace]
    ) -> None:
        container, _ = codex_workspace
        assert _status(container)["available"] is True
        delegated, intent = _delegate(container)
        # No credentials, so Codex itself fails; what matters is it LAUNCHED.
        assert delegated.returncode != 69, delegated.stderr
        assert intent["status"] != "launch_failed", intent
        assert "reason" not in intent


class TestWithoutCodexSandboxProfile:
    @pytest.mark.asyncio
    async def test_probe_reports_unavailable(
        self, default_workspace: tuple[str, Workspace]
    ) -> None:
        container, _ = default_workspace
        config = _host_config(container)
        security_opt = config["SecurityOpt"]
        assert isinstance(security_opt, list)
        assert not any(str(opt).startswith("seccomp=") for opt in security_opt)
        status = _status(container)
        assert status["available"] is False, status
        assert "namespace" in str(status["detail"]), status

    @pytest.mark.asyncio
    async def test_syn_delegate_refuses_and_records_launch_failed(
        self, default_workspace: tuple[str, Workspace]
    ) -> None:
        container, _ = default_workspace
        assert _status(container)["available"] is False
        delegated, intent = _delegate(container)
        assert delegated.returncode == 69, (delegated.stdout, delegated.stderr)
        assert "Codex sandbox is unavailable" in delegated.stderr
        assert intent["status"] == "launch_failed"
        assert intent["reason"] == "codex_sandbox_unavailable"
        assert "child_native_id" not in intent or intent["child_native_id"] is None
