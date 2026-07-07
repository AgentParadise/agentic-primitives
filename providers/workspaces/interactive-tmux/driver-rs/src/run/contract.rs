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
    /// Plan 3 observability exporters to fan telemetry out to. Empty by default.
    #[serde(default)]
    pub observability: Vec<ObservabilityExporter>,
    /// Optional run limits (timeout, token budget).
    #[serde(default)]
    pub limits: Option<AgentRunLimits>,
}

/// Per-harness credentials for the run. All fields optional - only the
/// harnesses actually exercised by the recipe need credentials supplied.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct AgentRunCredentials {
    #[serde(default)]
    pub claude: Option<ClaudeCredentials>,
    #[serde(default)]
    pub codex: Option<CodexCredentials>,
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

/// Plan 3 placeholder: an observability sink to fan run telemetry out to.
/// The shape is intentionally minimal (`name` + opaque `config`) until
/// Plan 3 defines concrete exporter configs (OTel, file, webhook, ...).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ObservabilityExporter {
    pub name: String,
    /// Opaque, exporter-specific configuration. Untyped by design - Plan 3
    /// will introduce a typed config per exporter kind.
    #[serde(default)]
    pub config: serde_json::Value,
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
    /// Plan 3 placeholder: aggregated observability data for the run.
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

/// Plan 3 placeholder: aggregated observability data attached to the final
/// `AgentRunResult`. Minimal until Plan 3 defines the real bundle shape.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ObservabilityBundle {
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub data: serde_json::Value,
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
        cost_usd: Option<f64>,
    },
    /// Terminal event - always the last event of a run, carrying the
    /// terminal outcome (mirrors `AgentRunResult.result`).
    #[serde(rename = "session_end")]
    SessionEnd { outcome: AgentRunOutcome },
}
