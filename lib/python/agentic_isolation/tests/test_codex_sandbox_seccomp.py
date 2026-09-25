"""The Codex sandbox seccomp profile: opt-in only, shipped as a file, minimal."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentic_isolation import (
    CODEX_SANDBOX_APPARMOR_PROFILE,
    CODEX_SANDBOX_SECCOMP_PROFILE_NAME,
    AppArmorProfileNotLoadedError,
    SecurityConfig,
    WorkspaceConfig,
    WorkspaceDockerProvider,
    codex_sandbox_apparmor_profile_path,
    codex_sandbox_seccomp_profile,
)
from agentic_isolation import config as config_module

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
    codex.use_apparmor = False

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
    codex.use_apparmor = False
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


def _codex_on_apparmor_host() -> SecurityConfig:
    config = SecurityConfig.production(codex_sandbox=True)
    config.use_gvisor = False
    config.use_apparmor = True
    return config


def test_apparmor_profile_is_installed_and_named() -> None:
    path = codex_sandbox_apparmor_profile_path()
    assert path.is_file()
    assert path.name == CODEX_SANDBOX_APPARMOR_PROFILE
    text = path.read_text()
    assert f"profile {CODEX_SANDBOX_APPARMOR_PROFILE} flags=" in text
    assert "abi <abi/3.0>," in text


def test_apparmor_profile_only_replaces_deny_mount() -> None:
    lines = [
        line.split("#", 1)[0].strip()
        for line in codex_sandbox_apparmor_profile_path().read_text().splitlines()
    ]
    rules = [line for line in lines if line]
    assert "deny mount," not in rules
    assert "mount," not in rules  # no blanket allow
    assert "userns," not in rules  # verified unnecessary under ABI 3.0
    mount_rules = [r for r in rules if r.startswith(("mount ", "pivot_root "))]
    assert all(" -> /" in r or r.startswith("pivot_root ") for r in mount_rules)
    targets = {r.rsplit(" -> ", 1)[-1] for r in mount_rules if " -> " in r}
    assert targets == {
        "/,",
        "/oldroot/,",
        "/tmp/,",
        "/tmp/newroot/,",
        "/newroot/{,**},",
        "/newroot/proc/,",
        "/newroot/dev/pts/,",
    }
    # docker-default's other denials survive.
    for rule in (
        "deny @{PROC}/sysrq-trigger rwklx,",
        "deny /sys/kernel/security/** rwklx,",
        "deny network vsock,",
    ):
        assert rule in rules


def test_apparmor_applied_on_apparmor_host_when_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config_module, "apparmor_profile_loaded", lambda _name: True)
    args = _codex_on_apparmor_host().to_docker_run_args()
    assert f"--security-opt=apparmor={CODEX_SANDBOX_APPARMOR_PROFILE}" in args
    assert any(a.startswith("--security-opt=seccomp=") for a in args)


def test_apparmor_unknown_load_state_still_applies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config_module, "apparmor_profile_loaded", lambda _name: None)
    args = _codex_on_apparmor_host().to_docker_run_args()
    assert f"--security-opt=apparmor={CODEX_SANDBOX_APPARMOR_PROFILE}" in args


def test_apparmor_host_without_loaded_profile_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config_module, "apparmor_profile_loaded", lambda _name: False)
    with pytest.raises(AppArmorProfileNotLoadedError, match="apparmor_parser -r"):
        _codex_on_apparmor_host().to_docker_run_args()


def test_no_apparmor_option_on_hosts_without_apparmor() -> None:
    config = SecurityConfig.production(codex_sandbox=True)
    config.use_gvisor = False
    config.use_apparmor = False
    assert not any(a.startswith("--security-opt=apparmor") for a in config.to_docker_run_args())


def test_default_production_never_sets_apparmor() -> None:
    config = SecurityConfig.production()
    config.use_gvisor = False
    config.use_apparmor = True
    assert config.apparmor_profile is None
    assert not any(a.startswith("--security-opt=apparmor") for a in config.to_docker_run_args())


@pytest.mark.parametrize("name", ["", "unconfined;x", "../x", "a b"])
def test_invalid_apparmor_names_rejected(name: str) -> None:
    config = SecurityConfig(apparmor_profile=name, use_apparmor=True, use_gvisor=False)
    with pytest.raises(ValueError, match="Invalid AppArmor profile name"):
        config.to_docker_run_args()


def test_loaded_detection_reads_policy_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profiles = tmp_path / "profiles"
    (profiles / "agentic-codex-sandbox.12").mkdir(parents=True)
    (profiles / "agentic-codex-sandbox.12" / "name").write_text("agentic-codex-sandbox\n")
    (profiles / "docker-default.3").mkdir()
    (profiles / "docker-default.3" / "name").write_text("docker-default\n")
    monkeypatch.setattr(config_module, "_APPARMOR_POLICY_PROFILES", profiles)
    assert config_module.apparmor_profile_loaded("agentic-codex-sandbox") is True
    assert config_module.apparmor_profile_loaded("agentic-other") is False
    monkeypatch.setattr(config_module, "_APPARMOR_POLICY_PROFILES", tmp_path / "absent")
    assert config_module.apparmor_profile_loaded("agentic-codex-sandbox") is None


def test_docker_apparmor_failure_is_recognised() -> None:
    detail = (
        "docker: Error response from daemon: ... unable to apply apparmor profile: "
        "apparmor failed to apply profile: write .../attr/apparmor/exec: no such file"
    )
    assert config_module.is_apparmor_profile_error(detail)
    assert not config_module.is_apparmor_profile_error("no such image")
