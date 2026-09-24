# Persistent workspace mounts

The Docker provider accepts bind mounts and named volumes through `WorkspaceConfig.mounts`:

```python
from agentic_isolation import MountConfig, WorkspaceConfig

config = WorkspaceConfig(
    provider="docker",
    mounts=[MountConfig("workflow-session-spool", "/spool", kind="volume")],
)
```

The orchestrator owns the volume name and its association with a workflow run.
Container removal does not delete named volumes. Reuse the same volume to recover
native transcripts after container loss. Volume retention and eventual deletion
remain the orchestrator's responsibility.

An explicit mount replaces the default security tmpfs at the same destination.
Other tmpfs mounts and security settings remain active. Mount targets must be
absolute, unique, and cannot replace `/workspace`. Bind mounts keep their existing
host-path resolution behavior; named volumes preserve the Docker volume name.

The workspace image must provide suitable ownership at the mount destination.
For `/spool`, the omni-agent image provides ownership for the agent user. A generic
image with no such directory may create a root-owned volume and require explicit
provisioning before a non-root agent can write.

This storage contract preserves files. It does not establish workflow attribution,
capture completeness, or successful replication to a remote store.
