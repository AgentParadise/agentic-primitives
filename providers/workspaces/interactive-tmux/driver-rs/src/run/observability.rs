//! Reusable observability fanout for `itmux run`.
//!
//! The orchestrator stays focused on run lifecycle. This layer consumes the
//! normalized `AgentRunEvent` stream and exports it to configured sinks, while
//! accumulating exporter status for the final `AgentRunResult`.

use std::fs::{File, OpenOptions};
use std::io::{self, Write};
use std::path::{Path, PathBuf};

use crate::run::contract::{
    AgentRunEvent, ObservabilityBundle, ObservabilityExportReport, ObservabilityExportStatus,
    ObservabilityExporter, ObservabilityLink,
};

pub struct ObservabilityFanout {
    sinks: Vec<ExporterState>,
}

enum ExporterSink {
    File(File),
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
            ObservabilityExporter::LangFuseOtlp {
                base_url,
                public_key_env,
                secret_key_env,
                environment_env,
                service_name,
                label,
            } => {
                let env = SystemEnv;
                match resolve_langfuse_otlp_config(
                    base_url.as_deref(),
                    public_key_env,
                    secret_key_env,
                    environment_env,
                    service_name,
                    &env,
                ) {
                    Ok(resolved) => Self {
                        kind: config.kind().to_string(),
                        target: Some(resolved.traces_endpoint),
                        label: label
                            .clone()
                            .unwrap_or_else(|| "LangFuse trace".to_string()),
                        sink: ExporterSink::Disabled,
                        events_exported: 0,
                        error: Some(
                            "langfuse_otlp transport is not enabled yet; run the real LangFuse OTLP ingestion smoke before treating this exporter as complete"
                                .to_string(),
                        ),
                    },
                    Err(err) => Self {
                        kind: config.kind().to_string(),
                        target: None,
                        label: label
                            .clone()
                            .unwrap_or_else(|| "LangFuse trace".to_string()),
                        sink: ExporterSink::Disabled,
                        events_exported: 0,
                        error: Some(err),
                    },
                }
            }
        }
    }

    fn emit(&mut self, event: &AgentRunEvent) {
        let ExporterSink::File(file) = &mut self.sink else {
            return;
        };
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

    fn report(self) -> ObservabilityExportReport {
        let status = if self.error.is_some() {
            ObservabilityExportStatus::Failed
        } else {
            ObservabilityExportStatus::Ok
        };
        let links = self
            .target
            .as_deref()
            .map(|target| ObservabilityLink {
                label: self.label,
                uri: file_uri(target),
            })
            .into_iter()
            .collect();
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
    authorization_header: String,
    environment: String,
    service_name: String,
}

fn resolve_langfuse_otlp_config(
    base_url: Option<&str>,
    public_key_env: &str,
    secret_key_env: &str,
    environment_env: &str,
    service_name: &str,
    env: &impl EnvLookup,
) -> Result<LangFuseOtlpResolvedConfig, String> {
    let base_url = required_value("LANGFUSE_BASE_URL", base_url, env.get("LANGFUSE_BASE_URL"))?;
    let public_key = required_env(public_key_env, env)?;
    let secret_key = required_env(secret_key_env, env)?;
    let environment = required_env(environment_env, env)?;
    if service_name.trim().is_empty() {
        return Err("langfuse_otlp service_name must not be empty".to_string());
    }
    Ok(LangFuseOtlpResolvedConfig {
        traces_endpoint: langfuse_traces_endpoint(&base_url),
        authorization_header: format!(
            "Basic {}",
            base64_encode(format!("{public_key}:{secret_key}").as_bytes())
        ),
        environment,
        service_name: service_name.to_string(),
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

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeMap;

    use crate::run::contract::{AgentRunEventPayload, AgentRunOutcome};

    struct MapEnv(BTreeMap<String, String>);

    impl EnvLookup for MapEnv {
        fn get(&self, key: &str) -> Option<String> {
            self.0.get(key).cloned()
        }
    }

    fn event(seq: u64) -> AgentRunEvent {
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

        fanout.emit(&event(0));
        fanout.emit(&event(1));
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
    fn langfuse_otlp_config_derives_traces_endpoint_and_auth() {
        let env = map_env(&[
            ("LANGFUSE_PUBLIC_KEY", "pk-lf-test"),
            ("LANGFUSE_SECRET_KEY", "sk-lf-test"),
            ("LANGFUSE_TRACING_ENVIRONMENT", "agentic-primitives-test"),
        ]);

        let resolved = resolve_langfuse_otlp_config(
            Some("https://cloud.langfuse.com"),
            "LANGFUSE_PUBLIC_KEY",
            "LANGFUSE_SECRET_KEY",
            "LANGFUSE_TRACING_ENVIRONMENT",
            "agentic-primitives",
            &env,
        )
        .expect("config resolves");

        assert_eq!(
            resolved.traces_endpoint,
            "https://cloud.langfuse.com/api/public/otel/v1/traces"
        );
        assert_eq!(
            resolved.authorization_header,
            "Basic cGstbGYtdGVzdDpzay1sZi10ZXN0"
        );
        assert_eq!(resolved.environment, "agentic-primitives-test");
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
    }

    #[test]
    fn langfuse_otlp_exporter_reports_missing_env_without_secrets() {
        let fanout = ObservabilityFanout::new(&[ObservabilityExporter::LangFuseOtlp {
            base_url: Some("https://cloud.langfuse.com".to_string()),
            public_key_env: "MISSING_PUBLIC".to_string(),
            secret_key_env: "MISSING_SECRET".to_string(),
            environment_env: "MISSING_ENVIRONMENT".to_string(),
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
}
