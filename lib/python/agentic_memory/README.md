# agentic-memory

Memory primitive contract + doctor for `agentic-workspace-claude-cli`.
Implements [ADR-036](../../../docs/adrs/036-memory-primitive-and-doctor.md)
and the matching [design spec](../../../docs/superpowers/specs/2026-05-13-memory-primitive-and-doctor-design.md).

## Contract

Three required env vars from the host:

- `AGENTIC_MEMORY_PROVIDER` — provider name (`hindsight`, `lossless-claw`, `none`, …)
- `AGENTIC_MEMORY_NAMESPACE` — host-supplied scope identifier
- `AGENTIC_MEMORY_URL` — base URL of provider backend, reachable from container

Three optional:

- `AGENTIC_MEMORY_NAMESPACE_KIND` — `task` | `domain` | `workflow` | `user` | `session` | `project` | `custom`
- `AGENTIC_MEMORY_AUTH` — provider-specific token
- `AGENTIC_MEMORY_CONFIG_JSON` — adapter-specific config (JSON, escape hatch)

Setting `AGENTIC_MEMORY_PROVIDER` is the user's opt-in to memory; opting in is
opting into hard-fail on misconfiguration. There is no soft-fail mode.

## Doctor

CLI at `/opt/agentic/memory/doctor` (also available as `agentic-memory-doctor`
on the Python path).

```sh
agentic-memory-doctor                 # full preflight; pretty output, exit 0 or 1
agentic-memory-doctor --json          # JSON to stdout, pretty to stderr
agentic-memory-doctor --fix --apply   # auto-correct client-side issues
agentic-memory-doctor --verbose       # extra diagnostics
agentic-memory-doctor --provider hindsight   # override provider for testing
```

Exit codes:

- `0` — all checks pass
- `1` — one or more checks failed

## Standard checks

1. `env_contract` — required env vars set
2. `namespace_well_formed` — namespace matches `[a-zA-Z0-9._:-]+`
3. `provider_known` — provider exists under `/opt/agentic/memory/`
4. `adapter_exists` — `<provider>/init.sh` is an executable file
5. `config_json_valid` — `AGENTIC_MEMORY_CONFIG_JSON` parses (when set)
6. `backend_dns` — `AGENTIC_MEMORY_URL` hostname resolves
7. `backend_health` — `GET <url>/health` returns 200
8. `provider_specific` — delegated to `<provider>/doctor.sh`

## Audit log

When the doctor is invoked from the workspace entrypoint (section 5.7), the
JSON output is appended to `/var/agentic/memory-doctor/YYYY-MM-DD.jsonl`. The
orchestrator is expected to bind-mount this directory from the host so logs
survive container teardown.
