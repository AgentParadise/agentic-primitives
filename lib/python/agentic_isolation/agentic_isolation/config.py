"""Configuration types for workspace isolation."""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field, replace
from importlib import resources
from pathlib import Path, PurePosixPath
from typing import Any, ClassVar, Literal

logger = logging.getLogger(__name__)


def _load_plugin_manifest(plugin_path: str) -> dict[str, Any] | None:
    manifest_path = Path(plugin_path) / ".claude-plugin" / "plugin.json"
    if not manifest_path.exists():
        return None
    try:
        return json.loads(manifest_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read plugin manifest %s: %s", manifest_path, e)
        return None


def _resolve_single_env_var(
    var_name: str,
    spec: dict[str, Any],
    plugin_name: str,
) -> tuple[str, bool]:
    value = os.environ.get(var_name)
    if value is None:
        if spec.get("required", False):
            description = spec.get("description", "")
            raise ValueError(f"Plugin '{plugin_name}' requires env var {var_name}: {description}")
        return "", False
    return value, True


CODEX_SANDBOX_SECCOMP_PROFILE_NAME = "codex-sandbox.json"


def codex_sandbox_seccomp_profile() -> Path:
    """Filesystem path of the shipped Codex sandbox seccomp profile.

    Docker's default profile plus clone/unshare for the user, mount, pid, net
    and ipc namespaces only, and mount, umount2 and pivot_root, so Codex's
    bubblewrap sandbox can build its namespaces. See
    ``agentic_isolation/seccomp/README.md`` for provenance.

    The docker CLI reads this file on the host that runs ``docker run``, so it
    must be a real file, not a zip member.
    """
    resource = resources.files("agentic_isolation.seccomp") / CODEX_SANDBOX_SECCOMP_PROFILE_NAME
    path = Path(str(resource))
    if not path.is_file():
        raise FileNotFoundError(f"Codex sandbox seccomp profile is not installed as a file: {path}")
    return path


CODEX_SANDBOX_APPARMOR_PROFILE = "agentic-codex-sandbox"
_APPARMOR_POLICY_PROFILES = Path("/sys/kernel/security/apparmor/policy/profiles")
_APPARMOR_PROFILE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


#: Image label that declares a workspace image can run Codex. Set at build
#: time from the pinned Codex CLI version; the provider reads it with
#: ``docker image inspect`` and derives the Codex sandbox policy from it.
CODEX_IMAGE_LABEL = "agentic.codex_cli_version"


class CodexSandboxPolicyError(ValueError):
    """The requested Codex sandbox policy contradicts the image's declaration."""


class DockerDetectionError(RuntimeError):
    """A security-relevant Docker host property could not be determined.

    Never treated as "feature absent": that would silently drop protection.
    """


class AppArmorProfileNotLoadedError(RuntimeError):
    """AppArmor is active on the Docker host but the requested profile is not loaded."""

    def __init__(self, profile: str) -> None:
        super().__init__(
            f"AppArmor is active on the Docker host but profile {profile!r} is not loaded. "
            "Load it once per boot on the Docker host, then retry: "
            f"sudo apparmor_parser -r {codex_sandbox_apparmor_profile_path()} "
            "(see agentic_isolation/apparmor/README.md). Refusing to start the "
            "workspace without it."
        )
        self.profile = profile


def codex_sandbox_apparmor_profile_path() -> Path:
    """Filesystem path of the shipped Codex sandbox AppArmor profile.

    Docker's docker-default profile with its blanket ``deny mount,`` replaced
    by the mount and pivot_root operations bubblewrap performs. Loaded by the
    host administrator with ``apparmor_parser -r``; see
    ``agentic_isolation/apparmor/README.md``.
    """
    resource = resources.files("agentic_isolation.apparmor") / CODEX_SANDBOX_APPARMOR_PROFILE
    return Path(str(resource))


def apparmor_profile_loaded(profile: str) -> bool | None:
    """Whether ``profile`` is loaded in this kernel.

    Reads ``policy/profiles/*/name``, which unprivileged users can read (the
    flat ``profiles`` list is root-only on Ubuntu). None means this host cannot
    tell, for example because the Docker daemon is remote or securityfs is not
    mounted here; Docker then reports a missing profile itself at run time.
    """
    try:
        entries = list(_APPARMOR_POLICY_PROFILES.iterdir())
    except OSError:
        return None
    for entry in entries:
        try:
            if (entry / "name").read_text().strip() == profile:
                return True
        except OSError:
            continue
    return False


def is_apparmor_profile_error(detail: str) -> bool:
    """Whether a ``docker run`` failure means the AppArmor profile is missing."""
    return "apparmor failed to apply profile" in detail


@dataclass
class SecurityConfig:
    """Security hardening configuration for isolated workspaces.

    Controls Linux security features applied at container runtime.
    These settings cannot be baked into a Docker image - they must
    be applied via `docker run` flags.

    Default values provide production-grade hardening:
    - All Linux capabilities dropped
    - Privilege escalation blocked
    - Read-only root filesystem
    - Writable tmpfs for /tmp and /home

    Usage:
        # Production (default - maximum security)
        config = SecurityConfig.production()

        # Development (relaxed for debugging)
        config = SecurityConfig.development()

        # Custom
        config = SecurityConfig(read_only_root=False)

        # Codex sandbox policy: derived from the image label at create();
        # True/False only asserts the expectation (mismatch is rejected)
        config = SecurityConfig.production(codex_sandbox=True)
    """

    # Capability dropping
    cap_drop_all: bool = True  # --cap-drop=ALL

    # Privilege escalation prevention
    no_new_privileges: bool = True  # --security-opt=no-new-privileges

    # Filesystem protection
    read_only_root: bool = True  # --read-only
    tmpfs_tmp: bool = True  # --tmpfs=/tmp:rw,noexec,nosuid,size=256m
    tmpfs_home: bool = True  # --tmpfs=/home/agent:rw,exec,nosuid,size=128m
    # Capability working directories. Under --read-only these are image
    # directories on a read-only rootfs, so a capability that writes to them
    # fails at preflight and hard-fails the whole workspace. /spool is the
    # session-store capability's transcript partition (ADR-040); /var/agentic
    # is where the entrypoint writes capability doctor audit files.
    tmpfs_spool: bool = True  # --tmpfs=/spool:rw,noexec,nosuid,size=512m
    tmpfs_var_agentic: bool = True  # --tmpfs=/var/agentic:rw,noexec,nosuid,size=32m

    # Process limits
    pids_limit: int = 256  # --pids-limit=256

    # gVisor runtime (extra sandbox layer)
    use_gvisor: bool | None = None  # None = auto-detect, True/False = force

    # Seccomp profile file (--security-opt=seccomp=<path>). None keeps Docker's
    # default profile. Set for Codex-capable images by resolve_for_image();
    # see codex_sandbox_seccomp_profile().
    seccomp_profile: Path | None = None

    # AppArmor profile name (--security-opt=apparmor=<name>). Needed with the
    # Codex seccomp profile on AppArmor hosts, whose docker-default profile
    # denies the mounts bubblewrap makes. Applied only when AppArmor is active
    # on the Docker host (use_apparmor=None auto-detects); if it is active and
    # the profile is not loaded, launching fails closed.
    apparmor_profile: str | None = None
    use_apparmor: bool | None = None  # None = auto-detect, True/False = force

    # Codex sandbox policy. None derives it from the image's
    # ``agentic.codex_cli_version`` label at provision; True/False must agree
    # with that label or provisioning is rejected. See resolve_for_image().
    codex_sandbox: bool | None = None

    @classmethod
    def production(cls, *, codex_sandbox: bool | None = None) -> SecurityConfig:
        """Production-grade security configuration.

        All security features enabled. Use for untrusted workloads.

        The Codex sandbox policy (the shipped seccomp profile that lets
        Codex's bubblewrap sandbox create namespaces and, on AppArmor hosts,
        the paired AppArmor profile that lets it build its mount tree) is
        derived from the image at provision when ``codex_sandbox`` is None:
        images labelled ``agentic.codex_cli_version`` get it, others do not.
        Passing True or False asserts the expectation; a contradiction with
        the image is rejected. Capabilities stay dropped, no-new-privileges
        and the read-only root stay on either way.
        """
        return cls(codex_sandbox=codex_sandbox)._with_codex_profiles()

    def _with_codex_profiles(self) -> SecurityConfig:
        """Pin the shipped profiles; a different caller-supplied one is refused.

        A Codex image's policy is exactly the shipped pair, so a custom
        seccomp or AppArmor profile cannot silently replace it.
        """
        if self.codex_sandbox is not True:
            return self
        seccomp = codex_sandbox_seccomp_profile()
        if self.seccomp_profile is not None and (
            Path(self.seccomp_profile).resolve() != seccomp.resolve()
        ):
            raise CodexSandboxPolicyError(
                f"a Codex image must use the shipped seccomp profile {seccomp}, "
                f"not {self.seccomp_profile}"
            )
        if self.apparmor_profile not in (None, CODEX_SANDBOX_APPARMOR_PROFILE):
            raise CodexSandboxPolicyError(
                f"a Codex image must use the AppArmor profile {CODEX_SANDBOX_APPARMOR_PROFILE}, "
                f"not {self.apparmor_profile}"
            )
        return replace(
            self,
            seccomp_profile=seccomp,
            apparmor_profile=CODEX_SANDBOX_APPARMOR_PROFILE,
        )

    def resolve_for_image(self, codex_capable: bool) -> SecurityConfig:
        """The effective policy for an image, from its trusted declaration.

        ``codex_capable`` comes from the image label, never from the caller.
        """
        if self.codex_sandbox is True and not codex_capable:
            raise CodexSandboxPolicyError(
                f"codex_sandbox=True requested but the image has no {CODEX_IMAGE_LABEL} "
                "label; the Codex sandbox profiles are only for Codex-capable images"
            )
        if self.codex_sandbox is False and codex_capable:
            raise CodexSandboxPolicyError(
                f"codex_sandbox=False requested but the image declares {CODEX_IMAGE_LABEL}; "
                "a Codex-capable image must run with the Codex sandbox policy"
            )
        return replace(self, codex_sandbox=codex_capable)._with_codex_profiles()

    @classmethod
    def development(cls) -> SecurityConfig:
        """Relaxed security for local development.

        Easier to debug but less secure. Never use in production.
        """
        return cls(
            read_only_root=False,
            use_gvisor=False,
        )

    # Cache for gVisor detection to avoid repeated blocking subprocess calls.
    # Only successful answers are cached; a failed probe is retried next time.
    _gvisor_available: ClassVar[bool | None] = None
    _apparmor_available: ClassVar[bool | None] = None

    @staticmethod
    def _docker_info(template: str) -> str:
        """``docker info --format TEMPLATE``; raises DockerDetectionError on any failure."""
        if shutil.which("docker") is None:
            raise DockerDetectionError("docker CLI not found; cannot inspect the Docker host")
        try:
            result = subprocess.run(
                ["docker", "info", "--format", template],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as error:
            raise DockerDetectionError(f"docker info failed: {error}") from error
        if result.returncode != 0:
            raise DockerDetectionError(
                f"docker info exited {result.returncode}: {result.stderr.strip()[:300]}"
            )
        return result.stdout

    @classmethod
    def detect_apparmor(cls) -> bool:
        """Whether the Docker daemon confines containers with AppArmor.

        Asks the daemon (``docker info``), so it is right for remote hosts too;
        Docker Desktop reports no AppArmor. A failed query raises
        DockerDetectionError and is not cached: an unknown host is never
        treated as one without AppArmor.
        """
        if cls._apparmor_available is None:
            cls._apparmor_available = "name=apparmor" in cls._docker_info(
                "{{json .SecurityOptions}}"
            )
        return cls._apparmor_available

    @classmethod
    def detect_gvisor(cls) -> bool:
        """Detect if the gVisor runtime is available.

        No docker CLI means no runtime to detect (and nothing can launch).
        A failed query raises DockerDetectionError and is not cached, so a
        transient failure never silently drops gVisor.
        """
        if cls._gvisor_available is not None:
            return cls._gvisor_available
        if shutil.which("docker") is None:
            return False
        runtimes = cls._docker_info("{{json .Runtimes}}")
        cls._gvisor_available = "runsc" in runtimes or "gvisor" in runtimes
        return cls._gvisor_available

    def to_docker_run_args(self) -> list[str]:
        """Convert to docker run command line arguments."""
        args: list[str] = []

        if self.cap_drop_all:
            args.append("--cap-drop=ALL")

        if self.no_new_privileges:
            args.append("--security-opt=no-new-privileges")

        if self.read_only_root:
            args.append("--read-only")

        if self.tmpfs_tmp:
            args.append("--tmpfs=/tmp:rw,noexec,nosuid,size=256m")

        if self.tmpfs_home:
            args.append("--tmpfs=/home/agent:rw,exec,nosuid,size=128m,uid=1000,gid=1000")

        # Owned by the agent user: capabilities run as the non-root agent and
        # must be able to create their partition and audit directories.
        if self.tmpfs_spool:
            args.append("--tmpfs=/spool:rw,noexec,nosuid,size=512m,uid=1000,gid=1000")

        if self.tmpfs_var_agentic:
            args.append("--tmpfs=/var/agentic:rw,noexec,nosuid,size=32m,uid=1000,gid=1000")

        if self.pids_limit > 0:
            args.append(f"--pids-limit={self.pids_limit}")

        if self.seccomp_profile is not None:
            profile = Path(self.seccomp_profile)
            if not profile.is_file():
                raise FileNotFoundError(f"Seccomp profile not found: {profile}")
            args.append(f"--security-opt=seccomp={profile.resolve()}")

        if self.apparmor_profile is not None:
            name = self.apparmor_profile
            if not _APPARMOR_PROFILE_NAME.fullmatch(name):
                raise ValueError(f"Invalid AppArmor profile name: {name!r}")
            use_apparmor = self.use_apparmor
            if use_apparmor is None:
                use_apparmor = self.detect_apparmor()
            if use_apparmor:
                if apparmor_profile_loaded(name) is False:
                    raise AppArmorProfileNotLoadedError(name)
                args.append(f"--security-opt=apparmor={name}")

        # gVisor runtime
        use_gvisor = self.use_gvisor
        if use_gvisor is None:
            use_gvisor = self.detect_gvisor()
        if use_gvisor:
            args.append("--runtime=runsc")

        return args


@dataclass
class ResourceLimits:
    """Resource limits for isolated workspaces."""

    cpu: str = "2"  # Number of CPUs or CPU shares
    memory: str = "4G"  # Memory limit (e.g., "4G", "512M")
    disk: str | None = None  # Disk space limit
    network: bool = True  # Allow network access
    timeout_seconds: int = 3600  # Max execution time (1 hour default)

    def to_docker_args(self) -> dict[str, Any]:
        """Convert to Docker run arguments."""
        args: dict[str, Any] = {
            "cpu_count": int(self.cpu) if self.cpu.isdigit() else 2,
            "mem_limit": self.memory,
        }
        if not self.network:
            args["network_mode"] = "none"
        return args


@dataclass
class MountConfig:
    """Configuration for a volume mount."""

    host_path: str | Path
    container_path: str
    read_only: bool = False
    kind: Literal["bind", "volume"] = "bind"

    def __post_init__(self) -> None:
        if self.kind not in ("bind", "volume"):
            raise ValueError("Unsupported mount kind")
        target = PurePosixPath(self.container_path)
        if (
            not target.is_absolute()
            or self.container_path.startswith("//")
            or ".." in target.parts
            or str(target) == "/"
        ):
            raise ValueError("Mount target must be an absolute non-root container path")
        if any(char in str(self.host_path) + self.container_path for char in "\x00\r\n"):
            raise ValueError("Mount paths must not contain control characters")
        if self.kind == "volume" and not re.fullmatch(
            r"[a-zA-Z0-9][a-zA-Z0-9_.-]+", str(self.host_path)
        ):
            raise ValueError("Invalid Docker volume name")

    def to_docker_mount(self) -> dict[str, Any]:
        """Convert to Docker mount specification."""
        return {
            "type": self.kind,
            "source": str(self.host_path)
            if self.kind == "volume"
            else str(Path(self.host_path).resolve()),
            "target": str(PurePosixPath(self.container_path)),
            "read_only": self.read_only,
        }

    def to_docker_run_arg(self) -> str:
        """Encode one Docker --mount CSV argument without shell interpolation."""
        mount = self.to_docker_mount()
        fields = [f"type={mount['type']}", f"source={mount['source']}", f"target={mount['target']}"]
        if self.read_only:
            fields.append("readonly")
        output = io.StringIO()
        csv.writer(output, lineterminator="").writerow(fields)
        return output.getvalue()


@dataclass
class WorkspaceConfig:
    """Configuration for creating an isolated workspace."""

    # Provider selection
    provider: str = "local"  # "local", "docker", "e2b"

    # Docker-specific
    image: str = "python:3.12-slim"
    dockerfile: str | Path | None = None

    # Working directory inside workspace
    working_dir: str = "/workspace"

    # Mounts
    mounts: list[MountConfig] = field(default_factory=list)

    # Secrets (injected as environment variables).
    #
    # `repr=False` because the generated `__repr__` renders values in plaintext,
    # and a config is rendered far more often than anyone intends: a failed
    # assertion in any test that compares configs, a debugger frame, an
    # exception whose message interpolates the object, a DEBUG log line. One
    # assertion failure is enough to put a live credential in CI output.
    secrets: dict[str, str] = field(default_factory=dict, repr=False)

    # Environment variables.
    #
    # Historically documented as "non-secret", and that is no longer true of how
    # this field is used. A capability contract delivered through here can carry
    # a credential (AGENTIC_SESSION_STORE_AUTH is the live example), so this
    # field is treated as secret-bearing and gets the same `repr=False`.
    #
    # Moving credentials into `secrets` is NOT an alternative to this: that
    # field had the identical exposure until this change, so the advice "put
    # secrets in `secrets`" was a mitigation that did nothing.
    environment: dict[str, str] = field(default_factory=dict, repr=False)

    # Resource limits
    limits: ResourceLimits = field(default_factory=ResourceLimits)

    # Security hardening (Docker provider only)
    security: SecurityConfig = field(default_factory=SecurityConfig)

    # Cleanup behavior
    auto_cleanup: bool = True  # Remove workspace on exit
    keep_on_error: bool = False  # Keep workspace if error occurs

    # Labels for identification
    labels: dict[str, str] = field(default_factory=dict)

    # Plugin directories to load via --plugin-dir (ADR-033)
    plugins: list[str] = field(default_factory=list)

    def with_plugin(self, plugin_path: str | Path) -> WorkspaceConfig:
        """Add a plugin directory and return self for chaining."""
        self.plugins.append(str(plugin_path))
        return self

    def _apply_env_var(
        self,
        var_name: str,
        spec: dict[str, Any],
        plugin_name: str,
    ) -> None:
        """Resolve and store a single environment variable from a plugin manifest."""
        if var_name in self.secrets or var_name in self.environment:
            return

        value, resolved = _resolve_single_env_var(var_name, spec, plugin_name)
        if not resolved:
            return

        if spec.get("secret", False):
            self.secrets[var_name] = value
        else:
            self.environment[var_name] = value

    def resolve_plugin_env(self) -> None:
        """Read requires_env from plugin manifests and populate secrets/environment.

        For each plugin directory, reads .claude-plugin/plugin.json and
        looks for a requires_env field. For each declared env var:
        - secret=true vars are added to self.secrets (if set in host env)
        - secret=false vars are added to self.environment (if set in host env)
        - required=true vars raise ValueError if not set

        This method is idempotent - safe to call multiple times.
        """
        for plugin_path in self.plugins:
            manifest = _load_plugin_manifest(plugin_path)
            if manifest is None:
                continue

            requires_env = manifest.get("requires_env", {})
            plugin_name = manifest.get("name", Path(plugin_path).name)

            for var_name, spec in requires_env.items():
                self._apply_env_var(var_name, spec, plugin_name)

    def with_mount(
        self,
        host_path: str | Path,
        container_path: str,
        read_only: bool = False,
    ) -> WorkspaceConfig:
        """Add a mount and return self for chaining."""
        self.mounts.append(MountConfig(host_path, container_path, read_only))
        return self

    def with_secret(self, name: str, value: str) -> WorkspaceConfig:
        """Add a secret and return self for chaining."""
        self.secrets[name] = value
        return self

    def with_env(self, name: str, value: str) -> WorkspaceConfig:
        """Add an environment variable and return self for chaining."""
        self.environment[name] = value
        return self
