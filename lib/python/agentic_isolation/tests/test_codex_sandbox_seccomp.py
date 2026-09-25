"""The Codex sandbox seccomp profile: opt-in only, shipped as a file, minimal."""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

import pytest

from agentic_isolation import (
    CODEX_SANDBOX_APPARMOR_PROFILE,
    CODEX_SANDBOX_SECCOMP_PROFILE_NAME,
    AppArmorProfileNotLoadedError,
    CodexSandboxPolicyError,
    DockerDetectionError,
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


CLONE_NEWUTS = 0x04000000
CLONE_NEWCGROUP = 0x02000000
CLONE_NEWTIME = 0x00000080
CLONE_NAMESPACES = 0x7E020000  # every CLONE_NEW* flag Docker's default masks


def _added_rules() -> list[dict[str, object]]:
    return [rule for rule in _rules() if "agentic-isolation" in str(rule.get("comment", ""))]


def test_profile_adds_only_the_codex_rules_at_the_end() -> None:
    profile = _profile()
    assert profile["defaultAction"] == "SCMP_ACT_ERRNO"
    added = _added_rules()
    assert added == _rules()[-len(added) :]
    names = sorted({name for rule in added for name in rule["names"]})  # type: ignore[union-attr]
    assert names == ADDED_SYSCALLS
    assert all(rule["action"] == "SCMP_ACT_ALLOW" for rule in added)


def _masked(rule: dict[str, object]) -> tuple[int, int]:
    args = rule["args"]
    assert isinstance(args, list) and len(args) == 1
    arg = args[0]
    assert arg["op"] == "SCMP_CMP_MASKED_EQ" and arg.get("valueTwo", 0) == 0
    return arg["index"], arg["value"]


def test_clone_and_unshare_only_gain_the_namespaces_bwrap_uses() -> None:
    by_name: dict[str, list[dict[str, object]]] = {}
    for rule in _added_rules():
        for name in rule["names"]:  # type: ignore[union-attr]
            by_name.setdefault(str(name), []).append(rule)
    clone_masks = {_masked(rule) for rule in by_name["clone"]}
    # Index 0 everywhere, index 1 on s390 (argument order differs there).
    assert clone_masks == {(0, CLONE_NEWUTS | CLONE_NEWCGROUP), (1, CLONE_NEWUTS | CLONE_NEWCGROUP)}
    assert [_masked(rule) for rule in by_name["unshare"]] == [
        (0, CLONE_NEWUTS | CLONE_NEWCGROUP | CLONE_NEWTIME)
    ]
    allowed = CLONE_NAMESPACES & ~(CLONE_NEWUTS | CLONE_NEWCGROUP)
    assert allowed == 0x10000000 | 0x00020000 | 0x20000000 | 0x40000000 | 0x08000000
    for name in ("mount", "pivot_root", "umount2"):
        assert "args" not in by_name[name][0]


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


def _apparmor_rules() -> list[str]:
    lines = [
        line.split("#", 1)[0].strip()
        for line in codex_sandbox_apparmor_profile_path().read_text().splitlines()
    ]
    return [line for line in lines if line and not line.startswith("#")]


def test_apparmor_profile_has_no_blanket_or_wildcard_mount_grants() -> None:
    rules = _apparmor_rules()
    assert "deny mount," not in rules
    assert "mount," not in rules
    assert "userns," not in rules  # verified unnecessary under ABI 3.0
    for rule in (r for r in rules if r.startswith("mount ")):
        target = rule.rsplit(" -> ", 1)[-1].rstrip(",")
        assert " -> " in rule and "options" in rule, rule
        if "rbind" in rule or "tmpfs" in rule or "(rw," in rule:
            # Creating or writable mounts: never a bare wildcard under /newroot.
            assert target not in {"/newroot/{,**}", "/newroot/**"}, rule


def test_apparmor_writable_remount_only_on_workspace_roots() -> None:
    writable = [
        r for r in _apparmor_rules() if r.startswith("mount options=(rw") and "remount" in r
    ]
    assert writable == [
        "mount options=(rw, nosuid, nodev, remount, bind, silent, relatime)"
        " -> /newroot/workspace/{,**/},"
    ]
    readonly = [r for r in _apparmor_rules() if r.startswith("mount options=(ro")]
    assert readonly and all("ro," in r and "remount" in r for r in readonly)


def test_apparmor_binds_are_the_recorded_pairs() -> None:
    binds = sorted(
        r.split(") ", 1)[1].rstrip(",")
        for r in _apparmor_rules()
        if r.startswith("mount options=(rw, rbind)")
    )
    assert binds == sorted(
        [
            "/tmp/newroot/ -> /tmp/newroot/",
            "/oldroot/ -> /newroot/",
            "/oldroot/usr/ -> /newroot/usr/",
            "/oldroot/usr/bin/ -> /newroot/bin/",
            "/oldroot/usr/sbin/ -> /newroot/sbin/",
            "/oldroot/usr/lib/ -> /newroot/lib/",
            "/oldroot/usr/lib64/ -> /newroot/lib64/",
            "/oldroot/etc/ -> /newroot/etc/",
            *(
                f"/oldroot/dev/{d} -> /newroot/dev/{d}"
                for d in ("null", "zero", "full", "random", "urandom", "tty")
            ),
            "/oldroot/tmp/ -> /newroot/tmp/",
            "/oldroot/tmp/codex-bwrap-synthetic-mount-targets-*/"
            " -> /newroot/tmp/codex-bwrap-synthetic-mount-targets-*/",
            "/oldroot/workspace/{,**/} -> /newroot/workspace/{,**/}",
        ]
    )


def test_apparmor_explicitly_denies_sensitive_mounts() -> None:
    rules = _apparmor_rules()
    for rule in (
        "deny mount fstype=sysfs,",
        "deny mount fstype=cgroup,",
        "deny mount fstype=cgroup2,",
        "deny mount /{,oldroot/}{proc,sys}/** -> /**,",
        "deny mount /{,oldroot/}{run,var/run}/** -> /**,",
        "deny mount /**/docker.sock -> /**,",
    ):
        assert rule in rules
    for rule in (
        "deny @{PROC}/sysrq-trigger rwklx,",
        "deny /sys/kernel/security/** rwklx,",
        "deny network vsock,",
    ):
        assert rule in rules


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


# --- Detection never fails open (review finding 2) ---------------------------


class _Info:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture
def fresh_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(SecurityConfig, "_apparmor_available", None)
    monkeypatch.setattr(config_module.shutil, "which", lambda _name: "/usr/bin/docker")
    monkeypatch.setattr(config_module, "apparmor_profile_loaded", lambda _name: True)


@pytest.mark.usefixtures("fresh_detection")
@pytest.mark.parametrize(
    "failure",
    [
        _Info(1, stderr="Cannot connect to the Docker daemon"),
        subprocess.TimeoutExpired(["docker", "info"], 10),
    ],
)
def test_failed_apparmor_detection_fails_launch_then_recovers(
    monkeypatch: pytest.MonkeyPatch, failure: object
) -> None:
    answers: list[object] = [failure, _Info(0, '["name=apparmor","name=seccomp"]')]

    def run(*_args: object, **_kwargs: object) -> object:
        answer = answers.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer

    monkeypatch.setattr(config_module.subprocess, "run", run)
    config = SecurityConfig.production(codex_sandbox=True)
    config.use_gvisor = False
    with pytest.raises(DockerDetectionError):
        config.to_docker_run_args()
    assert SecurityConfig._apparmor_available is None  # the failure was not cached
    args = config.to_docker_run_args()
    assert f"--security-opt=apparmor={CODEX_SANDBOX_APPARMOR_PROFILE}" in args


@pytest.mark.usefixtures("fresh_detection")
def test_missing_docker_cli_is_not_treated_as_no_apparmor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(config_module.shutil, "which", lambda _name: None)
    config = SecurityConfig.production(codex_sandbox=True)
    config.use_gvisor = False
    with pytest.raises(DockerDetectionError, match="docker CLI not found"):
        config.to_docker_run_args()


# --- Policy is derived from the image's declaration (review finding 3) --------


def test_codex_image_derives_the_policy() -> None:
    resolved = SecurityConfig.production().resolve_for_image(codex_capable=True)
    assert resolved.codex_sandbox is True
    assert resolved.seccomp_profile == codex_sandbox_seccomp_profile()
    assert resolved.apparmor_profile == CODEX_SANDBOX_APPARMOR_PROFILE


def test_plain_image_keeps_docker_defaults() -> None:
    resolved = SecurityConfig.production().resolve_for_image(codex_capable=False)
    assert resolved.codex_sandbox is False
    assert resolved.seccomp_profile is None
    assert resolved.apparmor_profile is None


def test_opt_in_on_plain_image_is_rejected() -> None:
    with pytest.raises(CodexSandboxPolicyError, match="no agentic.codex_cli_version"):
        SecurityConfig.production(codex_sandbox=True).resolve_for_image(codex_capable=False)


def test_opt_out_on_codex_image_is_rejected() -> None:
    with pytest.raises(CodexSandboxPolicyError, match="declares agentic.codex_cli_version"):
        SecurityConfig.production(codex_sandbox=False).resolve_for_image(codex_capable=True)


def test_development_also_derives() -> None:
    resolved = SecurityConfig.development().resolve_for_image(codex_capable=True)
    assert resolved.seccomp_profile is not None
    assert resolved.read_only_root is False


class _Proc:
    def __init__(self, returncode: int, stdout: bytes = b"", stderr: bytes = b"") -> None:
        self.returncode = returncode
        self._out = (stdout, stderr)

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._out


inspected: list[str] = []


def _fake_docker(
    monkeypatch: pytest.MonkeyPatch, labels: dict[str, str] | None, calls: list[list[str]]
) -> None:
    async def spawn(*argv: str, **_kwargs: object) -> _Proc:
        calls.append(list(argv))
        if argv[1:3] == ("image", "inspect"):
            if labels is None:
                return _Proc(1)
            # The tag resolves to a different image on every inspect, as if
            # it were being moved concurrently.
            inspected.append(f"sha256:{len(inspected):064x}")
            config = {"Labels": labels} if labels else {}  # unlabelled: key absent
            return _Proc(0, f"{inspected[-1]} {json.dumps(config)}".encode())
        if argv[1] == "pull":
            return _Proc(1, stderr=b"pull access denied")
        if argv[1] == "run":
            return _Proc(125, stderr=b"stop here")
        return _Proc(0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)


async def _create(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    labels: dict[str, str] | None,
    security: SecurityConfig,
) -> list[list[str]]:
    calls: list[list[str]] = []
    _fake_docker(monkeypatch, labels, calls)
    security.use_gvisor = False
    security.use_apparmor = False
    provider = WorkspaceDockerProvider(workspace_base_dir=tmp_path, security=security)

    async def noop(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(provider, "_ensure_network", noop)
    monkeypatch.setattr(provider, "_cleanup_container", noop)
    # WorkspaceConfig.security always wins over the provider's, so the
    # detection overrides above must travel on it.
    with pytest.raises(RuntimeError, match="stop here"):
        await provider.create(WorkspaceConfig(provider="docker", image="img", security=security))
    return calls


def _run_args(calls: list[list[str]]) -> list[str]:
    return next(call for call in calls if call[1] == "run")


async def test_create_applies_profile_to_codex_image_with_plain_production(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = await _create(
        monkeypatch, tmp_path, {"agentic.codex_cli_version": "0.156.1"}, SecurityConfig.production()
    )
    run = _run_args(calls)
    assert any(arg.startswith("--security-opt=seccomp=") for arg in run)
    assert "--cap-drop=ALL" in run


async def test_create_keeps_plain_image_on_docker_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = await _create(monkeypatch, tmp_path, {}, SecurityConfig.production())
    assert not any(arg.startswith("--security-opt=seccomp=") for arg in _run_args(calls))


@pytest.mark.parametrize(
    ("labels", "codex_sandbox"),
    [({}, True), ({"agentic.codex_cli_version": "0.156.1"}, False)],
)
async def test_create_rejects_a_mismatch_before_launch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    labels: dict[str, str],
    codex_sandbox: bool,
) -> None:
    calls: list[list[str]] = []
    _fake_docker(monkeypatch, labels, calls)
    provider = WorkspaceDockerProvider(workspace_base_dir=tmp_path)
    with pytest.raises(CodexSandboxPolicyError):
        await provider.create(
            WorkspaceConfig(
                provider="docker",
                image="img",
                security=SecurityConfig.production(codex_sandbox=codex_sandbox),
            )
        )
    assert not any(call[1] == "run" for call in calls)
    assert not list(tmp_path.iterdir())  # nothing was created


async def test_create_fails_closed_when_image_labels_are_unreadable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []
    _fake_docker(monkeypatch, None, calls)
    provider = WorkspaceDockerProvider(workspace_base_dir=tmp_path)
    with pytest.raises(RuntimeError, match="Cannot inspect image img"):
        await provider.create(WorkspaceConfig(provider="docker", image="img"))
    assert [call[1] for call in calls] == ["image", "pull", "image"]


# --- Review pass 2 ------------------------------------------------------------


async def test_create_launches_the_inspected_image_id_not_the_tag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls = await _create(
        monkeypatch, tmp_path, {"agentic.codex_cli_version": "0.156.1"}, SecurityConfig.production()
    )
    inspects = [call for call in calls if call[1:3] == ["image", "inspect"]]
    assert len(inspects) == 1  # inspected once
    run = _run_args(calls)
    assert "img" not in run
    launched = [arg for arg in run if arg.startswith("sha256:")]
    assert launched == [inspected[-1]]


def test_codex_image_ignores_nothing_it_would_silently_replace(tmp_path: Path) -> None:
    custom = tmp_path / "custom.json"
    custom.write_text("{}")
    with pytest.raises(CodexSandboxPolicyError, match="shipped seccomp profile"):
        SecurityConfig(seccomp_profile=custom).resolve_for_image(codex_capable=True)
    with pytest.raises(CodexSandboxPolicyError, match="AppArmor profile"):
        SecurityConfig(apparmor_profile="unconfined").resolve_for_image(codex_capable=True)


async def test_create_rejects_a_custom_profile_on_a_codex_image(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    custom = tmp_path / "custom.json"
    custom.write_text("{}")
    calls: list[list[str]] = []
    _fake_docker(monkeypatch, {"agentic.codex_cli_version": "0.156.1"}, calls)
    provider = WorkspaceDockerProvider(workspace_base_dir=tmp_path / "ws")
    with pytest.raises(CodexSandboxPolicyError):
        await provider.create(
            WorkspaceConfig(
                provider="docker", image="img", security=SecurityConfig(seccomp_profile=custom)
            )
        )
    assert not any(call[1] == "run" for call in calls)


async def test_codex_image_effective_args_are_the_shipped_pair(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(config_module, "apparmor_profile_loaded", lambda _name: True)
    security = SecurityConfig(
        seccomp_profile=codex_sandbox_seccomp_profile(),
        apparmor_profile=CODEX_SANDBOX_APPARMOR_PROFILE,
    )
    calls: list[list[str]] = []
    _fake_docker(monkeypatch, {"agentic.codex_cli_version": "0.156.1"}, calls)
    security.use_gvisor = False
    security.use_apparmor = True
    provider = WorkspaceDockerProvider(workspace_base_dir=tmp_path)

    async def noop(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(provider, "_ensure_network", noop)
    monkeypatch.setattr(provider, "_cleanup_container", noop)
    with pytest.raises(RuntimeError, match="stop here"):
        await provider.create(WorkspaceConfig(provider="docker", image="img", security=security))
    run = _run_args(calls)
    assert [a for a in run if a.startswith("--security-opt=")] == [
        "--security-opt=no-new-privileges",
        f"--security-opt=seccomp={codex_sandbox_seccomp_profile().resolve()}",
        f"--security-opt=apparmor={CODEX_SANDBOX_APPARMOR_PROFILE}",
    ]
