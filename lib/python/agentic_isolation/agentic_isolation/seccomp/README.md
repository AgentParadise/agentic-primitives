# Seccomp profiles

## `codex-sandbox.json`

Docker's default seccomp profile plus exactly one added rule, so Codex's
bubblewrap sandbox can create the user namespace it needs inside a workspace
that otherwise keeps `--cap-drop=ALL`, `--security-opt=no-new-privileges` and
`--read-only`.

Opt in with `SecurityConfig.production(codex_sandbox=True)` (Python) or
`DockerProvider::with_codex_sandbox` (Rust). Only workspaces
that can run Codex should use it. Every other workspace keeps Docker's default
profile, unchanged.

### Provenance

| | |
|---|---|
| Upstream | `vendor/github.com/moby/profiles/seccomp/default.json` in moby/moby |
| Tag | `docker-v29.8.0` (commit `3ce5872b7950c63ba2ffbc5123101019ff3e6682`) |
| Module | `github.com/moby/profiles/seccomp v0.2.3` |
| Upstream sha256 | `536529b665dd0972c37bfb569f5d4ac8a53592e7b00752bc39ff063ca9864c74` |

The file is byte-identical to upstream except for the appended rule (and a
trailing newline). Verify with:

```bash
curl -fsSL https://raw.githubusercontent.com/moby/moby/3ce5872b7950c63ba2ffbc5123101019ff3e6682/vendor/github.com/moby/profiles/seccomp/default.json \
  | diff - codex-sandbox.json
```

### The five additions

One `SCMP_ACT_ALLOW` rule, no argument filters, no capability condition:

| Syscall | Why bubblewrap needs it | Default profile |
|---|---|---|
| `clone` | `CLONE_NEWUSER`/`CLONE_NEWNS`/`CLONE_NEWPID`/... flags | Allowed only when no `CLONE_NEW*` flag is set, unless `CAP_SYS_ADMIN` |
| `unshare` | enter new namespaces | `CAP_SYS_ADMIN` only |
| `mount` | build the sandbox mount tree inside the new mount namespace | `CAP_SYS_ADMIN` only |
| `umount2` | detach the old root | `CAP_SYS_ADMIN` only |
| `pivot_root` | switch into the sandbox root | not allowed |

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

Bump only when the pinned Docker version moves. Replace the upstream body,
re-append the rule above unchanged, update the table, and run the docker
integration test `tests/integration/test_codex_sandbox_seccomp.py`.
