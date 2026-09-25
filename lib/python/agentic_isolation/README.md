# agentic-isolation

Workspace isolation for AI agent execution with security hardening and streaming.

## Installation

```bash
pip install agentic-isolation
```

## Quick Start

```python
from agentic_isolation import AgenticWorkspace

# Docker provider (production)
async with AgenticWorkspace.create(provider="docker") as workspace:
    result = await workspace.execute("echo hello")
    print(result.stdout)  # "hello\n"

# Local provider (development/testing)
async with AgenticWorkspace.create(provider="local") as workspace:
    result = await workspace.execute("echo hello")
    print(result.stdout)
```

## Providers

### WorkspaceDockerProvider

Production-grade isolation with Docker containers and security hardening.

```python
from agentic_isolation import AgenticWorkspace, SecurityConfig

# With production security hardening
async with AgenticWorkspace.create(
    provider="docker",
    image="python:3.12-slim",
    security=SecurityConfig.production(),
) as workspace:
    result = await workspace.execute("python --version")
```

### WorkspaceLocalProvider

For development and testing. Creates isolated directories but no process isolation.

```python
async with AgenticWorkspace.create(
    provider="local",
    working_dir="/workspace",
) as workspace:
    await workspace.write_file("test.py", b"print('hi')")
    result = await workspace.execute("python test.py")
```

## Security Hardening

The `SecurityConfig` class provides production-grade Docker security:

```python
from agentic_isolation import SecurityConfig

# Production profile (recommended)
security = SecurityConfig.production()
# - cap_drop_all: Drop ALL Linux capabilities
# - no_new_privileges: Prevent privilege escalation
# - read_only_root: Read-only root filesystem
# - tmpfs_tmp: Ephemeral /tmp
# - tmpfs_home: Ephemeral /home/agent
# - pids_limit: 256 max processes
# - gVisor runtime (if available)

# Development profile (for local testing)
security = SecurityConfig.development()
# - Less restrictive for debugging

# Workspaces that can run Codex
security = SecurityConfig.production(codex_sandbox=True)
# - Everything production() sets, plus
#   --security-opt=seccomp=<installed codex-sandbox.json>
#   --security-opt=apparmor=agentic-codex-sandbox (AppArmor hosts only)
```

`codex_sandbox=True` lets Codex's own bubblewrap sandbox create a user
namespace, which Docker's default seccomp profile denies. The shipped profile
is Docker's default plus exactly `clone` (namespace flags), `unshare`, `mount`,
`umount2` and `pivot_root`; capabilities stay dropped and no-new-privileges and
the read-only root stay on. Use it only for Codex-capable workspaces. Pass the
same `SecurityConfig` as `WorkspaceConfig.security`, which takes precedence
over the provider's. Provenance and trade-offs:
[`agentic_isolation/seccomp/README.md`](agentic_isolation/seccomp/README.md).
`codex_sandbox_seccomp_profile()` returns the installed file path.

On hosts where Docker uses AppArmor (Ubuntu 24.04 and most Debian/Ubuntu
servers) the opt-in also applies the AppArmor profile `agentic-codex-sandbox`,
docker-default with `deny mount,` replaced by the mounts bubblewrap needs. Load
it once per boot on the Docker host:
`sudo apparmor_parser -r <codex_sandbox_apparmor_profile_path()>`. If AppArmor
is active and the profile is missing, workspace creation raises
`AppArmorProfileNotLoadedError`. Details:
[`agentic_isolation/apparmor/README.md`](agentic_isolation/apparmor/README.md).

## Real-Time Streaming

Stream stdout line-by-line for observability dashboards:

```python
async with AgenticWorkspace.create(provider="docker") as workspace:
    async for line in workspace.stream(["python", "-u", "agent.py"]):
        print(f"Agent output: {line}")
        # Parse JSONL events, update dashboard, etc.
```

## File Operations

```python
async with AgenticWorkspace.create() as workspace:
    # Write file
    await workspace.write_file("script.py", b"print('hello')")

    # Read file
    content = await workspace.read_file("script.py")

    # Check existence
    exists = await workspace.file_exists("script.py")

    # Execute
    result = await workspace.execute("python script.py")
```

## Direct Provider Usage

For more control, use providers directly:

```python
from agentic_isolation import WorkspaceDockerProvider, WorkspaceConfig, SecurityConfig

provider = WorkspaceDockerProvider(
    default_image="python:3.12-slim",
    security=SecurityConfig.production(),
)

config = WorkspaceConfig(
    provider="docker",
    working_dir="/workspace",
    environment={"API_KEY": "secret"},
)

workspace = await provider.create(config)
try:
    result = await provider.execute(workspace, "python --version")
    print(result.stdout)
finally:
    await provider.destroy(workspace)
```

## API Reference

### AgenticWorkspace

Main entry point for workspace isolation.

```python
@classmethod
async def create(
    provider: str = "docker",  # "docker" or "local"
    image: str | None = None,
    working_dir: str = "/workspace",
    environment: dict[str, str] | None = None,
    security: SecurityConfig | None = None,
) -> AgenticWorkspace
```

### SecurityConfig

Security configuration for Docker containers.

```python
@dataclass
class SecurityConfig:
    cap_drop_all: bool = True
    no_new_privileges: bool = True
    read_only_root: bool = True
    tmpfs_tmp: bool = True
    tmpfs_home: bool = True
    pids_limit: int = 256
    use_gvisor: bool | None = None  # None = auto-detect

    @classmethod
    def production(cls) -> SecurityConfig: ...
    @classmethod
    def development(cls) -> SecurityConfig: ...
```

### ExecuteResult

Result of command execution.

```python
@dataclass
class ExecuteResult:
    exit_code: int
    stdout: str
    stderr: str
    success: bool
    duration_ms: float
    timed_out: bool = False
```

## License

MIT
