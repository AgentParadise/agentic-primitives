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

`.9` has two proven pieces, but is not complete. The Rust OTLP fallback path is
locally implemented and proven against local Docker Compose. The official
LangFuse Claude/Codex plugin path is proven by direct local hook invocation
against the same backend, and is now the canonical rich-trace path for those
harnesses. The default noise-control guard is also proven for `itmux`: truthy
`TRACE_TO_LANGFUSE` suppresses Rust OTLP while preserving file JSONL unless
`--observability-langfuse-force` is supplied. The direct CLI/MCP trace-summary
read path is proven against real local official-plugin traces. The remaining
close gate is durable setup across the target deployment surfaces
(MacBook/Mac Mini/VPS/Docker workspace), including the Claude stored-config
caveat and discovery/filter polish for learning-loop reports against LangFuse
Cloud or the planned Mac Mini self-host.

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
| Official LangFuse plugins are canonical for rich Claude/Codex traces | Proven locally | ADR-038; `experiments/2026-07-08--langfuse--official-plugin-trace-shape`; `experiments/2026-07-08--langfuse--official-plugin-e2e-local` | Claude and Codex official plugins emitted LangFuse-native turns, generations, tools, input/output, and Codex cost/usage against local Docker Compose. |
| Official marketplace plugins trace real local sessions | Proven locally with caveat | `experiments/2026-07-08--langfuse--official-plugin-real-session` | Marketplace-installed official plugins produced real local LangFuse traces without fallback Rust OTLP: Claude `0e553fc833c71639acd03be9807eb616`, Codex `b3d2561d7c0557c12fd427c02a16e2f3`. Caveat: Claude install-time `--config` reported values unset; successful run used env fallback. |
| Single-active-rich-exporter guard exists in `itmux` CLI | Proven locally | `experiments/2026-07-08--langfuse--single-rich-exporter-guard` | `TRACE_TO_LANGFUSE=true` suppresses Rust `langfuse_otlp`, preserves file JSONL, and `--observability-langfuse-force` restores fallback OTLP for deliberate collector/Syntropic137 use. |
| Syntropic137 local projection exporter exists | Proven locally | `experiments/2026-07-08--syntropic137--jsonl-fanout-compat`; `ObservabilityExporter::SyntropicJsonl` | Current `AgentRunEvent` JSONL is not direct-compatible with Syntropic137 HookWatcher. `syntropic_jsonl` emits hook-style session/tool rows without changing canonical file JSONL or requiring fallback LangFuse OTLP. |
| Rust OTLP remains available as fallback/collector exporter | Proven locally | ADR-038; `ObservabilityExporter::LangFuseOtlp`; `experiments/2026-07-07--langfuse--exporter-config-failfast/results.md` | Preserves backend-independent fanout for local smoke, Syntropic137/collector use, and unsupported harnesses. |
| Endpoint derivation and Basic auth construction work | Local-receiver-proven | `experiments/2026-07-07--langfuse--otel-preflight-local-receiver/results.md`; Rust unit tests in `observability.rs` | Supports origin, `/api/public/otel`, and `/api/public/otel/v1/traces` inputs. |
| Missing config fails safely without leaking secrets | Proven | `experiments/2026-07-07--langfuse--exporter-config-failfast/results.md`; `experiments/2026-07-07--langfuse--cli-runtime-failfast/results.md` | Failure is reported in `ObservabilityExportReport`, not stdout corruption. |
| OTLP HTTP/protobuf transport works against a receiver | Local-receiver-proven | `experiments/2026-07-07--langfuse--otlp-transport-local-receiver/results.md` | Sends protobuf body with Basic auth and `x-langfuse-ingestion-version: 4`; local receiver 2xx reports `ok`. |
| Trace links can be reported when project id is known | Local-receiver-proven | `experiments/2026-07-07--langfuse--trace-link-reporting/results.md` | Real URL resolution is still pending real backend ingestion. |
| CLI setup exists for `itmux run` and `itmux codex-exec` | Proven locally | `experiments/2026-07-07--langfuse--cli-setup-path/results.md`; driver README | Public/secret keys remain env refs. |
| Mixed local+LangFuse export is safe during setup | Proven | `experiments/2026-07-07--observability--mixed-exporter-isolation/results.md` | Local file JSONL remains complete when LangFuse is absent. |
| Repeatable fallback backend smoke runner exists | Proven | `experiments/2026-07-07--langfuse--otel-ingestion-smoke/run-smoke.sh`; `scripts/langfuse-local.sh`; `runs/real-backend-smoke/summary.txt` | Wrapper starts the local LangFuse Docker Compose stack, seeds ignored local env, exports the Rust OTLP fallback path, polls queryability, and checks trace URL resolution. |
| Agent trace-query integration exists | Proven locally/local-receiver-proven | `itmux langfuse-trace`; `experiments/2026-07-07--langfuse--trace-query-cli/results.md` | The command derives trace id from run id, queries bounded Observations API v2 rows or a legacy trace endpoint for self-host compatibility, fails safely when query config is absent, and the actual CLI GET/auth/JSON path is proven against a local receiver. |
| Real LangFuse backend accepts fallback OTLP traces | Proven on local Docker Compose | `experiments/2026-07-07--langfuse--otel-ingestion-smoke/results.md`; `runs/real-backend-smoke/result.json` | Local LangFuse v3 Docker Compose accepted OTLP HTTP/protobuf export and reported `status=ok`, `events_exported=6`. |
| Real LangFuse backend accepts official-plugin rich traces | Proven on local Docker Compose | `experiments/2026-07-08--langfuse--official-plugin-e2e-local/results.md`; `experiments/2026-07-08--langfuse--official-plugin-real-session/results.md` | Direct-hook traces `76a54f7c977ae138c22ebae34b05e047` / `6905cfb7d1b969a0214e613383748ce7` and real-session traces `0e553fc833c71639acd03be9807eb616` / `b3d2561d7c0557c12fd427c02a16e2f3` were discoverable with root input/output, generation observations, tool observations, and usage/cost where available. |
| Runtime noise guard preserves JSONL while suppressing fallback OTLP | Proven locally | `experiments/2026-07-08--langfuse--runtime-noise-guard` | With `TRACE_TO_LANGFUSE=true`, `itmux claude-transcript --observability-langfuse` sent zero OTLP receiver requests while file and Syntropic137 JSONL each exported 7 events. Adding `--observability-langfuse-force` sent exactly one OTLP POST and kept both JSONL exporters `ok`. |
| Official-plugin tool observations are visible through CLI/MCP summaries | Proven locally | `experiments/2026-07-08--langfuse--official-plugin-tool-rollups`; `experiments/2026-07-08--langfuse--runtime-noise-guard/runs/real-langfuse-*-summary.json` | Claude real trace reports `agent_tools.names: ["Read"]`; Codex real trace reports `agent_tools.names: ["exec_command"]`, with usage/cost and generation counts from the real LangFuse backend. |
| Portable setup doctor exists for MacBook/VPS/Docker readiness | Proven locally | `experiments/2026-07-08--langfuse--portable-setup-doctor`; `experiments/2026-07-08--langfuse--doctor-minimal-env-portability`; `experiments/2026-07-08--langfuse--doctor-workspace-image`; `scripts/langfuse-observability-doctor.sh` | Read-only preflight reports official Claude/Codex prerequisites, `LANGFUSE_*` set/missing state, JSONL/Syntropic137 fanout, MCP presence, and the focused OTLP noise-guard test without printing credentials. Minimal shell mode no longer requires `rg`; `--no-tests` supports VPS/Docker shells without Cargo; the command runs successfully inside `agentic-workspace-interactive-tmux:latest` with the repo mounted read-only. |
| Codex plugin-hooks setup caveat is diagnosable | Proven locally | `experiments/2026-07-08--langfuse--codex-plugin-hooks-doctor`; `scripts/langfuse-observability-doctor.sh`; `docs/guides/langfuse-observability-setup.md` | The doctor now reports checked Codex config paths, whether `plugin_hooks = true` was found, whether the official tracing plugin is enabled, and the exact `[features]` remediation without mutating user config or printing secrets. |
| Trace is discoverable/queryable in LangFuse | Proven on local Docker Compose | `runs/real-backend-smoke/langfuse-trace-query-legacy.json` | `itmux langfuse-trace --api legacy-trace` returned the trace with 7 observations. Observations API v2 returned the expected v3/v4-mode 404. |
| Trace link resolves in real LangFuse UI | Proven on local Docker Compose | `runs/real-backend-smoke/trace-ui-response.txt` | Emitted trace URL returned HTTP 200. |

## `.9` Required Next Proof

1. Load a real LangFuse configuration using
   `docs/guides/langfuse-observability-setup.md`.
2. Make the official Claude/Codex plugin setup durable across MacBook, VPS, and
   Docker workspace paths, including the Claude stored-config caveat from
   `experiments/2026-07-08--langfuse--official-plugin-real-session`.
   `scripts/langfuse-observability-doctor.sh` now covers read-only readiness
   checks and Codex plugin-hooks remediation guidance; remaining work is
   target-machine remediation/installation, not detecting the setup state.
3. Keep the agent-facing summary path counting official-plugin `TOOL`
   observations, not only agentic-primitives metadata-shaped tool events:
   **done for direct CLI/MCP trace summaries by
   `experiments/2026-07-08--langfuse--official-plugin-tool-rollups`**.
4. Keep JSONL enabled for local evidence where useful, but leave the Rust
   `--observability-langfuse` writer off for those same real sessions unless
   explicitly testing fallback OTLP.
5. Capture redacted evidence that:
   - the official-plugin traces are visible/queryable;
   - root input/output and observation input/output are populated;
   - at least one `GENERATION` observation has native usage/cost where the
     harness transcript provides usage;
   - tool observations have meaningful names and payloads;
   - the traces can be pulled through `itmux langfuse-trace` and the
     `agentic-langfuse` MCP server for learning-loop use.
   **done locally for direct trace-summary reads and discovery-driven
   learning-loop filtering by
   `experiments/2026-07-08--langfuse--official-plugin-discovery-report`.**
6. Only then close `.9` or claim production LangFuse readiness. The fallback
   OTLP smoke remains a separate regression for collector/exporter health.

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
