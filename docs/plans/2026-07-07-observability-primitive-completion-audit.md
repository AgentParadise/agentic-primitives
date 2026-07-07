# Observability Primitive Completion Audit

Date: 2026-07-07
Branch: `feat/observability-exporter-primitive`
PR: <https://github.com/AgentParadise/agentic-primitives/pull/256>

This audit maps the `.6` and `.9` requirements to current evidence. It is meant
to prevent status drift between the OKR board, ADR-038, the implementation plan,
and the experiment folders.

Authoritative design docs:

- `docs/adrs/038-modular-agent-observability.md`
- `docs/plans/2026-07-07-observability-primitive-implementation.md`
- `docs/guides/langfuse-observability-setup.md`

## Current Decision

`.6` is complete in the reusable primitive sense represented by PR #256:
normalized harness events can be observed, fanned out to backend-independent
file JSONL, reported in `ObservabilityBundle`, and kept isolated from backend
exporter failures.

`.9` is locally implemented and local-receiver-proven, but not complete. It remains gated
on a reachable LangFuse deployment plus real `LANGFUSE_*` setup. The close gate
is the refreshed ingestion smoke proving backend acceptance, trace
discoverability/queryability, and trace-link resolution through the current
`itmux codex-exec --observability-langfuse` path.

## `.6` Evidence Matrix

| Requirement | Status | Evidence | Notes |
|---|---|---|---|
| Typed exporter contract exists | Proven | `providers/workspaces/interactive-tmux/driver-rs/src/run/contract.rs`, `providers/workspaces/interactive-tmux/driver-rs/docs/contract/agent-run-spec.schema.json` | Includes `file` and `langfuse_otlp`; `.6` depends only on backend-independent file fanout. |
| Final result reports observability status | Proven | `ObservabilityBundle` and `ObservabilityExportReport` in `contract.rs`; `experiments/2026-07-07--observability--codex-exec-observer-wiring/results.md` | Reports status, target, event count, links, and errors. |
| File exporter works on normalized events | Proven | `experiments/2026-07-07--observability--codex-exec-observer-wiring/results.md`; `experiments/2026-07-07--observability--claude-hook-file-fanout/results.md` | Codex exec path proves runnable observer plus exporter parity; early Claude probe proves file parity even before hooks were visible. |
| Exporter failure isolation works | Proven | `experiments/2026-07-07--observability--mixed-exporter-isolation/results.md` | File exporter stayed `ok` while missing LangFuse config reported a failed backend exporter. |
| File link portability is covered | Proven | Commit `98f1310`; `providers/workspaces/interactive-tmux/driver-rs/tests/contract_json.rs`; ADR-038 validated gates | Relative paths remain relative; absolute paths produce `file://`; existing `file://` is preserved. |
| Harness observer boundary exists | Proven | `providers/workspaces/interactive-tmux/driver-rs/src/run/harness_observer.rs`; `experiments/2026-07-07--observability--codex-exec-observer-wiring/results.md` | First proven observer is `codex_exec_json`. |
| Codex usage/token surface is empirically scoped | Proven | `experiments/2026-07-07--observability--codex-token-cost-surface/results.md`; `experiments/2026-07-07--observability--codex-exec-observer-wiring/results.md` | `codex exec --json` is viable; interactive Codex TUI parity is not claimed. |
| Claude auth blocker is classified and fixed for Docker runs | Proven | `experiments/2026-07-07--observability--claude-credential-health/results.md`; `experiments/2026-07-07--observability--claude-env-token-passthrough/results.md` | Env token passthrough is by env name, not secret value in argv. |
| Claude hook capture works without stdout pollution | Proven | `experiments/2026-07-07--observability--claude-hook-sink-capture/results.md`; `plugins/observability/hooks/handlers/observe.py` | Hook JSONL is captured through `AGENTIC_EVENTS_JSONL` and normalized as `hook_event`. |
| Stock interactive-tmux packaging contains the observability runtime | Proven | `experiments/2026-07-07--observability--stock-itmux-hook-sink/results.md`; provider manifests | Stock image emitted normalized hook events without a temporary derived image. |
| CI validates the stacked PR | Proven | PR #256 checks: QA, Plugin Version Check, Rust `itmux`, Integration Gate, `Build: claude-cli`, `Build: interactive-tmux` | At last check, PR #256 was draft, stacked on PR #247, `mergeStateStatus = CLEAN`. |

## `.6` Non-Claims

These are intentionally not treated as `.6` blockers:

- Codex interactive TUI token/cost parity.
- Claude full token/cost parity.
- Real LangFuse backend ingestion.
- Agent trace-query utilities over LangFuse.

Those belong to `.9`, `.10`, or the OTEL agentic standard work.

## `.9` Evidence Matrix

| Requirement | Status | Evidence | Notes |
|---|---|---|---|
| LangFuse is represented as a backend exporter, not a per-harness plugin | Proven locally | ADR-038; `ObservabilityExporter::LangFuseOtlp`; `experiments/2026-07-07--langfuse--exporter-config-failfast/results.md` | Preserves harness/backend separation. |
| Endpoint derivation and Basic auth construction work | Local-receiver-proven | `experiments/2026-07-07--langfuse--otel-preflight-local-receiver/results.md`; Rust unit tests in `observability.rs` | Supports origin, `/api/public/otel`, and `/api/public/otel/v1/traces` inputs. |
| Missing config fails safely without leaking secrets | Proven | `experiments/2026-07-07--langfuse--exporter-config-failfast/results.md`; `experiments/2026-07-07--langfuse--cli-runtime-failfast/results.md` | Failure is reported in `ObservabilityExportReport`, not stdout corruption. |
| OTLP HTTP/protobuf transport works against a receiver | Local-receiver-proven | `experiments/2026-07-07--langfuse--otlp-transport-local-receiver/results.md` | Sends protobuf body with Basic auth and `x-langfuse-ingestion-version: 4`; local receiver 2xx reports `ok`. |
| Trace links can be reported when project id is known | Local-receiver-proven | `experiments/2026-07-07--langfuse--trace-link-reporting/results.md` | Real URL resolution is still pending real backend ingestion. |
| CLI setup exists for `itmux run` and `itmux codex-exec` | Proven locally | `experiments/2026-07-07--langfuse--cli-setup-path/results.md`; driver README | Public/secret keys remain env refs. |
| Mixed local+LangFuse export is safe during setup | Proven | `experiments/2026-07-07--observability--mixed-exporter-isolation/results.md` | Local file JSONL remains complete when LangFuse is absent. |
| Repeatable real-backend smoke runner exists | Proven | `experiments/2026-07-07--langfuse--otel-ingestion-smoke/run-smoke.sh`; `scripts/langfuse-local.sh`; `runs/real-backend-smoke/summary.txt` | Wrapper starts the local LangFuse Docker Compose stack, seeds ignored local env, exports the current `itmux` path, polls queryability, and checks trace URL resolution. |
| Agent trace-query integration exists | Proven locally/local-receiver-proven | `itmux langfuse-trace`; `experiments/2026-07-07--langfuse--trace-query-cli/results.md` | The command derives trace id from run id, queries bounded Observations API v2 rows or a legacy trace endpoint for self-host compatibility, fails safely when query config is absent, and the actual CLI GET/auth/JSON path is proven against a local receiver. |
| Real LangFuse backend accepts traces | Proven on local Docker Compose | `experiments/2026-07-07--langfuse--otel-ingestion-smoke/results.md`; `runs/real-backend-smoke/result.json` | Local LangFuse v3 Docker Compose accepted OTLP HTTP/protobuf export and reported `status=ok`, `events_exported=6`. |
| Trace is discoverable/queryable in LangFuse | Proven on local Docker Compose | `runs/real-backend-smoke/langfuse-trace-query-legacy.json` | `itmux langfuse-trace --api legacy-trace` returned the trace with 7 observations. Observations API v2 returned the expected v3/v4-mode 404. |
| Trace link resolves in real LangFuse UI | Proven on local Docker Compose | `runs/real-backend-smoke/trace-ui-response.txt` | Emitted trace URL returned HTTP 200. |

## `.9` Required Next Proof

1. Load a real LangFuse configuration using
   `docs/guides/langfuse-observability-setup.md`.
2. Rerun
   `experiments/2026-07-07--langfuse--otel-ingestion-smoke/run-smoke.sh`
   against LangFuse Cloud or the planned Mac Mini self-host.
3. Run the current `itmux codex-exec --observability-langfuse` smoke against
   that backend.
4. Capture redacted evidence that:
   - `langfuse_otlp` reports `status = ok`;
   - `events_exported > 0`;
   - the backend trace is visible/queryable by run id via `itmux langfuse-trace`;
   - at least three child observations are present;
   - the trace link resolves when project metadata is configured.
5. Only then close `.9` or claim production LangFuse readiness.

## Stack State

At the last verification pass, the relevant GitHub stack was:

| PR | Branch | Base | State |
|---|---|---|---|
| #240 | `feat/workspace-run` | `main` | clean, CI green |
| #243 | `feat/itmux-production-parity` | `main` | clean, CI green |
| #247 | `feat/itmux-run-contract` | `feat/itmux-production-parity` | clean, CI green |
| #250 | `feat/itmux-python-client` | `feat/itmux-run-contract` | clean, CI green |
| #252 | `feat/itmux-eval` | `feat/itmux-run-contract` | clean, CI green |
| #254 | `feat/itmux-env-credentials` | `feat/itmux-run-contract` | clean, CI green |
| #256 | `feat/observability-exporter-primitive` | `feat/itmux-run-contract` | draft, clean, CI green |

The PR stack order, not implementation evidence, is the remaining merge
coordination issue for `.6`.
