# agentic-isolation

Workspace isolation for AI agent execution.

## Installation

```bash
# Core only (local provider)
pip install agentic-isolation

# With Docker provider
pip install agentic-isolation[docker]
```

## Quick Start

```python
from agentic_isolation import IsolatedWorkspace

# Local provider (for development)
async with IsolatedWorkspace.create(provider="local") as workspace:
    result = await workspace.execute("echo hello")
    print(result.stdout)  # "hello\n"
```

## Providers

### Local Provider

For development and testing. Creates isolated directories but no real process isolation.

```python
async with IsolatedWorkspace.create(
    provider="local",
    working_dir="/workspace",
) as workspace:
    await workspace.write_file("test.py", "print('hi')")
    result = await workspace.execute("python test.py")
```

### Docker Provider

For production. Creates isolated Docker containers.

```python
async with IsolatedWorkspace.create(
    provider="docker",
    image="python:3.12-slim",
    secrets={"API_KEY": "secret"},
    mounts=[("/host/code", "/workspace/code", True)],  # read-only
) as workspace:
    result = await workspace.execute("python --version")
```

## Features

### Secrets Injection

Secrets are injected as environment variables:

```python
async with IsolatedWorkspace.create(
    provider="docker",
    secrets={
        "GITHUB_TOKEN": "ghp_xxx",
        "API_KEY": "sk-xxx",
    },
) as workspace:
    # Secrets available as environment variables
    result = await workspace.execute("echo $GITHUB_TOKEN")
```

### Resource Limits

```python
from agentic_isolation import ResourceLimits

async with IsolatedWorkspace.create(
    provider="docker",
    limits=ResourceLimits(
        cpu="2",
        memory="4G",
        timeout_seconds=3600,
    ),
) as workspace:
    # Workspace limited to 2 CPUs, 4GB RAM, 1 hour timeout
    pass
```

### Volume Mounts

```python
async with IsolatedWorkspace.create(
    provider="docker",
    mounts=[
        ("/host/data", "/workspace/data", True),   # read-only
        ("/host/output", "/workspace/output", False),  # read-write
    ],
) as workspace:
    pass
```

### File Operations

```python
async with IsolatedWorkspace.create() as workspace:
    # Write file
    await workspace.write_file("test.py", "print('hello')")
    
    # Read file
    content = await workspace.read_file("test.py")
    
    # Check existence
    exists = await workspace.file_exists("test.py")
```

### Error Handling

```python
async with IsolatedWorkspace.create(
    auto_cleanup=True,      # Cleanup on normal exit
    keep_on_error=True,     # Keep workspace on error for debugging
) as workspace:
    result = await workspace.execute("exit 1")
    if not result.success:
        print(f"Command failed: {result.stderr}")
```

## Custom Providers

```python
from agentic_isolation import WorkspaceProvider, register_provider

class MyProvider:
    @property
    def name(self) -> str:
        return "my-provider"
    
    async def create(self, config): ...
    async def destroy(self, workspace): ...
    async def execute(self, workspace, command, **kwargs): ...
    async def write_file(self, workspace, path, content): ...
    async def read_file(self, workspace, path): ...
    async def file_exists(self, workspace, path): ...

register_provider("my-provider", MyProvider)

# Now use it
async with IsolatedWorkspace.create(provider="my-provider"):
    pass
```

## License

MIT
