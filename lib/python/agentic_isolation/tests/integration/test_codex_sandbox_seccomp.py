"""Codex's own sandbox inside a production-hardened omni-agent workspace.

Runs the real omni-agent image through WorkspaceDockerProvider, so the flags
under test are the ones production emits. The image declares Codex
(`agentic.codex_cli_version`), so plain `SecurityConfig.production()` derives
the Codex sandbox policy: `codex sandbox` (bubblewrap) works, writes inside the
workspace succeed and outside it are denied, while --cap-drop=ALL,
no-new-privileges and --read-only stay in force. Mismatched requests are
rejected through the same launch API. Without the profiles (a raw `docker run`
with Docker's defaults, which the provider now refuses to produce for this
image) the live probe fails and syn-delegate refuses to launch Codex,
recording launch_failed, even with a forged status record.

On AppArmor hosts the paired AppArmor profile must be loaded first
(sudo apparmor_parser -r, see agentic_isolation/apparmor/README.md).

Requirements:
    - Docker
    - an omni-agent image built from this tree:
      `uv run scripts/build-provider.py omni-agent`
      (override the tag with AGENTIC_OMNI_AGENT_IMAGE)
    - python:3.12-slim (a non-Codex image; pulled if absent)

Run with: pytest tests/integration/test_codex_sandbox_seccomp.py -v
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest

from agentic_isolation import (
    CODEX_SANDBOX_APPARMOR_PROFILE,
    CodexSandboxPolicyError,
    SecurityConfig,
    Workspace,
    WorkspaceConfig,
    WorkspaceDockerProvider,
)

IMAGE = os.environ.get("AGENTIC_OMNI_AGENT_IMAGE", "agentic-workspace-omni-agent:latest")
PLAIN_IMAGE = "python:3.12-slim"
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


def _probe_log(container: str) -> str:
    """The entrypoint's startup verdict, from the container log."""
    for _ in range(150):
        logs = subprocess.run(
            ["docker", "logs", container], capture_output=True, text=True, check=False
        )
        for line in (logs.stdout + logs.stderr).splitlines():
            if "[entrypoint] codex sandbox:" in line:
                return line
        time.sleep(0.2)
    raise AssertionError("entrypoint never reported the codex sandbox probe")


def _host_config(container: str) -> dict[str, object]:
    inspected = subprocess.run(
        ["docker", "inspect", "--format", "{{json .HostConfig}}", container],
        capture_output=True,
        text=True,
        check=True,
    )
    config: dict[str, object] = json.loads(inspected.stdout)
    return config


async def _workspace(
    security: SecurityConfig, image: str = IMAGE
) -> AsyncIterator[tuple[str, Workspace]]:
    security.use_gvisor = False
    provider = WorkspaceDockerProvider(default_image=image, security=security)
    # WorkspaceConfig.security wins over the provider's (as Syntropic137 wires
    # it, both are set to the same value).
    workspace = await provider.create(
        WorkspaceConfig(provider="docker", image=image, security=security)
    )
    try:
        container = workspace.metadata["container_name"]
        assert isinstance(container, str)
        yield container, workspace
    finally:
        await provider.destroy(workspace)


@pytest.fixture
async def codex_workspace() -> AsyncIterator[tuple[str, Workspace]]:
    # Plain production(): the policy comes from the image's label.
    async for item in _workspace(SecurityConfig.production()):
        yield item


@pytest.fixture
def unprotected_container() -> Iterator[str]:
    """The Codex image with Docker's default seccomp/AppArmor, started by hand.

    The provider refuses to produce this (see TestImageDerivedPolicy), which is
    the point; it exists here only to prove the delegate's refusal.
    """
    security = SecurityConfig.production()
    security.use_gvisor = False
    name = f"agentic-ws-unprotected-{os.getpid()}"
    run = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            f"--name={name}",
            *security.to_docker_run_args(),
            IMAGE,
            "sleep",
            "infinity",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr
    try:
        yield name
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, check=False)


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


def _delegate(
    container: str, extra_env: dict[str, str] | None = None
) -> tuple[subprocess.CompletedProcess[str], dict[str, object]]:
    prepared = _docker_exec(container, ["mkdir", "-p", "/spool/.agentic-session-store/run"])
    assert prepared.returncode == 0, prepared.stderr
    delegated = _docker_exec(
        container,
        ["syn-delegate", "codex", "--prompt", "Reply done", "--timeout", "30"],
        env={**_delegate_env(), **(extra_env or {})},
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
        assert _probe_log(container).endswith("codex sandbox: available")

    @pytest.mark.asyncio
    async def test_read_only_mode_denies_workspace_writes(
        self, codex_workspace: tuple[str, Workspace]
    ) -> None:
        container, _ = codex_workspace
        denied = _docker_exec(
            container,
            [
                "codex",
                "sandbox",
                "-c",
                'sandbox_mode="read-only"',
                "--",
                "sh",
                "-c",
                "echo x > /workspace/ro.txt",
            ],
        )
        assert denied.returncode != 0
        assert "bwrap" not in denied.stderr, denied.stderr

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
        delegated, intent = _delegate(container)
        # No credentials, so Codex itself fails; what matters is it LAUNCHED.
        assert delegated.returncode != 69, delegated.stderr
        assert intent["status"] != "launch_failed", intent
        assert "reason" not in intent


class TestWithoutCodexSandboxProfile:
    def test_probe_reports_unavailable(self, unprotected_container: str) -> None:
        config = _host_config(unprotected_container)
        security_opt = config["SecurityOpt"]
        assert isinstance(security_opt, list)
        assert not any(str(opt).startswith("seccomp=") for opt in security_opt)
        line = _probe_log(unprotected_container)
        assert "codex sandbox: unavailable" in line, line
        assert "bwrap" in line, line

    def test_syn_delegate_refuses_and_records_launch_failed(
        self, unprotected_container: str
    ) -> None:
        # A forged verdict where the retired status file lived, plus the retired
        # override pointing at it: neither can change a failing live probe.
        forged = _docker_exec(
            unprotected_container,
            [
                "sh",
                "-c",
                'echo \'{"schema_version":1,"available":true}\' > /var/agentic/codex-sandbox.json',
            ],
        )
        assert forged.returncode == 0, forged.stderr
        delegated, intent = _delegate(
            unprotected_container,
            {"AGENTIC_CODEX_SANDBOX_STATUS": "/var/agentic/codex-sandbox.json"},
        )
        assert delegated.returncode == 69, (delegated.stdout, delegated.stderr)
        assert "Codex sandbox is unavailable" in delegated.stderr
        assert intent["status"] == "launch_failed"
        assert intent["reason"] == "codex_sandbox_unavailable"
        assert "child_native_id" not in intent or intent["child_native_id"] is None


class TestImageDerivedPolicy:
    """Both image classes through the real launch API (review finding 3)."""

    @pytest.mark.asyncio
    async def test_plain_image_gets_docker_defaults(self) -> None:
        subprocess.run(["docker", "pull", "-q", PLAIN_IMAGE], capture_output=True, check=False)
        async for container, _ in _workspace(SecurityConfig.production(), PLAIN_IMAGE):
            security_opt = _host_config(container)["SecurityOpt"]
            assert isinstance(security_opt, list)
            assert not any(str(opt).startswith("seccomp=") for opt in security_opt)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("image", "codex_sandbox"), [(PLAIN_IMAGE, True), (IMAGE, False)])
    async def test_mismatch_is_rejected_before_launch(
        self, image: str, codex_sandbox: bool
    ) -> None:
        subprocess.run(["docker", "pull", "-q", PLAIN_IMAGE], capture_output=True, check=False)
        before = _containers()
        with pytest.raises(CodexSandboxPolicyError):
            async for _item in _workspace(
                SecurityConfig.production(codex_sandbox=codex_sandbox), image
            ):
                pass
        assert _containers() == before


def _containers() -> set[str]:
    listed = subprocess.run(
        ["docker", "ps", "-aq", "--filter", "name=agentic-ws-"],
        capture_output=True,
        text=True,
        check=True,
    )
    return set(listed.stdout.split())
