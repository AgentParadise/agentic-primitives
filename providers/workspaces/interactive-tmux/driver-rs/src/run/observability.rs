//! Reusable observability fanout for `itmux run`.
//!
//! The orchestrator stays focused on run lifecycle. This layer consumes the
//! normalized `AgentRunEvent` stream and exports it to configured sinks, while
//! accumulating exporter status for the final `AgentRunResult`.

use std::fs::{File, OpenOptions};
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::time::Duration;

use crate::run::contract::{
    AgentRunEvent, AgentRunEventPayload, ObservabilityBundle, ObservabilityExportReport,
    ObservabilityExportStatus, ObservabilityExporter, ObservabilityLink,
};

const LANGFUSE_HTTP_TIMEOUT: Duration = Duration::from_secs(10);

pub struct ObservabilityFanout {
    sinks: Vec<ExporterState>,
}

enum ExporterSink {
    File(File),
    LangFuseOtlp(LangFuseOtlpSink),
    Disabled,
}

struct ExporterState {
    kind: String,
    target: Option<String>,
    label: String,
    sink: ExporterSink,
    events_exported: u64,
    events_pending: u64,
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
                    events_pending: 0,
                    error: None,
                },
                Err(err) => Self {
                    kind: config.kind().to_string(),
                    target: Some(path.display().to_string()),
                    label: label.clone().unwrap_or_else(|| "run events".to_string()),
                    sink: ExporterSink::Disabled,
                    events_exported: 0,
                    events_pending: 0,
                    error: Some(err.to_string()),
                },
            },
            ObservabilityExporter::LangFuseOtlp {
                base_url,
                public_key_env,
                secret_key_env,
                environment_env,
                project_id,
                project_id_env,
                service_name,
                label,
            } => {
                let env = SystemEnv;
                let input = LangFuseOtlpConfigInput {
                    base_url: base_url.as_deref(),
                    public_key_env,
                    secret_key_env,
                    environment_env,
                    project_id: project_id.as_deref(),
                    project_id_env,
                    service_name,
                };
                match resolve_langfuse_otlp_config(&input, &env) {
                    Ok(resolved) => Self {
                        kind: config.kind().to_string(),
                        target: Some(resolved.traces_endpoint.clone()),
                        label: label
                            .clone()
                            .unwrap_or_else(|| "LangFuse trace".to_string()),
                        sink: ExporterSink::LangFuseOtlp(LangFuseOtlpSink::new(resolved)),
                        events_exported: 0,
                        events_pending: 0,
                        error: None,
                    },
                    Err(err) => Self {
                        kind: config.kind().to_string(),
                        target: None,
                        label: label
                            .clone()
                            .unwrap_or_else(|| "LangFuse trace".to_string()),
                        sink: ExporterSink::Disabled,
                        events_exported: 0,
                        events_pending: 0,
                        error: Some(err),
                    },
                }
            }
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
            ExporterSink::LangFuseOtlp(sink) => {
                sink.push(event);
                self.events_pending += 1;
            }
            ExporterSink::Disabled => {}
        }
    }

    fn report(mut self) -> ObservabilityExportReport {
        let mut links = Vec::new();
        match &mut self.sink {
            ExporterSink::File(_) => {
                if let Some(target) = self.target.as_deref() {
                    links.push(ObservabilityLink {
                        label: self.label.clone(),
                        uri: file_uri(target),
                    });
                }
            }
            ExporterSink::LangFuseOtlp(sink) => {
                if let Err(err) = sink.export() {
                    self.error = Some(err);
                } else if let Some(link) = sink.trace_link(&self.label) {
                    self.events_exported = self.events_pending;
                    links.push(link);
                } else {
                    self.events_exported = self.events_pending;
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

trait EnvLookup {
    fn get(&self, key: &str) -> Option<String>;
}

struct SystemEnv;

impl EnvLookup for SystemEnv {
    fn get(&self, key: &str) -> Option<String> {
        std::env::var(key).ok()
    }
}

#[derive(Debug, PartialEq, Eq)]
struct LangFuseOtlpResolvedConfig {
    traces_endpoint: String,
    ui_base_url: String,
    authorization_header: String,
    environment: String,
    project_id: Option<String>,
    service_name: String,
}

struct LangFuseOtlpConfigInput<'a> {
    base_url: Option<&'a str>,
    public_key_env: &'a str,
    secret_key_env: &'a str,
    environment_env: &'a str,
    project_id: Option<&'a str>,
    project_id_env: &'a str,
    service_name: &'a str,
}

struct LangFuseOtlpSink {
    config: LangFuseOtlpResolvedConfig,
    events: Vec<AgentRunEvent>,
}

impl LangFuseOtlpSink {
    fn new(config: LangFuseOtlpResolvedConfig) -> Self {
        Self {
            config,
            events: Vec::new(),
        }
    }

    fn push(&mut self, event: &AgentRunEvent) {
        self.events.push(event.clone());
    }

    fn export(&self) -> Result<(), String> {
        if self.events.is_empty() {
            return Ok(());
        }
        let body = encode_otlp_trace_request(
            &self.events,
            &self.config.service_name,
            &self.config.environment,
        );
        let response = ureq::post(&self.config.traces_endpoint)
            .timeout(LANGFUSE_HTTP_TIMEOUT)
            .set("Authorization", &self.config.authorization_header)
            .set("Content-Type", "application/x-protobuf")
            .set("x-langfuse-ingestion-version", "4")
            .send_bytes(&body);
        match response {
            Ok(response) if (200..300).contains(&response.status()) => Ok(()),
            Ok(response) => Err(format!(
                "langfuse_otlp export failed: HTTP {} {}",
                response.status(),
                response.status_text()
            )),
            Err(ureq::Error::Status(code, response)) => Err(format!(
                "langfuse_otlp export failed: HTTP {code} {}",
                response.status_text()
            )),
            Err(err) => Err(format!("langfuse_otlp export failed: {err}")),
        }
    }

    fn trace_link(&self, label: &str) -> Option<ObservabilityLink> {
        let project_id = self.config.project_id.as_deref()?;
        let run_id = self.events.first()?.run_id.as_str();
        let trace_id = hex_lower(&trace_id_for_run(run_id));
        Some(ObservabilityLink {
            label: label.to_string(),
            uri: format!(
                "{}/project/{}/traces/{}",
                self.config.ui_base_url,
                url_path_encode(project_id),
                trace_id
            ),
        })
    }
}

fn resolve_langfuse_otlp_config(
    input: &LangFuseOtlpConfigInput<'_>,
    env: &impl EnvLookup,
) -> Result<LangFuseOtlpResolvedConfig, String> {
    let base_url = required_value(
        "LANGFUSE_BASE_URL",
        input.base_url,
        env.get("LANGFUSE_BASE_URL"),
    )?;
    let public_key = required_env(input.public_key_env, env)?;
    let secret_key = required_env(input.secret_key_env, env)?;
    let environment = required_env(input.environment_env, env)?;
    let project_id = optional_value(input.project_id, env.get(input.project_id_env));
    if input.service_name.trim().is_empty() {
        return Err("langfuse_otlp service_name must not be empty".to_string());
    }
    Ok(LangFuseOtlpResolvedConfig {
        traces_endpoint: langfuse_traces_endpoint(&base_url),
        ui_base_url: langfuse_ui_base_url(&base_url),
        authorization_header: format!(
            "Basic {}",
            base64_encode(format!("{public_key}:{secret_key}").as_bytes())
        ),
        environment,
        project_id,
        service_name: input.service_name.to_string(),
    })
}

fn required_value(
    name: &str,
    explicit: Option<&str>,
    env_value: Option<String>,
) -> Result<String, String> {
    explicit
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToOwned::to_owned)
        .or_else(|| env_value.map(|value| value.trim().to_string()))
        .filter(|value| !value.is_empty())
        .ok_or_else(|| format!("missing required LangFuse config: {name}"))
}

fn required_env(name: &str, env: &impl EnvLookup) -> Result<String, String> {
    env.get(name)
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .ok_or_else(|| format!("missing required LangFuse env var: {name}"))
}

fn optional_value(explicit: Option<&str>, env_value: Option<String>) -> Option<String> {
    explicit
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToOwned::to_owned)
        .or_else(|| {
            env_value
                .map(|value| value.trim().to_string())
                .filter(|value| !value.is_empty())
        })
}

fn langfuse_traces_endpoint(base_url: &str) -> String {
    let trimmed = base_url.trim().trim_end_matches('/');
    if trimmed.ends_with("/api/public/otel/v1/traces") {
        trimmed.to_string()
    } else if trimmed.ends_with("/api/public/otel") {
        format!("{trimmed}/v1/traces")
    } else {
        format!("{trimmed}/api/public/otel/v1/traces")
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

fn url_path_encode(value: &str) -> String {
    let mut out = String::new();
    for byte in value.bytes() {
        if byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'.' | b'_' | b'~') {
            out.push(byte as char);
        } else {
            out.push('%');
            out.push(char::from(b"0123456789ABCDEF"[(byte >> 4) as usize]));
            out.push(char::from(b"0123456789ABCDEF"[(byte & 0x0f) as usize]));
        }
    }
    out
}

fn encode_otlp_trace_request(
    events: &[AgentRunEvent],
    service_name: &str,
    environment: &str,
) -> Vec<u8> {
    let run_id = events
        .first()
        .map(|event| event.run_id.as_str())
        .unwrap_or("run-unknown");
    let trace_id = trace_id_for_run(run_id);
    let mut spans = Vec::with_capacity(events.len() + 1);
    let root_span_id = span_id_for(run_id, u64::MAX);
    let root_nanos = events
        .first()
        .map(|event| unix_nanos_from_rfc3339_seconds(&event.ts))
        .unwrap_or(0);
    spans.push(encode_span(SpanEncodeInput {
        trace_id: &trace_id,
        span_id: &root_span_id,
        parent_span_id: None,
        name: "agentic_primitives.run",
        run_id,
        event: None,
        extra_attributes: &[
            ("session.id", run_id),
            ("langfuse.session.id", run_id),
            ("langfuse.trace.name", "agentic_primitives.run"),
            ("langfuse.trace.metadata.run_id", run_id),
        ],
        start_nanos: root_nanos,
    }));
    for event in events {
        let span_id = span_id_for(&event.run_id, event.seq);
        let nanos = unix_nanos_from_rfc3339_seconds(&event.ts);
        spans.push(encode_span(SpanEncodeInput {
            trace_id: &trace_id,
            span_id: &span_id,
            parent_span_id: Some(&root_span_id),
            name: event.payload.type_name(),
            run_id: &event.run_id,
            event: Some(event),
            extra_attributes: &[],
            start_nanos: nanos,
        }));
    }

    let mut scope_spans = Vec::new();
    push_message(&mut scope_spans, 1, &encode_instrumentation_scope("itmux"));
    for span in spans {
        push_message(&mut scope_spans, 2, &span);
    }

    let resource = encode_resource(&[
        ("service.name", service_name),
        ("deployment.environment.name", environment),
        ("langfuse.environment", environment),
    ]);
    let mut resource_spans = Vec::new();
    push_message(&mut resource_spans, 1, &resource);
    push_message(&mut resource_spans, 2, &scope_spans);

    let mut request = Vec::new();
    push_message(&mut request, 1, &resource_spans);
    request
}

fn encode_resource(attributes: &[(&str, &str)]) -> Vec<u8> {
    let mut out = Vec::new();
    for (key, value) in attributes {
        push_message(&mut out, 1, &encode_key_value(key, value));
    }
    out
}

fn encode_instrumentation_scope(name: &str) -> Vec<u8> {
    let mut out = Vec::new();
    push_string(&mut out, 1, name);
    out
}

struct SpanEncodeInput<'a> {
    trace_id: &'a [u8; 16],
    span_id: &'a [u8; 8],
    parent_span_id: Option<&'a [u8; 8]>,
    name: &'a str,
    run_id: &'a str,
    event: Option<&'a AgentRunEvent>,
    extra_attributes: &'a [(&'a str, &'a str)],
    start_nanos: u64,
}

fn encode_span(input: SpanEncodeInput<'_>) -> Vec<u8> {
    let mut out = Vec::new();
    push_bytes(&mut out, 1, input.trace_id);
    push_bytes(&mut out, 2, input.span_id);
    if let Some(parent_span_id) = input.parent_span_id {
        push_bytes(&mut out, 4, parent_span_id);
    }
    push_string(&mut out, 5, input.name);
    push_varint_field(&mut out, 6, 1); // SpanKind::Internal.
    push_fixed64(&mut out, 7, input.start_nanos);
    push_fixed64(&mut out, 8, input.start_nanos.saturating_add(1_000_000));
    push_message(&mut out, 9, &encode_key_value("session.id", input.run_id));
    for (key, value) in input.extra_attributes {
        push_message(&mut out, 9, &encode_key_value(key, value));
    }
    if let Some(event) = input.event {
        push_message(
            &mut out,
            9,
            &encode_key_value("agentic.event.type", event.payload.type_name()),
        );
        push_message(
            &mut out,
            9,
            &encode_key_value("agentic.event.seq", &event.seq.to_string()),
        );
        for (key, value) in event_payload_attributes(&event.payload) {
            push_message(&mut out, 9, &encode_key_value(&key, &value));
        }
    }
    out
}

fn event_payload_attributes(payload: &AgentRunEventPayload) -> Vec<(String, String)> {
    match payload {
        AgentRunEventPayload::ToolStart {
            tool_name,
            tool_input,
        } => vec![
            ("agentic.tool.name".to_string(), tool_name.clone()),
            (
                "agentic.tool.input_json".to_string(),
                tool_input.to_string(),
            ),
        ],
        AgentRunEventPayload::ToolEnd {
            tool_name,
            success,
            output_summary,
        } => {
            let mut attributes = vec![
                ("agentic.tool.name".to_string(), tool_name.clone()),
                ("agentic.tool.success".to_string(), success.to_string()),
            ];
            if let Some(output_summary) = output_summary {
                attributes.push((
                    "agentic.tool.output_summary".to_string(),
                    output_summary.clone(),
                ));
            }
            attributes
        }
        AgentRunEventPayload::TokenUsage {
            input_tokens,
            output_tokens,
            cached_input_tokens,
            reasoning_output_tokens,
            cost_usd,
        } => {
            let mut attributes = vec![
                (
                    "agentic.usage.input_tokens".to_string(),
                    input_tokens.to_string(),
                ),
                (
                    "agentic.usage.output_tokens".to_string(),
                    output_tokens.to_string(),
                ),
            ];
            if let Some(cached_input_tokens) = cached_input_tokens {
                attributes.push((
                    "agentic.usage.cached_input_tokens".to_string(),
                    cached_input_tokens.to_string(),
                ));
            }
            if let Some(reasoning_output_tokens) = reasoning_output_tokens {
                attributes.push((
                    "agentic.usage.reasoning_output_tokens".to_string(),
                    reasoning_output_tokens.to_string(),
                ));
            }
            if let Some(cost_usd) = cost_usd {
                attributes.push(("agentic.usage.cost_usd".to_string(), cost_usd.to_string()));
            }
            attributes
        }
        AgentRunEventPayload::HookEvent {
            provider,
            event_type,
            event,
        } => vec![
            ("agentic.hook.provider".to_string(), provider.clone()),
            ("agentic.hook.event_type".to_string(), event_type.clone()),
            ("agentic.hook.event_json".to_string(), event.to_string()),
        ],
        AgentRunEventPayload::SessionEnd { outcome } => vec![
            (
                "agentic.outcome.success".to_string(),
                outcome.success.to_string(),
            ),
            (
                "agentic.outcome.summary".to_string(),
                outcome.summary.clone(),
            ),
        ],
        AgentRunEventPayload::Result { result } => vec![
            (
                "agentic.result.success".to_string(),
                result.result.success.to_string(),
            ),
            (
                "agentic.result.summary".to_string(),
                result.result.summary.clone(),
            ),
        ],
    }
}

fn encode_key_value(key: &str, value: &str) -> Vec<u8> {
    let mut out = Vec::new();
    push_string(&mut out, 1, key);
    let mut any_value = Vec::new();
    push_string(&mut any_value, 1, value);
    push_message(&mut out, 2, &any_value);
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

fn span_id_for(run_id: &str, seq: u64) -> [u8; 8] {
    let value = stable_hash64("agentic-primitives.span-id", &format!("{run_id}:{seq}"));
    let value = if value == 0 { 1 } else { value };
    value.to_be_bytes()
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

fn unix_nanos_from_rfc3339_seconds(ts: &str) -> u64 {
    // The driver emits second-precision RFC3339 UTC timestamps. If parsing
    // fails, use zero rather than failing observability export.
    let Some((date, time)) = ts.trim_end_matches('Z').split_once('T') else {
        return 0;
    };
    let mut date_parts = date.split('-').filter_map(|part| part.parse::<i64>().ok());
    let (Some(year), Some(month), Some(day)) =
        (date_parts.next(), date_parts.next(), date_parts.next())
    else {
        return 0;
    };
    let mut time_parts = time.split(':').filter_map(|part| part.parse::<i64>().ok());
    let (Some(hour), Some(minute), Some(second)) =
        (time_parts.next(), time_parts.next(), time_parts.next())
    else {
        return 0;
    };
    let days = days_from_civil(year, month, day);
    if days < 0 {
        return 0;
    }
    ((days * 86_400 + hour * 3_600 + minute * 60 + second) as u64) * 1_000_000_000
}

fn days_from_civil(year: i64, month: i64, day: i64) -> i64 {
    let year = year - i64::from(month <= 2);
    let era = if year >= 0 { year } else { year - 399 } / 400;
    let yoe = year - era * 400;
    let month_prime = month + if month > 2 { -3 } else { 9 };
    let doy = (153 * month_prime + 2) / 5 + day - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    era * 146_097 + doe - 719_468
}

fn push_message(out: &mut Vec<u8>, field: u32, value: &[u8]) {
    push_key(out, field, 2);
    push_varint(out, value.len() as u64);
    out.extend_from_slice(value);
}

fn push_string(out: &mut Vec<u8>, field: u32, value: &str) {
    push_bytes(out, field, value.as_bytes());
}

fn push_bytes(out: &mut Vec<u8>, field: u32, value: &[u8]) {
    push_key(out, field, 2);
    push_varint(out, value.len() as u64);
    out.extend_from_slice(value);
}

fn push_varint_field(out: &mut Vec<u8>, field: u32, value: u64) {
    push_key(out, field, 0);
    push_varint(out, value);
}

fn push_fixed64(out: &mut Vec<u8>, field: u32, value: u64) {
    push_key(out, field, 1);
    out.extend_from_slice(&value.to_le_bytes());
}

fn push_key(out: &mut Vec<u8>, field: u32, wire_type: u8) {
    push_varint(out, ((field as u64) << 3) | u64::from(wire_type));
}

fn push_varint(out: &mut Vec<u8>, mut value: u64) {
    while value >= 0x80 {
        out.push((value as u8) | 0x80);
        value >>= 7;
    }
    out.push(value as u8);
}

trait AgentRunEventPayloadExt {
    fn type_name(&self) -> &'static str;
}

impl AgentRunEventPayloadExt for crate::run::contract::AgentRunEventPayload {
    fn type_name(&self) -> &'static str {
        match self {
            Self::ToolStart { .. } => "tool_start",
            Self::ToolEnd { .. } => "tool_end",
            Self::TokenUsage { .. } => "token_usage",
            Self::HookEvent { .. } => "hook_event",
            Self::SessionEnd { .. } => "session_end",
            Self::Result { .. } => "result",
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeMap;
    use std::io::Read;
    use std::net::TcpListener;
    use std::sync::mpsc;

    use crate::run::contract::{AgentRunEventPayload, AgentRunOutcome};

    struct MapEnv(BTreeMap<String, String>);

    impl EnvLookup for MapEnv {
        fn get(&self, key: &str) -> Option<String> {
            self.0.get(key).cloned()
        }
    }

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

    fn map_env(values: &[(&str, &str)]) -> MapEnv {
        MapEnv(
            values
                .iter()
                .map(|(key, value)| ((*key).to_string(), (*value).to_string()))
                .collect(),
        )
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
    fn langfuse_otlp_config_derives_traces_endpoint_and_auth() {
        let env = map_env(&[
            ("LANGFUSE_PUBLIC_KEY", "pk-lf-test"),
            ("LANGFUSE_SECRET_KEY", "sk-lf-test"),
            ("LANGFUSE_TRACING_ENVIRONMENT", "agentic-primitives-test"),
            ("LANGFUSE_PROJECT_ID", "project-123"),
        ]);

        let input = LangFuseOtlpConfigInput {
            base_url: Some("https://cloud.langfuse.com"),
            public_key_env: "LANGFUSE_PUBLIC_KEY",
            secret_key_env: "LANGFUSE_SECRET_KEY",
            environment_env: "LANGFUSE_TRACING_ENVIRONMENT",
            project_id: None,
            project_id_env: "LANGFUSE_PROJECT_ID",
            service_name: "agentic-primitives",
        };
        let resolved = resolve_langfuse_otlp_config(&input, &env).expect("config resolves");

        assert_eq!(
            resolved.traces_endpoint,
            "https://cloud.langfuse.com/api/public/otel/v1/traces"
        );
        assert_eq!(resolved.ui_base_url, "https://cloud.langfuse.com");
        assert_eq!(
            resolved.authorization_header,
            "Basic cGstbGYtdGVzdDpzay1sZi10ZXN0"
        );
        assert_eq!(resolved.environment, "agentic-primitives-test");
        assert_eq!(resolved.project_id.as_deref(), Some("project-123"));
        assert_eq!(resolved.service_name, "agentic-primitives");
    }

    #[test]
    fn langfuse_otlp_config_accepts_otel_base_or_trace_endpoint() {
        assert_eq!(
            langfuse_traces_endpoint("http://localhost:3000/api/public/otel"),
            "http://localhost:3000/api/public/otel/v1/traces"
        );
        assert_eq!(
            langfuse_traces_endpoint("http://localhost:3000/api/public/otel/v1/traces"),
            "http://localhost:3000/api/public/otel/v1/traces"
        );
        assert_eq!(
            langfuse_ui_base_url("http://localhost:3000/api/public/otel"),
            "http://localhost:3000"
        );
        assert_eq!(
            langfuse_ui_base_url("http://localhost:3000/api/public/otel/v1/traces"),
            "http://localhost:3000"
        );
    }

    #[test]
    fn langfuse_otlp_exporter_reports_missing_env_without_secrets() {
        let fanout = ObservabilityFanout::new(&[ObservabilityExporter::LangFuseOtlp {
            base_url: Some("https://cloud.langfuse.com".to_string()),
            public_key_env: "MISSING_PUBLIC".to_string(),
            secret_key_env: "MISSING_SECRET".to_string(),
            environment_env: "MISSING_ENVIRONMENT".to_string(),
            project_id: None,
            project_id_env: "LANGFUSE_PROJECT_ID".to_string(),
            service_name: "agentic-primitives".to_string(),
            label: None,
        }]);
        let bundle = fanout.finish().expect("configured exporter reports");
        let report = &bundle.exporters[0];
        assert_eq!(report.kind, "langfuse_otlp");
        assert_eq!(report.status, ObservabilityExportStatus::Failed);
        let error = report.error.as_deref().expect("config error");
        assert!(error.contains("MISSING_PUBLIC"), "error: {error}");
        assert!(
            !error.contains("pk-lf"),
            "error should not contain key values"
        );
        assert!(report.links.is_empty());
    }

    #[test]
    fn langfuse_otlp_exporter_posts_protobuf_to_local_receiver() {
        let listener = TcpListener::bind("127.0.0.1:0").expect("bind local receiver");
        let addr = listener.local_addr().expect("local receiver address");
        let (tx, rx) = mpsc::channel();
        let server = std::thread::spawn(move || {
            let (mut stream, _) = listener.accept().expect("accept request");
            let mut request = Vec::new();
            let mut buffer = [0_u8; 4096];
            loop {
                let n = stream.read(&mut buffer).expect("read request");
                if n == 0 {
                    break;
                }
                request.extend_from_slice(&buffer[..n]);
                let Some(header_pos) = request.windows(4).position(|window| window == b"\r\n\r\n")
                else {
                    continue;
                };
                let header_end = header_pos + 4;
                let headers = String::from_utf8_lossy(&request[..header_end]);
                let content_length = headers
                    .lines()
                    .find_map(|line| {
                        line.strip_prefix("Content-Length:")
                            .or_else(|| line.strip_prefix("content-length:"))
                    })
                    .and_then(|value| value.trim().parse::<usize>().ok())
                    .unwrap_or(0);
                while request.len() < header_end + content_length {
                    let n = stream.read(&mut buffer).expect("read request body");
                    if n == 0 {
                        break;
                    }
                    request.extend_from_slice(&buffer[..n]);
                }
                break;
            }
            stream
                .write_all(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nOK")
                .expect("write response");
            tx.send(request).expect("send captured request");
        });

        std::env::set_var("LANGFUSE_PUBLIC_KEY", "pk-lf-test");
        std::env::set_var("LANGFUSE_SECRET_KEY", "sk-lf-test");
        std::env::set_var("LANGFUSE_TRACING_ENVIRONMENT", "agentic-primitives-test");
        std::env::set_var("LANGFUSE_PROJECT_ID", "project-123");

        let mut fanout = ObservabilityFanout::new(&[ObservabilityExporter::LangFuseOtlp {
            base_url: Some(format!("http://{addr}")),
            public_key_env: "LANGFUSE_PUBLIC_KEY".to_string(),
            secret_key_env: "LANGFUSE_SECRET_KEY".to_string(),
            environment_env: "LANGFUSE_TRACING_ENVIRONMENT".to_string(),
            project_id: None,
            project_id_env: "LANGFUSE_PROJECT_ID".to_string(),
            service_name: "agentic-primitives".to_string(),
            label: Some("local receiver LangFuse".to_string()),
        }]);
        fanout.emit(&tool_end_event(0));
        let bundle = fanout.finish().expect("configured exporter reports");

        std::env::remove_var("LANGFUSE_PUBLIC_KEY");
        std::env::remove_var("LANGFUSE_SECRET_KEY");
        std::env::remove_var("LANGFUSE_TRACING_ENVIRONMENT");
        std::env::remove_var("LANGFUSE_PROJECT_ID");

        let request = rx.recv().expect("captured request");
        server.join().expect("server joined");
        let header_end = request
            .windows(4)
            .position(|window| window == b"\r\n\r\n")
            .expect("headers complete")
            + 4;
        let headers = String::from_utf8_lossy(&request[..header_end]);
        let body = &request[header_end..];

        assert!(headers.starts_with("POST /api/public/otel/v1/traces "));
        assert!(headers.contains("Content-Type: application/x-protobuf"));
        assert!(headers.contains("Authorization: Basic cGstbGYtdGVzdDpzay1sZi10ZXN0"));
        assert!(headers.contains("x-langfuse-ingestion-version: 4"));
        assert!(!body.is_empty());
        assert!(body
            .windows("agentic_primitives.run".len())
            .any(|window| window == b"agentic_primitives.run"));
        assert!(body
            .windows("agentic.tool.name".len())
            .any(|window| window == b"agentic.tool.name"));
        assert!(body
            .windows("codex.exec".len())
            .any(|window| window == b"codex.exec"));
        assert!(body
            .windows("agentic.tool.success".len())
            .any(|window| window == b"agentic.tool.success"));
        assert!(body
            .windows("created trace artifact".len())
            .any(|window| window == b"created trace artifact"));

        let report = &bundle.exporters[0];
        assert_eq!(report.status, ObservabilityExportStatus::Ok);
        assert_eq!(report.events_exported, 1);
        let expected_target = format!("http://{addr}/api/public/otel/v1/traces");
        assert_eq!(report.target.as_deref(), Some(expected_target.as_str()));
        assert_eq!(report.links.len(), 1);
        assert_eq!(report.links[0].label, "local receiver LangFuse");
        assert!(report.links[0]
            .uri
            .starts_with(&format!("http://{addr}/project/project-123/traces/")));
        let trace_id = report.links[0]
            .uri
            .rsplit('/')
            .next()
            .expect("trace id segment");
        assert_eq!(trace_id.len(), 32);
        assert!(trace_id.chars().all(|ch| ch.is_ascii_hexdigit()));
        assert!(report.error.is_none());
    }

    #[test]
    fn langfuse_trace_id_for_run_is_stable() {
        assert_eq!(
            langfuse_trace_id_for_run("run-test"),
            "56e46cb6e46dc6d0ef3a439f691881dd"
        );
    }
}
