"""The Codex sandbox seccomp profile: opt-in only, shipped as a file, minimal."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentic_isolation import (
    CODEX_SANDBOX_SECCOMP_PROFILE_NAME,
    SecurityConfig,
    WorkspaceConfig,
    WorkspaceDockerProvider,
    codex_sandbox_seccomp_profile,
)

ADDED_SYSCALLS = ["clone", "mount", "pivot_root", "umount2", "unshare"]


def _profile() -> dict[str, object]:
    document: dict[str, object] = json.loads(codex_sandbox_seccomp_profile().read_text())
    return document


def _rules() -> list[dict[str, object]]:
    rules = _profile()["syscalls"]
    assert isinstance(rules, list)
    return rules


def _seccomp_args(args: list[str]) -> list[str]:
    return [arg for arg in args if arg.startswith("--security-opt=seccomp")]


def _run_command(security: SecurityConfig) -> list[str]:
    return WorkspaceDockerProvider()._build_run_command(
        container_name="test",
        workspace_id="test",
        workspace_dir=Path("/tmp/workspace"),
        image="alpine:3.19",
        config=WorkspaceConfig(),
        security=security,
    )


def test_profile_is_installed_as_a_real_file() -> None:
    path = codex_sandbox_seccomp_profile()
    assert path.is_absolute()
    assert path.is_file()
    assert path.name == CODEX_SANDBOX_SECCOMP_PROFILE_NAME


def test_default_production_keeps_docker_default_seccomp() -> None:
    config = SecurityConfig.production()
    config.use_gvisor = False
    assert config.seccomp_profile is None
    assert _seccomp_args(config.to_docker_run_args()) == []
    assert _seccomp_args(_run_command(config)) == []


def test_codex_sandbox_adds_only_the_profile() -> None:
    plain = SecurityConfig.production()
    plain.use_gvisor = False
    codex = SecurityConfig.production(codex_sandbox=True)
    codex.use_gvisor = False

    profile = codex_sandbox_seccomp_profile().resolve()
    assert codex.seccomp_profile == codex_sandbox_seccomp_profile()
    args = codex.to_docker_run_args()
    assert _seccomp_args(args) == [f"--security-opt=seccomp={profile}"]
    assert [arg for arg in args if not arg.startswith("--security-opt=seccomp")] == (
        plain.to_docker_run_args()
    )
    # Hardening that must survive the opt-in.
    for flag in ("--cap-drop=ALL", "--security-opt=no-new-privileges", "--read-only"):
        assert flag in args


def test_provider_emits_the_profile() -> None:
    codex = SecurityConfig.production(codex_sandbox=True)
    codex.use_gvisor = False
    command = _run_command(codex)
    assert f"--security-opt=seccomp={codex_sandbox_seccomp_profile().resolve()}" in command
    assert "--cap-drop=ALL" in command
    assert "--read-only" in command


def test_missing_profile_fails_closed(tmp_path: Path) -> None:
    config = SecurityConfig(seccomp_profile=tmp_path / "absent.json", use_gvisor=False)
    with pytest.raises(FileNotFoundError, match="Seccomp profile not found"):
        config.to_docker_run_args()


def test_profile_adds_exactly_one_unconditional_rule_for_five_syscalls() -> None:
    profile = _profile()
    assert profile["defaultAction"] == "SCMP_ACT_ERRNO"
    added = [rule for rule in _rules() if "agentic-isolation" in str(rule.get("comment", ""))]
    assert len(added) == 1
    rule = added[0]
    assert rule["names"] == ADDED_SYSCALLS
    assert rule["action"] == "SCMP_ACT_ALLOW"
    assert set(rule) == {"names", "action", "comment"}
    assert rule == _rules()[-1]


def test_profile_keeps_setns_and_clone3_capability_gated() -> None:
    for rule in _rules():
        names = rule["names"]
        assert isinstance(names, list)
        if rule["action"] != "SCMP_ACT_ALLOW":
            continue
        if not {"setns", "clone3", "bpf", "open_tree", "move_mount"} & set(names):
            continue
        includes = rule.get("includes")
        assert isinstance(includes, dict)
        assert includes.get("caps"), f"{names} allowed without a capability"


def test_development_does_not_opt_in() -> None:
    assert SecurityConfig.development().seccomp_profile is None
