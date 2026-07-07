//! The `itmux run` JSON contract: `AgentRunSpec` (request), `AgentRunResult`
//! (final response), and `AgentRunEvent` (the JSONL stream emitted on stdout
//! while a run executes).
//!
//! Authoritative source: `docs/design/plans/2026-07-07-planB-itmux-run-rust-
//! contract.md`, Task 1, as amended by the codex plan-review revisions:
//!
//! - **R4**: `recipe` is a directory `PathBuf` ONLY in v1. There is no inline
//!   recipe representation - a recipe that runs is a recipe that validates
//!   against the Plan A directory schema (loaded by a later Plan B task).
//! - **R6**: every event on stdout is one `AgentRunEvent` JSON object per
//!   line: `{run_id, seq, ts, type: <tag>, ...payload fields}`. The envelope
//!   is `run_id`/`seq`/`ts` plus a `type`-tagged payload (`AgentRunEventPayload`,
//!   an internally-tagged enum on `type`), flattened into the envelope so the
//!   wire shape is one flat JSON object rather than a nested `payload` key.
//!
//! All request/response structs use `#[serde(deny_unknown_fields)]` so a
//! typo'd or stale field fails loudly instead of being silently ignored.
//!
//! Deviation note (documented, not a bug): serde forbids combining
//! `#[serde(flatten)]` with `#[serde(deny_unknown_fields)]` on the SAME
//! struct (the flatten buffering mechanism cannot detect unknown keys ahead
//! of handing them to the flattened field's `Deserialize` impl). `AgentRunEvent`
//! therefore cannot carry `deny_unknown_fields` directly. Unknown-field
//! rejection is preserved in practice because the flattened field
//! (`AgentRunEventPayload`) is an internally-tagged enum whose variants DO
//! carry `deny_unknown_fields` - any key that is not `run_id`/`seq`/`ts` and
//! not a field of the tagged variant is rejected when the variant is
//! deserialized. See `agent_run_event_rejects_unknown_top_level_field` in
//! `tests/contract_json.rs` for the behavioral proof.

use std::collections::BTreeMap;
use std::path::PathBuf;

use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

/// Request to `itmux run`: run a recipe's default agent against `task`.
///
/// R4 (authoritative): `recipe` is always a directory path in v1 - loaded via
/// the Plan A recipe-directory schema by a later Plan B task. There is no
/// inline-recipe variant; adding one is a future contract version with its
/// own schema and compatibility tests.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct AgentRunSpec {
    /// Path to a recipe directory (Plan A shape). NOT an inline recipe.
    pub recipe: PathBuf,
    /// The task text handed to the default agent.
    pub task: String,
    /// Paths to input artifacts to stage into the workspace before the run.
    #[serde(default)]
    pub input_artifacts: Vec<PathBuf>,
    /// Per-harness credentials. Empty by default (no credentials configured).
    #[serde(default)]
    pub credentials: AgentRunCredentials,
    /// Observability exporters to fan normalized run telemetry out to. Empty by default.
    #[serde(default)]
    pub observability: Vec<ObservabilityExporter>,
    /// Optional run limits (timeout, token budget).
    #[serde(default)]
    pub limits: Option<AgentRunLimits>,
}

/// Per-harness credentials for the run. All fields optional - only the
/// harnesses actually exercised by the recipe need credentials supplied.
///
/// # Secrets travel here, never in argv (security-critical)
///
/// Every field on this struct carries credential MATERIAL (token contents,
/// `auth.json` bytes, raw env-var values). The executor injects them into the
/// container ONLY over the base64-over-stdin `docker exec` transfer and, at
/// launch, via an in-container `0600` env file the harness pane `source`s
/// before `exec`ing the CLI. No credential value ever reaches a `docker
/// run`/`docker exec` argv or a `tmux` command line - argv is world-readable
/// via `ps` / `/proc/<pid>/cmdline`; stdin and a `0600` file are not. The
/// `secret_env` redaction test (`tests/secret_redaction.rs`) is the load-
/// bearing guard for that invariant.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct AgentRunCredentials {
    #[serde(default)]
    pub claude: Option<ClaudeCredentials>,
    #[serde(default)]
    pub codex: Option<CodexCredentials>,
    /// Generic, harness-neutral secret environment variables (R2). Populated
    /// by the `.env`/process-env loader with an ALLOWLISTED set of names only
    /// (`CLAUDE_CODE_OAUTH_TOKEN`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`). The
    /// executor routes each var to the relevant harness pane's sourced `0600`
    /// env file; values never touch argv. Empty by default. A `BTreeMap` so the
    /// serialized order is deterministic (stable schema round-trips).
    #[serde(default)]
    pub secret_env: BTreeMap<String, String>,
}

/// Claude Code credentials. `oauth_token` is the token CONTENTS, not a path.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ClaudeCredentials {
    pub oauth_token: String,
}

/// Codex CLI credentials. `auth_json` is the CONTENTS of `auth.json`, not a
/// filesystem path - the caller supplies the credential material inline so
/// the contract has no dependency on the host filesystem layout.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct CodexCredentials {
    pub auth_json: String,
}

/// Run limits enforced by the orchestrator (a later Plan B task).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct AgentRunLimits {
    /// Wall-clock timeout, in seconds, for the whole run.
    #[serde(default)]
    pub timeout_s: Option<f64>,
    /// Soft token budget for the run. Enforcement is a later Plan B task.
    #[serde(default)]
    pub token_budget: Option<u64>,
}

/// An observability sink that receives the normalized [`AgentRunEvent`] stream.
/// Exporters are configured per run and are deliberately filesystem/env
/// portable: the same spec can point at a host path on a Mac/VPS or a mounted
/// path inside a Docker workspace.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum ObservabilityExporter {
    /// Append one JSON-serialized [`AgentRunEvent`] per line to `path`.
    File {
        path: PathBuf,
        /// Stable label surfaced in the final observability bundle for UIs.
        #[serde(default)]
        label: Option<String>,
    },
    /// Export run events to LangFuse's OTLP HTTP traces endpoint.
    ///
    /// Secrets are intentionally referenced by environment variable names, not
    /// embedded in the run spec. `base_url` may be either the LangFuse origin
    /// (`https://cloud.langfuse.com`), the OTLP base endpoint
    /// (`.../api/public/otel`), or the signal-specific traces endpoint
    /// (`.../api/public/otel/v1/traces`).
    #[serde(rename = "langfuse_otlp")]
    LangFuseOtlp {
        #[serde(default)]
        base_url: Option<String>,
        #[serde(default = "default_langfuse_public_key_env")]
        public_key_env: String,
        #[serde(default = "default_langfuse_secret_key_env")]
        secret_key_env: String,
        #[serde(default = "default_langfuse_environment_env")]
        environment_env: String,
        #[serde(default = "default_langfuse_service_name")]
        service_name: String,
        #[serde(default)]
        label: Option<String>,
    },
}

impl ObservabilityExporter {
    pub fn kind(&self) -> &'static str {
        match self {
            Self::File { .. } => "file",
            Self::LangFuseOtlp { .. } => "langfuse_otlp",
        }
    }
}

fn default_langfuse_public_key_env() -> String {
    "LANGFUSE_PUBLIC_KEY".to_string()
}

fn default_langfuse_secret_key_env() -> String {
    "LANGFUSE_SECRET_KEY".to_string()
}

fn default_langfuse_environment_env() -> String {
    "LANGFUSE_TRACING_ENVIRONMENT".to_string()
}

fn default_langfuse_service_name() -> String {
    "agentic-primitives".to_string()
}

/// Aggregated observability export status attached to the final result.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ObservabilityBundle {
    #[serde(default)]
    pub exporters: Vec<ObservabilityExportReport>,
}

/// Final status for one configured observability exporter.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ObservabilityExportReport {
    pub kind: String,
    pub status: ObservabilityExportStatus,
    #[serde(default)]
    pub target: Option<String>,
    #[serde(default)]
    pub events_exported: u64,
    #[serde(default)]
    pub links: Vec<ObservabilityLink>,
    #[serde(default)]
    pub error: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum ObservabilityExportStatus {
    Ok,
    Failed,
}

/// A consumer-facing location for an exported observability view or artifact.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ObservabilityLink {
    pub label: String,
    pub uri: String,
}

/// Terminal result of `itmux run`, emitted once after the run finishes
/// (success, failure, timeout, or cancellation).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct AgentRunResult {
    pub result: AgentRunOutcome,
    /// Paths to output artifacts collected from the workspace.
    #[serde(default)]
    pub output_artifacts: Vec<PathBuf>,
    /// The captured pane / session transcript.
    pub session_log: String,
    /// Aggregated status for configured observability exporters.
    #[serde(default)]
    pub observability: Option<ObservabilityBundle>,
}

/// The success/failure verdict for a run (also carried by the terminal
/// `session_end` event - see `AgentRunEventPayload::SessionEnd`).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct AgentRunOutcome {
    pub success: bool,
    pub summary: String,
}

/// One line of the `itmux run` event stream (R6): `run_id`/`seq`/`ts` plus a
/// `type`-tagged payload, flattened into a single JSON object so each line
/// is exactly one event. `seq` is monotonic from 0, no gaps; exactly one
/// `session_end` is emitted per run, always last (enforced by the
/// orchestrator, a later Plan B task - not by this struct).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
pub struct AgentRunEvent {
    pub run_id: String,
    pub seq: u64,
    /// RFC3339 timestamp.
    pub ts: String,
    #[serde(flatten)]
    pub payload: AgentRunEventPayload,
}

impl AgentRunEvent {
    /// Build the final-result DELIVERY event that wraps `result` in a valid
    /// `AgentRunEvent` envelope (R6 stdout purity - see
    /// [`AgentRunEventPayload::Result`]).
    pub fn result(
        run_id: impl Into<String>,
        seq: u64,
        ts: impl Into<String>,
        result: AgentRunResult,
    ) -> Self {
        Self {
            run_id: run_id.into(),
            seq,
            ts: ts.into(),
            payload: AgentRunEventPayload::Result {
                result: Box::new(result),
            },
        }
    }
}

/// The `type`-tagged event payload. Internally tagged on `type` so the wire
/// shape reads `{"type": "tool_start", "tool_name": "...", ...}`.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(tag = "type", deny_unknown_fields)]
pub enum AgentRunEventPayload {
    #[serde(rename = "tool_start")]
    ToolStart {
        tool_name: String,
        #[serde(default)]
        tool_input: serde_json::Value,
    },
    #[serde(rename = "tool_end")]
    ToolEnd {
        tool_name: String,
        #[serde(default)]
        success: bool,
        #[serde(default)]
        output_summary: Option<String>,
    },
    #[serde(rename = "token_usage")]
    TokenUsage {
        input_tokens: u64,
        output_tokens: u64,
        #[serde(default)]
        cached_input_tokens: Option<u64>,
        #[serde(default)]
        reasoning_output_tokens: Option<u64>,
        #[serde(default)]
        cost_usd: Option<f64>,
    },
    #[serde(rename = "hook_event")]
    HookEvent {
        provider: String,
        event_type: String,
        event: serde_json::Value,
    },
    /// Terminal LIFECYCLE event - the last lifecycle event of a run, carrying
    /// the terminal outcome (mirrors `AgentRunResult.result`).
    #[serde(rename = "session_end")]
    SessionEnd { outcome: AgentRunOutcome },
    /// Final-result DELIVERY envelope. Carries the full [`AgentRunResult`] as a
    /// valid `AgentRunEvent` so a consumer reading the stdout stream can treat
    /// EVERY line as an `AgentRunEvent` (R6: stdout is pure event JSONL). Emitted
    /// once, after `session_end`, only when the CLI is not writing the result to
    /// a `--result-file`. Boxed to keep the enum small.
    #[serde(rename = "result")]
    Result { result: Box<AgentRunResult> },
}
