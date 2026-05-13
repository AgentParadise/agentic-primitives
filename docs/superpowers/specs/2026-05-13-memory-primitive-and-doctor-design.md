# Memory Primitive + Doctor Design (Workspace Image)

**Status:** Draft
**Created:** 2026-05-13
**Author:** NeuralEmpowerment
**Related:** [ADR-036](../../adrs/036-memory-primitive-and-doctor.md), [ADR-035 Workspace Injection Contract](../../adrs/035-workspace-injection-contract.md)
**Sibling design doc:** [agentic-memory/docs/architecture/memory-contract.md](../../../../agentic-memory/docs/architecture/memory-contract.md)

## Summary

Add a **memory primitive** to the `agentic-workspace-claude-cli` image so any
orchestrator (agentic-domain-runner, Syntropic137, future) can attach a
memory backend (hindsight first, lossless-claw or others later) without
coupling to a specific provider. Pair it with a **doctor primitive** that
validates the contract is wired correctly, sniffs the backend is reachable,
and surfaces actionable diagnostics — automatically at container start
(soft-fail by default) and on-demand via a CLI subcommand.

The primitive extends the [Workspace Injection Contract](../../adrs/035-workspace-injection-contract.md)
(ADR-035) following the same shape: three env vars from the host, a baked-in
adapter layer inside the image, soft-fail-with-loud-logs as the default
posture.

## Goals

- **Provider-agnostic at the host layer.** Orchestrators set three env vars;
  they do not learn anything about hindsight specifics.
- **Adapter-driven at the image layer.** Per-provider translation logic lives
  in the image at `/opt/agentic/memory/<provider>/init.sh`, baked at build
  time.
- **Opting in is opting into hard-fail.** Setting `AGENTIC_MEMORY_PROVIDER`
  is the user's signal that memory matters. Misconfiguration exits the
  entrypoint non-zero. There is no soft-fail mode — if you don't want hard
  fail, don't set the provider.
- **Backwards compatible.** A workspace that doesn't set `AGENTIC_MEMORY_PROVIDER`
  is unaffected. Existing orchestrators don't need to change.
- **Durable audit trail.** Doctor writes one JSON line per run to a host-mounted
  log file. Operators can `tail`, `grep`, and dashboard the diagnostics across
  every container start.
- **Consistent with ADR-035 conventions** for env-var prefix, entrypoint-section
  pattern, and the bind-mount-driven primitive shape.

## Non-goals

- **Defining the upstream memory backend** (hindsight, lossless-claw, …) —
  those are external services; this primitive only wires *into* them.
- **Stacking multiple providers.** One workspace, one memory provider for
  v1. Stacking is a future concern.
- ~~**Cross-namespace recall configuration.** Hindsight's `recallAdditionalBanks`
  is config-file-only, not env-overridable; defer until the contract gains
  an `AGENTIC_MEMORY_CONFIG_JSON` consumer.~~ Shipped 2026-05-13: the
  adapter consumes `AGENTIC_MEMORY_CONFIG_JSON` and writes it verbatim to
  `~/.hindsight/claude-code.json`; agentic-domain-runner emits the JSON
  from a per-domain `[memory] recall_additional_banks` in `domain.toml`.
  E2E covered by `tests/integration/test_entrypoint_memory.py::test_config_json_writes_claude_code_config`.
- **Namespace lifecycle (creation/deletion).** The adapter assumes the
  backend lazy-creates on first retain. Tear-down is operator-side.
- **Replacing or wrapping `claude doctor`.** This doctor is scoped to the
  memory contract, not the broader Claude CLI install.

## Design

### Layer 1 — The Memory Contract (host → workspace image)

Three required env vars from the host, three optional:

| Env var | Required | Meaning |
|---|---|---|
| `AGENTIC_MEMORY_PROVIDER` | yes (to opt in) | provider name — `hindsight`, `lossless-claw`, `none`, … |
| `AGENTIC_MEMORY_NAMESPACE` | yes | host-supplied scope identifier (task ID, workflow ID, …) |
| `AGENTIC_MEMORY_URL` | yes (network providers) | base URL of provider backend, reachable from container |
| `AGENTIC_MEMORY_NAMESPACE_KIND` | no, default `task` | semantic hint — `task` \| `domain` \| `workflow` \| `user` \| `session` \| `project` \| `custom` |
| `AGENTIC_MEMORY_AUTH` | no | provider-specific token (passed verbatim) |
| `AGENTIC_MEMORY_CONFIG_JSON` | no | adapter-specific config (JSON, escape hatch) |

**No `AGENTIC_MEMORY_REQUIRED` flag.** Setting `AGENTIC_MEMORY_PROVIDER` is
the user's opt-in to memory; the contract treats that as the user's
authorization to fail loud on misconfiguration. If you want a workspace
without memory, don't set the provider — the entrypoint skips section 5.6
and 5.7 entirely, no doctor runs, no failure mode exists.

The host **never** sets provider-specific vars like `HINDSIGHT_BANK_ID`. That
mapping is the adapter's job.

### Layer 2 — Workspace image (the integration point)

#### Entrypoint extensions

Two new sections in
`providers/workspaces/claude-cli/scripts/entrypoint.sh`, after the existing
section 5.5 (workspace context composition):

**Section 5.6 — Memory adapter initialization**

```bash
# --- 5.6 Memory adapter initialization ---
if [ -n "${AGENTIC_MEMORY_PROVIDER:-}" ] && [ "${AGENTIC_MEMORY_PROVIDER}" != "none" ]; then
  adapter="/opt/agentic/memory/${AGENTIC_MEMORY_PROVIDER}/init.sh"
  if [ -f "${adapter}" ]; then
    echo "[entrypoint] memory adapter: ${AGENTIC_MEMORY_PROVIDER}"
    # shellcheck disable=SC1090
    if . "${adapter}"; then
      export AGENTIC_MEMORY_READY=1
    else
      echo "[entrypoint] memory adapter init failed; continuing without memory" >&2
    fi
  else
    echo "[entrypoint] no adapter for memory provider '${AGENTIC_MEMORY_PROVIDER}' (looked at ${adapter})" >&2
  fi
fi
```

**Section 5.7 — Memory doctor preflight**

```bash
# --- 5.7 Memory doctor preflight ---
if [ -n "${AGENTIC_MEMORY_PROVIDER:-}" ] && [ "${AGENTIC_MEMORY_PROVIDER}" != "none" ]; then
  # Full preflight: env-var contract, namespace shape, adapter file,
  # backend DNS + /health, provider-specific checks. Pretty text to stderr,
  # one-line JSON to the audit log on host bind-mount. Hard-fail on any
  # check failure — opting into memory means opting into loud failure.
  audit_dir="/var/agentic/memory-doctor"
  mkdir -p "${audit_dir}"
  audit_file="${audit_dir}/$(date -u +%Y-%m-%d).jsonl"
  if ! /opt/agentic/memory/doctor --json >> "${audit_file}" 2>&1; then
    echo "[entrypoint] memory doctor reported failure (audit: ${audit_file})" >&2
    exit 1
  fi
fi
```

`/var/agentic/memory-doctor/` is a host bind-mount the orchestrator provides
(see "Audit trail" below). If the orchestrator forgets the mount, the directory
is created as a normal container path and the log dies with the container —
not great, but the doctor's `--json` is still on stderr.

#### Per-provider adapter scripts

Layout:

```
providers/workspaces/claude-cli/
└── memory/
    ├── doctor                              # CLI entry (executable)
    ├── doctor.py                           # Doctor implementation (Python)
    ├── hindsight/
    │   ├── init.sh                         # Translates AGENTIC_MEMORY_* → HINDSIGHT_*
    │   └── doctor.sh                       # Provider-specific health checks
    └── lossless-claw/                      # (placeholder for future)
        └── init.sh
```

`hindsight/init.sh` is the canonical example:

```bash
#!/usr/bin/env bash
# Hindsight adapter — translates AGENTIC_MEMORY_* contract → HINDSIGHT_* env.

set -e

export HINDSIGHT_API_URL="${AGENTIC_MEMORY_URL}"
[ -n "${AGENTIC_MEMORY_AUTH:-}" ] && export HINDSIGHT_API_TOKEN="${AGENTIC_MEMORY_AUTH}"

# Bank scoping: HINDSIGHT_BANK_ID env override only takes effect when
# dynamicBankId=false (verified in hindsight/bank.py:97).
export HINDSIGHT_DYNAMIC_BANK_ID=false
export HINDSIGHT_BANK_ID="${AGENTIC_MEMORY_NAMESPACE}"

# Optional rich config.
if [ -n "${AGENTIC_MEMORY_CONFIG_JSON:-}" ]; then
  mkdir -p "${HOME}/.hindsight"
  printf '%s' "${AGENTIC_MEMORY_CONFIG_JSON}" > "${HOME}/.hindsight/claude-code.json"
fi
```

Adapter scripts are **deliberately small** (~30 lines). The doctor is where
validation logic lives — not duplicated per-adapter.

### Layer 3 — The Doctor

#### Invocation surface

```sh
# 1. Automatic preflight at container start (section 5.7 entrypoint)
#    Runs full checks. Hard-fail on any failure (exit 1).

# 2. Explicit on-demand from inside the container
/opt/agentic/memory/doctor [--fix] [--json] [--verbose] [--provider PROVIDER]
```

There is only one mode — full preflight. No `--quick`. Speed isn't the
priority; honesty is.

Flags:

| Flag | Behavior |
|---|---|
| (default) | Full checks. Pretty output to stderr; non-zero exit on failure. |
| `--fix` | Apply auto-correctable fixes. Dry-run by default; pair with `--apply` to commit. |
| `--apply` | Commit `--fix` changes (no-op without `--fix`). |
| `--json` | Machine-readable JSON to stdout. Pretty text always goes to stderr. |
| `--verbose` | Include adapter source, env-var values (redacted), backend response bodies, timings. |
| `--provider <name>` | Override `AGENTIC_MEMORY_PROVIDER` for this invocation. Useful for testing. |

Exit codes:

- `0` — all checks pass
- `1` — one or more checks failed (entrypoint exits non-zero with this; the
  container does not start)

There is no "warning" tier. A check is either fine or it's a failure. If a
condition only deserves a warning, it's a candidate for `--fix` auto-correction
instead.

#### Checks performed

Standard checks (the contract layer — provider-agnostic):

1. **`env_contract`** — `AGENTIC_MEMORY_PROVIDER`, `AGENTIC_MEMORY_NAMESPACE`,
   and `AGENTIC_MEMORY_URL` (when provider isn't `none`) are all set.
2. **`namespace_well_formed`** — `AGENTIC_MEMORY_NAMESPACE` matches
   `[a-zA-Z0-9._:-]+`. No spaces, no slashes, no shell metacharacters.
3. **`provider_known`** — `AGENTIC_MEMORY_PROVIDER` matches a directory under
   `/opt/agentic/memory/`.
4. **`adapter_exists`** — `/opt/agentic/memory/<provider>/init.sh` is a file
   and executable.
5. **`config_json_valid`** — if `AGENTIC_MEMORY_CONFIG_JSON` is set, it parses
   as JSON.

Backend checks (network):

6. **`backend_dns`** — hostname in `AGENTIC_MEMORY_URL` resolves.
7. **`backend_health`** — `GET <url>/health` returns 200.

Provider-specific checks (delegated to adapter's `doctor.sh`):

8. **`provider_specific`** — adapter's `doctor.sh` runs additional checks
   relevant to that provider. For hindsight: bank existence (`GET /banks/<id>`
   returns 200 or 404 — 404 is fine, lazy-create on first retain), plus the
   `dynamicBankId` consistency check (see check 9).

9. **`hindsight_config_consistency`** (hindsight only) — if
   `~/.hindsight/claude-code.json` exists inside the container with
   `dynamicBankId !== false`, the `HINDSIGHT_BANK_ID` env var the adapter
   set is silently ignored by the hindsight plugin (verified at hindsight
   `bank.py:97`). The doctor warns AND auto-fixes by rewriting the config
   file with `dynamicBankId: false` (the contract's intent).

#### Output schema (JSON)

```json
{
  "doctor_version": "1.0",
  "timestamp": "2026-05-13T01:42:00Z",
  "provider": "hindsight",
  "namespace": "task-abc",
  "status": "ok",
  "checks": [
    {
      "name": "env_contract",
      "status": "ok",
      "message": "All required env vars set."
    },
    {
      "name": "namespace_well_formed",
      "status": "ok",
      "value": "task-abc"
    },
    {
      "name": "provider_known",
      "status": "ok",
      "provider": "hindsight"
    },
    {
      "name": "adapter_exists",
      "status": "ok",
      "path": "/opt/agentic/memory/hindsight/init.sh"
    },
    {
      "name": "config_json_valid",
      "status": "skipped",
      "reason": "AGENTIC_MEMORY_CONFIG_JSON not set"
    },
    {
      "name": "backend_dns",
      "status": "ok",
      "host": "hindsight",
      "resolved_to": "172.18.0.4"
    },
    {
      "name": "backend_health",
      "status": "ok",
      "url": "http://hindsight:8888/health",
      "response_time_ms": 17
    },
    {
      "name": "provider_specific",
      "status": "ok",
      "details": {
        "bank_exists": false,
        "bank_will_lazy_create": true
      }
    }
  ],
  "warnings": [],
  "fixable": [],
  "exit_code": 0
}
```

Failure example (with auto-fixable issues):

```json
{
  "doctor_version": "1.0",
  "timestamp": "2026-05-13T01:42:00Z",
  "provider": "hindsight",
  "namespace": "task-abc",
  "status": "warning",
  "checks": [
    {
      "name": "namespace_well_formed",
      "status": "warn",
      "value": "task abc/v2",
      "message": "Namespace contains illegal characters (space, slash). Will be sanitized."
    },
    {
      "name": "backend_health",
      "status": "fail",
      "url": "http://hindsight:8888/health",
      "error": "connection refused"
    }
  ],
  "warnings": [
    {
      "code": "namespace_sanitization_required",
      "message": "AGENTIC_MEMORY_NAMESPACE='task abc/v2' will be sanitized to 'task-abc-v2'.",
      "fixable": true,
      "fix": "Set AGENTIC_MEMORY_NAMESPACE='task-abc-v2' explicitly."
    },
    {
      "code": "backend_unreachable",
      "message": "Hindsight backend at http://hindsight:8888 is unreachable.",
      "fixable": false,
      "fix": "Verify hindsight container is running and on the agentic-domain-runner Docker network."
    }
  ],
  "fixable": ["namespace_sanitization_required"],
  "exit_code": 2
}
```

#### Auto-fix scope

`--fix --apply` may auto-correct **client-side** issues:

- **Namespace sanitization** — strip illegal chars; result emitted as a
  suggested env var setting. Writes a `~/.agentic/memory.env` file with the
  corrected value (operator sources it themselves; we don't mutate the
  parent shell).
- **Config-file generation** — if `AGENTIC_MEMORY_CONFIG_JSON` is set,
  write it to the provider's expected path (e.g. `~/.hindsight/claude-code.json`).
- **Hindsight `dynamicBankId` correction** — if a stale
  `~/.hindsight/claude-code.json` exists with `dynamicBankId !== false`,
  rewrite the file with `dynamicBankId: false` so the contract's
  `HINDSIGHT_BANK_ID` env var actually takes effect. This is a stale-state
  issue, not an operator decision; silently fixing it preserves the
  contract's intent.

`--fix` **never** mutates the backend:
- Does not create banks
- Does not change provider state
- Does not POST anything

This is deliberate. The doctor is a client-side validator, not an admin tool.
Backend-mutating operations belong in provider-specific CLIs (e.g.
`hindsight-cli`).

### Layer 4 — Python helper library

Add `lib/python/agentic_memory/` for shared validation logic the doctor
script uses:

```
lib/python/agentic_memory/
├── pyproject.toml
├── agentic_memory/
│   ├── __init__.py
│   ├── contract.py            # Env-var parsing + namespace validation
│   ├── doctor.py              # Check definitions + runner
│   ├── providers.py           # Provider registry (introspects /opt/agentic/memory/)
│   └── output.py              # JSON + pretty formatters
└── tests/
    ├── test_contract.py
    ├── test_doctor.py
    └── test_providers.py
```

`contract.py` exports a `MemoryContract` dataclass parsed from env vars.
`doctor.py` exports `Check` (one of N), `CheckResult` (ok / warn / fail /
skipped), and a `run_checks(...)` orchestrator. `output.py` handles pretty
text and JSON.

The shell script `/opt/agentic/memory/doctor` is a thin entry that
`exec python -m agentic_memory.doctor "$@"`.

## Adoption by consumers (host orchestrators)

### agentic-domain-runner

In `src/runner/mod.rs` near the existing `AGENTIC_*` injection (~line 171):

```rust
req.env.push(("AGENTIC_MEMORY_PROVIDER".into(), "hindsight".into()));
req.env.push(("AGENTIC_MEMORY_URL".into(), "http://hindsight:8888".into()));
let ns = req.agent_task_id.as_deref().unwrap_or(&task_id);
req.env.push(("AGENTIC_MEMORY_NAMESPACE".into(), ns.to_string()));
req.env.push(("AGENTIC_MEMORY_NAMESPACE_KIND".into(), "task".into()));
```

Four lines. The runner doesn't know what hindsight is — it just plumbs the
contract through.

### Syntropic137 (hypothetical, when ready)

Same env-var contract. Identity model differs:

```python
env["AGENTIC_MEMORY_PROVIDER"] = "hindsight"
env["AGENTIC_MEMORY_URL"] = "http://hindsight.syntropic.svc:8888"
env["AGENTIC_MEMORY_NAMESPACE"] = f"{workflow_id}::{phase}"
env["AGENTIC_MEMORY_NAMESPACE_KIND"] = "workflow"
```

### Hermes Agent

**Not applicable** — Hermes already has a native hindsight integration shipped
upstream (announced 2026-04-06; setup is `hermes memory setup`). Hermes wires
hindsight in via its own plugin slot, not via the agentic-workspace-claude-cli
image. This contract is for the *workspace-image* path; Hermes uses a
different path entirely.

## Implementation plan (sketch — full plan is a separate doc)

Phased:

1. **Phase 1 — Contract + doctor skeleton** (no provider adapters yet).
   - Add Python lib `lib/python/agentic_memory/` with contract parser and
     doctor framework.
   - Implement standard checks 1-7 (env, namespace, adapter, backend).
   - Add `/opt/agentic/memory/doctor` entry in the workspace image
     Dockerfile.
   - Section 5.7 entrypoint integration (calls doctor, soft-fails).
   - Integration test: `tests/integration/test_entrypoint_memory_doctor.py`.
2. **Phase 2 — Hindsight adapter** (first real provider).
   - Add `providers/workspaces/claude-cli/memory/hindsight/init.sh` +
     `doctor.sh`.
   - Section 5.6 entrypoint integration.
   - Integration test: `tests/integration/test_entrypoint_memory_hindsight.py`.
3. **Phase 3 — Adoption in agentic-domain-runner** (a separate PR in that
   repo).
4. **Phase 4 — `--fix` mode** (deferred until phases 1-3 stabilize).
5. **Phase 5 — Second provider adapter** (lossless-claw or whatever ships
   next).

## Decisions locked

Locked 2026-05-13 after author review. All previously-open questions resolved:

1. **No `--quick` mode.** One doctor, one mode: full preflight. Speed isn't
   the priority; honesty is.
2. **No `AGENTIC_MEMORY_REQUIRED` flag.** Setting `AGENTIC_MEMORY_PROVIDER` is
   opt-in; opt-in is automatic hard-fail. If you don't want hard fail, don't
   set the provider — the entrypoint then skips memory entirely.
3. **Audit trail via host bind-mount** at `/var/agentic/memory-doctor/`.
   One JSONL file per day (`YYYY-MM-DD.jsonl`), appended one entry per
   container start.
4. **Hindsight `dynamicBankId` conflict is a check AND an auto-fix.** Doctor
   rewrites the stale config file with `dynamicBankId: false` so the
   contract's env var takes effect.
5. **No `claude doctor` integration.** Memory diagnostics are obtained by
   running `/opt/agentic/memory/doctor` directly. Wrappers, if needed, live
   in the orchestrator (e.g. an `agentic-domain-runner doctor` command can
   run both Claude's doctor and memory doctor in sequence).

## Test plan

Integration tests live at `tests/integration/`:

- `test_entrypoint_memory_doctor.py` — verifies section 5.7 fires, doctor
  reports correct status for various env-var combinations (all set / one
  missing / bad namespace / no backend), exit codes match spec.
- `test_entrypoint_memory_hindsight.py` — spawns a hindsight `external-pg`
  compose stack on a Docker network, joins workspace container, verifies
  end-to-end: section 5.6 sets `HINDSIGHT_BANK_ID`, section 5.7 doctor
  passes, retain → recall roundtrip via the plugin works.
- `lib/python/agentic_memory/tests/` — unit tests for each check.

## References

- [ADR-035 Workspace Injection Contract](../../adrs/035-workspace-injection-contract.md) — design baseline this extends.
- [agentic-memory/docs/architecture/memory-contract.md](../../../../agentic-memory/docs/architecture/memory-contract.md) — sibling design doc.
- [hindsight bank derivation modes probe](../../../../agentic-memory/experiments/2026-05-12--claude-code--hindsight--bank-derivation-modes/results.md) — empirical evidence that `HINDSIGHT_BANK_ID` env override requires `dynamicBankId=false`.
- [lossless-claw doctor-contract-api](../../../../agentic-memory/lib/lossless-claw/doctor-contract-api.js) — reference for `--fix` semantics.
- [hindsight-cli health command](../../../../agentic-memory/lib/hindsight/hindsight-cli/src/commands/health.rs) — reference for JSON/pretty dual output.
