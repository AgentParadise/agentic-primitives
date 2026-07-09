//! Reusable observability fanout for `itmux run`.
//!
//! The orchestrator stays focused on run lifecycle. This layer consumes the
//! normalized `AgentRunEvent` stream and exports it to configured sinks, while
//! accumulating exporter status for the final `AgentRunResult`.

use std::fs::{File, OpenOptions};
use std::io::{self, Write};
use std::path::{Path, PathBuf};

use crate::run::contract::{
    AgentRunEvent, AgentRunEventPayload, ObservabilityBundle, ObservabilityExportReport,
    ObservabilityExportStatus, ObservabilityExporter, ObservabilityLink,
};
use serde_json::json;

pub struct ObservabilityFanout {
    sinks: Vec<ExporterState>,
}

enum ExporterSink {
    File(File),
    SyntropicJsonl(File),
    Disabled,
}

struct ExporterState {
    kind: String,
    target: Option<String>,
    label: String,
    sink: ExporterSink,
    events_exported: u64,
    error: Option<String>,
}

impl ObservabilityFanout {
    pub fn new(exporters: &[ObservabilityExporter]) -> Self {
        let sinks = exporters.iter().map(ExporterState::from_config).collect();
        Self { sinks }
    }

    pub fn emit(&mut self, event: &AgentRunEvent) {
        for sink in &mut self.sinks {
            sink.emit(event);
        }
    }

    pub fn is_empty(&self) -> bool {
        self.sinks.is_empty()
    }

    pub fn finish(self) -> Option<ObservabilityBundle> {
        if self.is_empty() {
            return None;
        }
        Some(ObservabilityBundle {
            exporters: self.sinks.into_iter().map(ExporterState::report).collect(),
        })
    }
}

impl ExporterState {
    fn from_config(config: &ObservabilityExporter) -> Self {
        match config {
            ObservabilityExporter::File { path, label } => match open_jsonl(path) {
                Ok(file) => Self {
                    kind: config.kind().to_string(),
                    target: Some(path.display().to_string()),
                    label: label.clone().unwrap_or_else(|| "run events".to_string()),
                    sink: ExporterSink::File(file),
                    events_exported: 0,
                    error: None,
                },
                Err(err) => Self {
                    kind: config.kind().to_string(),
                    target: Some(path.display().to_string()),
                    label: label.clone().unwrap_or_else(|| "run events".to_string()),
                    sink: ExporterSink::Disabled,
                    events_exported: 0,
                    error: Some(err.to_string()),
                },
            },
            ObservabilityExporter::SyntropicJsonl { path, label } => match open_jsonl(path) {
                Ok(file) => Self {
                    kind: config.kind().to_string(),
                    target: Some(path.display().to_string()),
                    label: label
                        .clone()
                        .unwrap_or_else(|| "syntropic events".to_string()),
                    sink: ExporterSink::SyntropicJsonl(file),
                    events_exported: 0,
                    error: None,
                },
                Err(err) => Self {
                    kind: config.kind().to_string(),
                    target: Some(path.display().to_string()),
                    label: label
                        .clone()
                        .unwrap_or_else(|| "syntropic events".to_string()),
                    sink: ExporterSink::Disabled,
                    events_exported: 0,
                    error: Some(err.to_string()),
                },
            },
        }
    }

    fn emit(&mut self, event: &AgentRunEvent) {
        match &mut self.sink {
            ExporterSink::File(file) => {
                let result = serde_json::to_writer(&mut *file, event)
                    .and_then(|()| file.write_all(b"\n").map_err(serde_json::Error::io))
                    .and_then(|()| file.flush().map_err(serde_json::Error::io));
                match result {
                    Ok(()) => {
                        self.events_exported += 1;
                    }
                    Err(err) => {
                        self.error = Some(err.to_string());
                        self.sink = ExporterSink::Disabled;
                    }
                }
            }
            ExporterSink::SyntropicJsonl(file) => {
                if let Some(syntropic_event) = syntropic_jsonl_event(event) {
                    let result = serde_json::to_writer(&mut *file, &syntropic_event)
                        .and_then(|()| file.write_all(b"\n").map_err(serde_json::Error::io))
                        .and_then(|()| file.flush().map_err(serde_json::Error::io));
                    match result {
                        Ok(()) => {
                            self.events_exported += 1;
                        }
                        Err(err) => {
                            self.error = Some(err.to_string());
                            self.sink = ExporterSink::Disabled;
                        }
                    }
                }
            }
            ExporterSink::Disabled => {}
        }
    }

    fn report(mut self) -> ObservabilityExportReport {
        let mut links = Vec::new();
        match &mut self.sink {
            ExporterSink::File(_) | ExporterSink::SyntropicJsonl(_) => {
                if let Some(target) = self.target.as_deref() {
                    links.push(ObservabilityLink {
                        label: self.label.clone(),
                        uri: file_uri(target),
                    });
                }
            }
            ExporterSink::Disabled => {}
        }
        let status = if self.error.is_some() {
            ObservabilityExportStatus::Failed
        } else {
            ObservabilityExportStatus::Ok
        };
        ObservabilityExportReport {
            kind: self.kind,
            status,
            target: self.target,
            events_exported: self.events_exported,
            links,
            error: self.error,
        }
    }
}

fn syntropic_jsonl_event(event: &AgentRunEvent) -> Option<serde_json::Value> {
    let base = |event_type: &str| {
        json!({
            "event_type": event_type,
            "session_id": event.run_id,
            "timestamp": event.ts,
            "agentic_run_id": event.run_id,
            "agentic_event_seq": event.seq,
        })
    };

    match &event.payload {
        AgentRunEventPayload::ToolStart {
            tool_name,
            tool_input,
        } => {
            let mut value = base("tool_execution_started");
            value["tool_name"] = json!(tool_name);
            value["tool_input"] = tool_input.clone();
            Some(value)
        }
        AgentRunEventPayload::ToolEnd {
            tool_name,
            success,
            output_summary,
        } => {
            let mut value = base("tool_execution_completed");
            value["tool_name"] = json!(tool_name);
            value["success"] = json!(success);
            if let Some(summary) = output_summary {
                value["output_summary"] = json!(summary);
            }
            Some(value)
        }
        AgentRunEventPayload::TokenUsage {
            input_tokens,
            output_tokens,
            cached_input_tokens,
            reasoning_output_tokens,
            cost_usd,
            harness,
            provider,
            model,
        } => {
            let mut value = base("token_usage");
            value["input_tokens"] = json!(input_tokens);
            value["output_tokens"] = json!(output_tokens);
            if let Some(tokens) = cached_input_tokens {
                value["cached_input_tokens"] = json!(tokens);
            }
            if let Some(tokens) = reasoning_output_tokens {
                value["reasoning_output_tokens"] = json!(tokens);
            }
            if let Some(cost) = cost_usd {
                value["cost_usd"] = json!(cost);
            }
            if let Some(harness) = harness {
                value["harness"] = json!(harness);
            }
            if let Some(provider) = provider {
                value["provider"] = json!(provider);
            }
            if let Some(model) = model {
                value["model"] = json!(model);
            }
            Some(value)
        }
        AgentRunEventPayload::HookEvent {
            provider,
            event_type,
            event: hook_event,
        } => {
            let mut value = base(event_type);
            value["provider"] = json!(provider);
            if let Some(obj) = hook_event.as_object() {
                for (key, item) in obj {
                    if key == "event_type" || key == "timestamp" {
                        continue;
                    }
                    if key == "session_id" {
                        value["source_session_id"] = item.clone();
                    } else {
                        value[key] = item.clone();
                    }
                }
            } else {
                value["event"] = hook_event.clone();
            }
            Some(value)
        }
        AgentRunEventPayload::SessionEnd { outcome } => {
            let mut value = base("session_ended");
            value["success"] = json!(outcome.success);
            value["summary"] = json!(outcome.summary);
            Some(value)
        }
        AgentRunEventPayload::Result { .. } => None,
    }
}

fn open_jsonl(path: &Path) -> io::Result<File> {
    if let Some(parent) = path
        .parent()
        .filter(|parent| !parent.as_os_str().is_empty())
    {
        std::fs::create_dir_all(parent)?;
    }
    OpenOptions::new().create(true).append(true).open(path)
}

fn file_uri(path: &str) -> String {
    if path.starts_with("file://") {
        path.to_string()
    } else if PathBuf::from(path).is_absolute() {
        format!("file://{path}")
    } else {
        path.to_string()
    }
}

fn langfuse_ui_base_url(base_url: &str) -> String {
    let trimmed = base_url.trim().trim_end_matches('/');
    if let Some(origin) = trimmed.strip_suffix("/api/public/otel/v1/traces") {
        origin.to_string()
    } else if let Some(origin) = trimmed.strip_suffix("/api/public/otel") {
        origin.to_string()
    } else {
        trimmed.to_string()
    }
}

fn base64_encode(data: &[u8]) -> String {
    const TABLE: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = String::with_capacity(data.len().div_ceil(3) * 4);
    for chunk in data.chunks(3) {
        let b0 = chunk[0];
        let b1 = *chunk.get(1).unwrap_or(&0);
        let b2 = *chunk.get(2).unwrap_or(&0);
        out.push(TABLE[(b0 >> 2) as usize] as char);
        out.push(TABLE[(((b0 & 0b0000_0011) << 4) | (b1 >> 4)) as usize] as char);
        if chunk.len() > 1 {
            out.push(TABLE[(((b1 & 0b0000_1111) << 2) | (b2 >> 6)) as usize] as char);
        } else {
            out.push('=');
        }
        if chunk.len() > 2 {
            out.push(TABLE[(b2 & 0b0011_1111) as usize] as char);
        } else {
            out.push('=');
        }
    }
    out
}

fn hex_lower(data: &[u8]) -> String {
    const TABLE: &[u8; 16] = b"0123456789abcdef";
    let mut out = String::with_capacity(data.len() * 2);
    for byte in data {
        out.push(TABLE[(byte >> 4) as usize] as char);
        out.push(TABLE[(byte & 0x0f) as usize] as char);
    }
    out
}

fn trace_id_for_run(run_id: &str) -> [u8; 16] {
    let first = stable_hash64("agentic-primitives.trace-id.0", run_id);
    let second = stable_hash64("agentic-primitives.trace-id.1", run_id);
    let mut out = [0; 16];
    out[..8].copy_from_slice(&first.to_be_bytes());
    out[8..].copy_from_slice(&second.to_be_bytes());
    if out.iter().all(|byte| *byte == 0) {
        out[15] = 1;
    }
    out
}

/// Return the deterministic 32-hex LangFuse/OpenTelemetry trace id used for an
/// `itmux` run id.
pub fn langfuse_trace_id_for_run(run_id: &str) -> String {
    hex_lower(&trace_id_for_run(run_id))
}

/// Return the LangFuse UI/API origin for a configured origin, OTEL base, or
/// OTEL traces endpoint.
pub fn langfuse_api_base_url(base_url: &str) -> String {
    langfuse_ui_base_url(base_url)
}

/// Build the LangFuse Basic auth header from public/secret key values.
pub fn langfuse_basic_auth_header(public_key: &str, secret_key: &str) -> String {
    format!(
        "Basic {}",
        base64_encode(format!("{public_key}:{secret_key}").as_bytes())
    )
}

fn stable_hash64(domain: &str, value: &str) -> u64 {
    let mut hash = 0xcbf2_9ce4_8422_2325_u64;
    for byte in domain
        .as_bytes()
        .iter()
        .copied()
        .chain([0])
        .chain(value.as_bytes().iter().copied())
    {
        hash ^= u64::from(byte);
        hash = hash.wrapping_mul(0x0000_0100_0000_01b3);
    }
    hash
}

#[cfg(test)]
mod tests {
    use super::*;

    use crate::run::contract::{AgentRunEventPayload, AgentRunOutcome};

    fn session_end_event(seq: u64) -> AgentRunEvent {
        AgentRunEvent {
            run_id: "run-test".to_string(),
            seq,
            ts: format!("2026-07-07T00:00:0{seq}Z"),
            payload: AgentRunEventPayload::SessionEnd {
                outcome: AgentRunOutcome {
                    success: true,
                    summary: "done".to_string(),
                },
            },
        }
    }

    fn tool_end_event(seq: u64) -> AgentRunEvent {
        AgentRunEvent {
            run_id: "run-test".to_string(),
            seq,
            ts: format!("2026-07-07T00:00:0{seq}Z"),
            payload: AgentRunEventPayload::ToolEnd {
                tool_name: "codex.exec".to_string(),
                success: true,
                output_summary: Some("created trace artifact".to_string()),
            },
        }
    }

    fn token_usage_event(seq: u64, harness: &str, provider: &str, model: &str) -> AgentRunEvent {
        AgentRunEvent {
            run_id: "run-test".to_string(),
            seq,
            ts: format!("2026-07-07T00:00:0{seq}Z"),
            payload: AgentRunEventPayload::TokenUsage {
                input_tokens: 100,
                output_tokens: 25,
                cached_input_tokens: Some(10),
                reasoning_output_tokens: Some(5),
                cost_usd: Some(0.0012),
                harness: Some(harness.to_string()),
                provider: Some(provider.to_string()),
                model: Some(model.to_string()),
            },
        }
    }

    fn temp_file(name: &str) -> PathBuf {
        std::env::temp_dir().join(format!(
            "itmux-observability-{name}-{}-{}.jsonl",
            std::process::id(),
            unique_test_suffix()
        ))
    }

    fn unique_test_suffix() -> u128 {
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos()
    }

    #[test]
    fn file_exporter_writes_event_jsonl_and_reports_link() {
        let path = temp_file("happy");
        let mut fanout = ObservabilityFanout::new(&[ObservabilityExporter::File {
            path: path.clone(),
            label: Some("local events".to_string()),
        }]);

        fanout.emit(&session_end_event(0));
        fanout.emit(&session_end_event(1));
        let bundle = fanout.finish().expect("configured exporter reports");

        let contents = std::fs::read_to_string(&path).expect("jsonl file exists");
        let lines: Vec<_> = contents.lines().collect();
        assert_eq!(lines.len(), 2);
        let parsed: AgentRunEvent = serde_json::from_str(lines[0]).expect("event json");
        assert_eq!(parsed.seq, 0);

        let report = &bundle.exporters[0];
        assert_eq!(report.status, ObservabilityExportStatus::Ok);
        assert_eq!(report.events_exported, 2);
        assert_eq!(report.links[0].label, "local events");
        assert!(report.links[0].uri.starts_with("file://"));

        let _ = std::fs::remove_file(path);
    }

    #[test]
    fn syntropic_jsonl_exporter_writes_hook_style_events() {
        let path = temp_file("syntropic");
        let mut fanout = ObservabilityFanout::new(&[ObservabilityExporter::SyntropicJsonl {
            path: path.clone(),
            label: Some("Syntropic137 events".to_string()),
        }]);

        fanout.emit(&tool_end_event(0));
        fanout.emit(&token_usage_event(1, "codex", "openai", "gpt-5.5"));
        fanout.emit(&session_end_event(2));
        let bundle = fanout.finish().expect("configured exporter reports");

        let contents = std::fs::read_to_string(&path).expect("jsonl file exists");
        let lines: Vec<_> = contents.lines().collect();
        assert_eq!(lines.len(), 3);

        let tool: serde_json::Value = serde_json::from_str(lines[0]).expect("tool json");
        assert_eq!(tool["event_type"], "tool_execution_completed");
        assert_eq!(tool["session_id"], "run-test");
        assert_eq!(tool["tool_name"], "codex.exec");
        assert_eq!(tool["agentic_event_seq"], 0);

        let usage: serde_json::Value = serde_json::from_str(lines[1]).expect("usage json");
        assert_eq!(usage["event_type"], "token_usage");
        assert_eq!(usage["input_tokens"], 100);
        assert_eq!(usage["harness"], "codex");

        let end: serde_json::Value = serde_json::from_str(lines[2]).expect("end json");
        assert_eq!(end["event_type"], "session_ended");
        assert_eq!(end["success"], true);

        let report = &bundle.exporters[0];
        assert_eq!(report.kind, "syntropic_jsonl");
        assert_eq!(report.status, ObservabilityExportStatus::Ok);
        assert_eq!(report.events_exported, 3);
        assert_eq!(report.links[0].label, "Syntropic137 events");

        let _ = std::fs::remove_file(path);
    }

    #[test]
    fn file_exporter_link_preserves_relative_paths() {
        assert_eq!(file_uri("events/run.jsonl"), "events/run.jsonl");
        assert_eq!(
            file_uri("/tmp/itmux-run-events.jsonl"),
            "file:///tmp/itmux-run-events.jsonl"
        );
        assert_eq!(
            file_uri("file:///tmp/already-a-uri.jsonl"),
            "file:///tmp/already-a-uri.jsonl"
        );
    }

    #[test]
    fn langfuse_api_base_url_accepts_otel_base_or_trace_endpoint() {
        assert_eq!(
            langfuse_api_base_url("http://localhost:3000/api/public/otel"),
            "http://localhost:3000"
        );
        assert_eq!(
            langfuse_api_base_url("http://localhost:3000/api/public/otel/v1/traces"),
            "http://localhost:3000"
        );
    }

    #[test]
    fn langfuse_basic_auth_header_encodes_public_and_secret_key() {
        assert_eq!(
            langfuse_basic_auth_header("pk-lf-test", "sk-lf-test"),
            "Basic cGstbGYtdGVzdDpzay1sZi10ZXN0"
        );
    }

    #[test]
    fn langfuse_trace_id_for_run_is_stable() {
        assert_eq!(
            langfuse_trace_id_for_run("run-test"),
            "56e46cb6e46dc6d0ef3a439f691881dd"
        );
    }
}
