            let kind = if signal == SIGTERM {
                SignalKind::Terminate
            } else {
                SignalKind::Interrupt
            };
            escalator.on_signal(kind, &cancel);
        }
    });
    Some((handle, join))
}

#[derive(Debug, Clone, Default)]
struct LangFuseCliOptions {
    enabled: bool,
    base_url: Option<String>,
    project_id: Option<String>,
    label: Option<String>,
}

fn build_observability_exporters(
    observability_file: Option<PathBuf>,
    file_label: &str,
    langfuse: LangFuseCliOptions,
) -> Vec<ObservabilityExporter> {
    let mut exporters: Vec<_> = observability_file
        .map(|path| ObservabilityExporter::File {
            path,
            label: Some(file_label.to_string()),
        })
        .into_iter()
        .collect();

    if langfuse.enabled {
        exporters.push(ObservabilityExporter::LangFuseOtlp {
            base_url: langfuse.base_url,
            public_key_env: "LANGFUSE_PUBLIC_KEY".to_string(),
            secret_key_env: "LANGFUSE_SECRET_KEY".to_string(),
            environment_env: "LANGFUSE_TRACING_ENVIRONMENT".to_string(),
            project_id: langfuse.project_id,
            project_id_env: "LANGFUSE_PROJECT_ID".to_string(),
            service_name: "agentic-primitives".to_string(),
            label: langfuse
                .label
                .or_else(|| Some("LangFuse trace".to_string())),
        });
    }

    exporters
}

fn resolve_codex_exec_model(explicit_model: Option<String>) -> Option<String> {


Baseline finding: build_observability_exporters currently pushes ObservabilityExporter::LangFuseOtlp whenever langfuse.enabled is true. It does not inspect TRACE_TO_LANGFUSE or any official-plugin active signal, so official plugin tracing plus --observability-langfuse can configure both rich writers.
