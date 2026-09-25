# AppArmor profiles

## `agentic-codex-sandbox`

The AppArmor half of the Codex sandbox opt-in. It pairs with
`../seccomp/codex-sandbox.json` and is applied only by
`SecurityConfig.production(codex_sandbox=True)` (Python) or
`DockerProvider::with_codex_sandbox` (Rust), and only when the Docker daemon
reports AppArmor (`docker info` security options contain `name=apparmor`).
Hosts without AppArmor, such as Docker Desktop, get no AppArmor option at all.

### Why it is needed

Measured on a GitHub `ubuntu-latest` runner (Ubuntu 24.04.5, kernel
6.17 azure, AppArmor parser 4.0.1, `kernel.apparmor_restrict_unprivileged_userns=1`)
with codex-cli 0.156.1 and the Codex seccomp profile:

- User-namespace creation already works under `docker-default`; the
  userns restriction is not the blocker (docker-default is an ABI 3.0
  profile, so no `userns,` rule is required, and none is added).
- bubblewrap then fails with `bwrap: Failed to make / slave: Permission denied`
  because `docker-default` contains `deny mount,`.

### Provenance

Rendered from the `docker-default` template in
`vendor/github.com/moby/profiles/apparmor/template.go` of moby/moby tag
`docker-v29.8.0` (commit `3ce5872b7950c63ba2ffbc5123101019ff3e6682`,
module `github.com/moby/profiles/apparmor v0.2.2-0.20260828104831-61eaf32614c7`),
with `DaemonProfile=unconfined`, `abi/3.0`, `tunables/global` and
`abstractions/base`, which is what dockerd renders on Ubuntu. The profile name
is `agentic-codex-sandbox`.

### The one change

`deny mount,` is replaced by exactly the operations bubblewrap performs while
building its sandbox inside its own mount namespace, taken from complain-mode
audit records of `codex sandbox` in workspace-write and read-only modes:

| Rule | bubblewrap step |
|---|---|
| `mount options in (rw, silent, rslave) -> /` | stop propagation out of the new namespace |
| `mount options in (rw, silent, rprivate) -> /oldroot/` | detach the old root before unmounting it |
| `mount fstype=tmpfs ... tmpfs -> /tmp/` | staging root |
| `mount options in (rw, rbind, silent) /tmp/newroot/ -> /tmp/newroot/` | bind the staging root onto itself |
| `pivot_root oldroot=/tmp/oldroot/ /tmp/` | enter the staging root |
| `mount fstype=tmpfs ... tmpfs -> /newroot/{,**}` | tmpfs directories in the sandbox tree |
| `mount options in (rw, rbind, silent) /oldroot/{,**} -> /newroot/{,**}` | bind visible paths |
| `mount options in (ro, nosuid, nodev, noexec, remount, bind, silent, relatime) -> /newroot/{,**}` | make them read-only |
| `mount fstype=proc ... proc -> /newroot/proc/` | sandbox `/proc` |
| `mount fstype=devpts ... devpts -> /newroot/dev/pts/` | sandbox `/dev/pts` |
| `pivot_root oldroot=/newroot/ /newroot/` | final root switch |

Everything else is `docker-default` verbatim. Verified on the runner, in
enforce mode: workspace-write writes succeed inside the workspace and are
denied outside it, read-only mode denies writes, and arbitrary mounts
(`tmpfs` on `/mnt`, bind of `/etc` on `/mnt`, `proc` on `/mnt`, `tmpfs` on
`/tmp` from a non-`tmpfs` source) are still denied.

### Host setup (once per boot, on the Docker host)

```bash
sudo apparmor_parser -r "$(uv run python -c 'from agentic_isolation import codex_sandbox_apparmor_profile_path as p; print(p())')"
```

or copy the file to `/etc/apparmor.d/agentic-codex-sandbox` so it loads at
boot. The file must be loaded on the host that runs the Docker daemon.

If AppArmor is active and the profile is not loaded, launching fails closed
with `AppArmorProfileNotLoadedError` (Python) or `WorkspaceError::Unsupported`
(Rust) naming this command. When load state cannot be read locally (for
example a remote daemon) the option is still passed and Docker's own
`apparmor failed to apply profile` error is translated to the same error.

### Not changed

No capabilities are added, `apparmor=unconfined` is never used, and host
sysctls such as `kernel.apparmor_restrict_unprivileged_userns` are left alone.
