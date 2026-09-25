# Seccomp profiles

## `codex-sandbox.json`

Docker's default seccomp profile plus four appended rules, so Codex's
bubblewrap sandbox can create the namespaces it needs inside a workspace that
otherwise keeps `--cap-drop=ALL`, `--security-opt=no-new-privileges` and
`--read-only`.

The providers apply it to images that declare Codex with the
`agentic.codex_cli_version` label, and only to those: Python derives it in
`WorkspaceDockerProvider.create` (`SecurityConfig.codex_sandbox` None), Rust in
`DockerProvider::provision`. An explicit request that contradicts the label
(`codex_sandbox=True` / `with_codex_sandbox` on an image without it, or
`False` / `without_codex_sandbox` on one with it) is refused before launch.
Every other workspace keeps Docker's default profile, unchanged.

### Provenance

| | |
|---|---|
| Upstream | `vendor/github.com/moby/profiles/seccomp/default.json` in moby/moby |
| Tag | `docker-v29.8.0` (commit `3ce5872b7950c63ba2ffbc5123101019ff3e6682`) |
| Module | `github.com/moby/profiles/seccomp v0.2.3` |
| Upstream sha256 | `536529b665dd0972c37bfb569f5d4ac8a53592e7b00752bc39ff063ca9864c74` |

The file is byte-identical to upstream except for the appended rules (and a
trailing newline). Verify with:

```bash
curl -fsSL https://raw.githubusercontent.com/moby/moby/3ce5872b7950c63ba2ffbc5123101019ff3e6682/vendor/github.com/moby/profiles/seccomp/default.json \
  | diff - codex-sandbox.json
```

### The additions

| Syscall | Condition | Why bubblewrap needs it | Default profile |
|---|---|---|---|
| `clone` | `(flags & (CLONE_NEWUTS \| CLONE_NEWCGROUP)) == 0` (arg 0; arg 1 on s390) | new user, mount, pid, net and ipc namespaces | no `CLONE_NEW*` flag at all, unless `CAP_SYS_ADMIN` |
| `unshare` | `(flags & (CLONE_NEWUTS \| CLONE_NEWCGROUP \| CLONE_NEWTIME)) == 0` | same namespaces via unshare | `CAP_SYS_ADMIN` only |
| `mount` | none | build the sandbox mount tree | `CAP_SYS_ADMIN` only |
| `umount2` | none | detach the old root | `CAP_SYS_ADMIN` only |
| `pivot_root` | none | switch into the sandbox root | not allowed |

The namespace set is measured, not assumed: `strace -f -e trace=clone,unshare`
of `codex sandbox` (codex-cli 0.156.1, workspace-write) on an Ubuntu 24.04
runner showed only `CLONE_NEWUSER`, `CLONE_NEWNS`, `CLONE_NEWPID`,
`CLONE_NEWNET` and `CLONE_NEWIPC`. With the filter in force, `unshare --uts`,
`--cgroup` and `--time` fail while both Codex sandbox modes work.
`CLONE_NEWTIME` (0x80) is masked for `unshare` only: for `clone` that bit is
part of the exit-signal byte, and a new time namespace cannot be created by
`clone` anyway.

`mount`, `umount2` and `pivot_root` cannot be narrowed usefully by seccomp,
which only sees pointer arguments. On AppArmor hosts the paired AppArmor profile
restricts them to the exact operations bubblewrap performs. On hosts without
AppArmor (Docker Desktop, OrbStack) only the kernel mediates them: they take
effect only inside a user namespace the container created, inherited mounts
stay locked (a read-only mount cannot be remounted writable, measured), and
binds can only expose what the agent user can already read. Arbitrary binds
and tmpfs mounts inside that private namespace are possible there; that
residual is accepted for hosts without an LSM, and the Docker conformance
suite asserts the full denial set only where AppArmor is active.

Deliberately NOT added: `setns` (verified unnecessary for
`codex sandbox`), `clone3` (still returns `ENOSYS`, so libc falls back to
`clone`), and every other `CAP_SYS_ADMIN`-gated call (`bpf`, `fsopen`,
`open_tree`, `move_mount`, `perf_event_open`, ...).

### Security trade-off

Unprivileged user namespaces expose more kernel attack surface to code in
the container. Mitigations that remain in force: all capabilities dropped,
`no-new-privileges`, read-only root, the opt-in is scoped to Codex-capable
workspaces, and hosts are expected to run patched kernels.

On AppArmor hosts (for example Ubuntu 24.04) this profile is not enough on its
own: Docker's `docker-default` AppArmor profile denies the mounts bubblewrap
makes. The opt-in therefore also applies the paired AppArmor profile
`agentic-codex-sandbox`; see [`../apparmor/README.md`](../apparmor/README.md)
for the host setup step.

### Updating

Bump when the pinned Docker version moves: replace the upstream body,
re-append the rules above unchanged and update the table. When the pinned
Codex CLI moves, re-measure the namespace flags (strace, as above) and the
AppArmor mount set (see `../apparmor/README.md`). Then run the docker
integration test `tests/integration/test_codex_sandbox_seccomp.py` and the
Docker conformance suite on an AppArmor host.
