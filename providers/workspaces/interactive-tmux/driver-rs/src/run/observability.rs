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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::run::contract::{AgentRunEventPayload, AgentRunOutcome};

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
}
