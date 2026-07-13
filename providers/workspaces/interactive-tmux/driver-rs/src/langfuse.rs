use std::collections::{BTreeMap, BTreeSet};
use std::process::ExitCode;
use std::time::Duration;

use clap::ValueEnum;
use serde::Serialize;
use serde_json::{json, Value};

use itmux::run::observability::{
    langfuse_api_base_url, langfuse_basic_auth_header, langfuse_trace_id_for_run,
};

const LANGFUSE_TRACE_QUERY_TIMEOUT: Duration = Duration::from_secs(10);
pub(crate) const DEFAULT_LANGFUSE_QUERY_FROM_START_TIME: &str = "2020-01-01T00:00:00Z";
pub(crate) const DEFAULT_LANGFUSE_QUERY_TO_START_TIME: &str = "2100-01-01T00:00:00Z";

#[derive(Debug, Clone, Copy, ValueEnum)]
pub(crate) enum LangFuseTraceApi {
    /// Recommended row-level API for current LangFuse Cloud/newer deployments.
    ObservationsV2,
    /// Compatibility path for self-hosted deployments that do not expose v2.
    LegacyTrace,
}

impl LangFuseTraceApi {
    fn as_str(self) -> &'static str {
        match self {
            Self::ObservationsV2 => "observations_v2",
            Self::LegacyTrace => "legacy_trace",
        }
    }
}

#[derive(Debug, Clone, Copy, ValueEnum)]
pub(crate) enum LangFuseTraceOutput {
    /// Emit only the agent-facing learning-loop summary.
    Summary,
    /// Emit the summary plus the raw LangFuse response.
    Full,
}

#[derive(Debug, Clone, Copy, ValueEnum)]
pub(crate) enum LangFuseScoreDataType {
    Numeric,
    Boolean,
    Categorical,
    Text,
}

impl LangFuseScoreDataType {
    fn as_langfuse(self) -> &'static str {
        match self {
            Self::Numeric => "NUMERIC",
            Self::Boolean => "BOOLEAN",
            Self::Categorical => "CATEGORICAL",
            Self::Text => "TEXT",
        }
    }

    fn parse_value(self, value: &str) -> Result<Value, String> {
        match self {
            Self::Numeric => {
                let number = value
                    .parse::<f64>()
                    .map_err(|_| "NUMERIC scores require a finite JSON number".to_string())?;
                if !number.is_finite() {
                    return Err("NUMERIC scores require a finite JSON number".to_string());
                }
                serde_json::Number::from_f64(number)
                    .map(Value::Number)
                    .ok_or_else(|| "NUMERIC scores require a finite JSON number".to_string())
            }
            Self::Boolean => match value {
                "1" | "true" | "TRUE" | "True" => Ok(Value::Number(1.into())),
                "0" | "false" | "FALSE" | "False" => Ok(Value::Number(0.into())),
                _ => Err("BOOLEAN scores require one of true, false, 1, or 0".to_string()),
            },
            Self::Categorical | Self::Text => Ok(Value::String(value.to_string())),
        }
    }
}

#[derive(Serialize)]
struct LangFuseTraceQueryRequest {
    api: &'static str,
    endpoint: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    scores_endpoint: Option<String>,
    trace_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    run_id: Option<String>,
    fields: String,
    limit: u32,
    include_scores: bool,
    score_limit: u32,
    from_start_time: String,
    to_start_time: String,
}

#[derive(Serialize)]
struct LangFuseTracesListRequest {
    endpoint: String,
    limit: u32,
    page: u32,
    #[serde(skip_serializing_if = "Option::is_none")]
    harness: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    provider: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    model: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    environment: Option<String>,
}

#[derive(Serialize)]
struct LangFuseSessionsListRequest {
    endpoint: String,
    limit: u32,
    page: u32,
    #[serde(skip_serializing_if = "Option::is_none")]
    harness: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    provider: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    model: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    environment: Option<String>,
    include_scores: bool,
    score_limit: u32,
}

#[derive(Serialize)]
struct LangFuseScoreCreateRequest {
    endpoint: String,
    trace_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    run_id: Option<String>,
    name: String,
    data_type: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    score_id: Option<String>,
}

#[derive(Serialize)]
struct LangFuseScoresListRequest {
    endpoint: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    trace_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    run_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    score_ids: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    data_type: Option<&'static str>,
    limit: u32,
    page: u32,
}

#[allow(clippy::too_many_arguments)]
pub(crate) fn handle_langfuse_trace(
    trace_id: Option<String>,
    run_id: Option<String>,
    base_url: Option<String>,
    public_key_env: String,
    secret_key_env: String,
    from_start_time: String,
    to_start_time: String,
    fields: String,
    limit: u32,
    include_scores: bool,
    score_limit: u32,
    api: LangFuseTraceApi,
    output: LangFuseTraceOutput,
) -> ExitCode {
    let Some(trace_id) = trace_id.or_else(|| run_id.as_deref().map(langfuse_trace_id_for_run))
    else {
        println!(
            "{}",
            json!({
                "ok": false,
                "error": "provide exactly one of --trace-id or --run-id"
            })
        );
        return ExitCode::from(2);
    };

    let mut missing = Vec::new();
    let base_url = base_url
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .or_else(|| non_empty_env("LANGFUSE_BASE_URL"))
        .unwrap_or_else(|| {
            missing.push("LANGFUSE_BASE_URL".to_string());
            String::new()
        });
    let public_key = non_empty_env(&public_key_env).unwrap_or_else(|| {
        missing.push(public_key_env.clone());
        String::new()
    });
    let secret_key = non_empty_env(&secret_key_env).unwrap_or_else(|| {
        missing.push(secret_key_env.clone());
        String::new()
    });

    if !missing.is_empty() {
        println!(
            "{}",
            json!({
                "ok": false,
                "error": "missing required LangFuse query configuration",
                "missing": missing,
            })
        );
        return ExitCode::from(78);
    }

    let endpoint = build_langfuse_trace_query_url(
        api,
        &base_url,
        &trace_id,
        &from_start_time,
        &to_start_time,
        &fields,
        limit,
    );
    let scores_endpoint = include_scores.then(|| {
        build_langfuse_scores_list_url(&base_url, Some(&trace_id), None, None, None, score_limit, 1)
    });
    let request = LangFuseTraceQueryRequest {
        api: api.as_str(),
        endpoint: endpoint.clone(),
        scores_endpoint: scores_endpoint.clone(),
        trace_id: trace_id.clone(),
        run_id: run_id.clone(),
        fields,
        limit,
        include_scores,
        score_limit,
        from_start_time,
        to_start_time,
    };

    let response = ureq::get(&endpoint)
        .timeout(LANGFUSE_TRACE_QUERY_TIMEOUT)
        .set(
            "Authorization",
            &langfuse_basic_auth_header(&public_key, &secret_key),
        )
        .call();

    match response {
        Ok(response) if (200..300).contains(&response.status()) => {
            let body = response.into_string().unwrap_or_default();
            let parsed = match serde_json::from_str::<Value>(&body) {
                Ok(parsed) => parsed,
                Err(err) => {
                    println!(
                        "{}",
                        serde_json::to_string_pretty(&json!({
                            "ok": false,
                            "request": request,
                            "error": "invalid LangFuse trace JSON response",
                            "parse_error": err.to_string(),
                            "body": body,
                        }))
                        .unwrap()
                    );
                    return ExitCode::from(1);
                }
            };
            let mut summary = summarize_langfuse_trace_response(&parsed);
            let mut scores_response = None;
            if let Some(scores_endpoint) = scores_endpoint {
                match query_langfuse_json(&scores_endpoint, &public_key, &secret_key) {
                    Ok(score_payload) => {
                        let scores_request = LangFuseScoresListRequest {
                            endpoint: scores_endpoint,
                            trace_id: Some(trace_id),
                            run_id,
                            score_ids: None,
                            name: None,
                            data_type: None,
                            limit: score_limit,
                            page: 1,
                        };
                        let score_summary =
                            summarize_langfuse_scores_response(&score_payload, &scores_request);
                        if let Some(summary) = summary.as_object_mut() {
                            summary.insert("scores".to_string(), score_summary);
                        }
                        scores_response = Some(score_payload);
                    }
                    Err(error) => {
                        if let Some(summary) = summary.as_object_mut() {
                            summary.insert("scores_error".to_string(), error);
                        }
                    }
                }
            }
            let output = match output {
                LangFuseTraceOutput::Summary => json!({
                    "ok": true,
                    "request": request,
                    "summary": summary,
                }),
                LangFuseTraceOutput::Full => json!({
                    "ok": true,
                    "request": request,
                    "summary": summary,
                    "response": parsed,
                    "scores_response": scores_response,
                }),
            };
            println!("{}", serde_json::to_string_pretty(&output).unwrap());
            ExitCode::SUCCESS
        }
        Ok(response) => {
            let status = response.status();
            let status_text = response.status_text().to_string();
            let body = response.into_string().unwrap_or_default();
            println!(
                "{}",
                serde_json::to_string_pretty(&json!({
                    "ok": false,
                    "request": request,
                    "status": status,
                    "status_text": status_text,
                    "body": body,
                }))
                .unwrap()
            );
            ExitCode::from(1)
        }
        Err(ureq::Error::Status(status, response)) => {
            let status_text = response.status_text().to_string();
            let body = response.into_string().unwrap_or_default();
            println!(
                "{}",
                serde_json::to_string_pretty(&json!({
                    "ok": false,
                    "request": request,
                    "status": status,
                    "status_text": status_text,
                    "body": body,
                }))
                .unwrap()
            );
            ExitCode::from(1)
        }
        Err(err) => {
            println!(
                "{}",
                serde_json::to_string_pretty(&json!({
                    "ok": false,
                    "request": request,
                    "error": err.to_string(),
                }))
                .unwrap()
            );
            ExitCode::from(1)
        }
    }
}

#[allow(clippy::too_many_arguments)]
pub(crate) fn handle_langfuse_traces(
    base_url: Option<String>,
    public_key_env: String,
    secret_key_env: String,
    limit: u32,
    page: u32,
    harness: Option<String>,
    provider: Option<String>,
    model: Option<String>,
    environment: Option<String>,
    output: LangFuseTraceOutput,
) -> ExitCode {
    let mut missing = Vec::new();
    let base_url = base_url
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .or_else(|| non_empty_env("LANGFUSE_BASE_URL"))
        .unwrap_or_else(|| {
            missing.push("LANGFUSE_BASE_URL".to_string());
            String::new()
        });
    let public_key = non_empty_env(&public_key_env).unwrap_or_else(|| {
        missing.push(public_key_env.clone());
        String::new()
    });
    let secret_key = non_empty_env(&secret_key_env).unwrap_or_else(|| {
        missing.push(secret_key_env.clone());
        String::new()
    });

    if !missing.is_empty() {
        println!(
            "{}",
            json!({
                "ok": false,
                "error": "missing required LangFuse query configuration",
                "missing": missing,
            })
        );
        return ExitCode::from(78);
    }

    let endpoint = build_langfuse_traces_list_url(&base_url, limit, page);
    let request = LangFuseTracesListRequest {
        endpoint: endpoint.clone(),
        limit,
        page,
        harness: non_empty_string(harness),
        provider: non_empty_string(provider),
        model: non_empty_string(model),
        environment: non_empty_string(environment),
    };

    let response = ureq::get(&endpoint)
        .timeout(LANGFUSE_TRACE_QUERY_TIMEOUT)
        .set(
            "Authorization",
            &langfuse_basic_auth_header(&public_key, &secret_key),
        )
        .call();

    match response {
        Ok(response) if (200..300).contains(&response.status()) => {
            let body = response.into_string().unwrap_or_default();
            let parsed = serde_json::from_str::<Value>(&body).unwrap_or_else(|err| {
                json!({
                    "parse_error": err.to_string(),
                    "body": body,
                })
            });
            let summary = summarize_langfuse_traces_response(&parsed, &request);
            let output = match output {
                LangFuseTraceOutput::Summary => json!({
                    "ok": true,
                    "request": request,
                    "summary": summary,
                }),
                LangFuseTraceOutput::Full => json!({
                    "ok": true,
                    "request": request,
                    "summary": summary,
                    "response": parsed,
                }),
            };
            println!("{}", serde_json::to_string_pretty(&output).unwrap());
            ExitCode::SUCCESS
        }
        Ok(response) => {
            let status = response.status();
            let status_text = response.status_text().to_string();
            let body = response.into_string().unwrap_or_default();
            println!(
                "{}",
                serde_json::to_string_pretty(&json!({
                    "ok": false,
                    "request": request,
                    "status": status,
                    "status_text": status_text,
                    "body": body,
                }))
                .unwrap()
            );
            ExitCode::from(1)
        }
        Err(ureq::Error::Status(status, response)) => {
            let status_text = response.status_text().to_string();
            let body = response.into_string().unwrap_or_default();
            println!(
                "{}",
                serde_json::to_string_pretty(&json!({
                    "ok": false,
                    "request": request,
                    "status": status,
                    "status_text": status_text,
                    "body": body,
                }))
                .unwrap()
            );
            ExitCode::from(1)
        }
        Err(err) => {
            println!(
                "{}",
                serde_json::to_string_pretty(&json!({
                    "ok": false,
                    "request": request,
                    "error": err.to_string(),
                }))
                .unwrap()
            );
            ExitCode::from(1)
        }
    }
}

#[allow(clippy::too_many_arguments)]
pub(crate) fn handle_langfuse_sessions(
    base_url: Option<String>,
    public_key_env: String,
    secret_key_env: String,
    limit: u32,
    page: u32,
    harness: Option<String>,
    provider: Option<String>,
    model: Option<String>,
    environment: Option<String>,
    include_scores: bool,
    score_limit: u32,
    output: LangFuseTraceOutput,
) -> ExitCode {
    let mut missing = Vec::new();
    let base_url = base_url
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .or_else(|| non_empty_env("LANGFUSE_BASE_URL"))
        .unwrap_or_else(|| {
            missing.push("LANGFUSE_BASE_URL".to_string());
            String::new()
        });
    let public_key = non_empty_env(&public_key_env).unwrap_or_else(|| {
        missing.push(public_key_env.clone());
        String::new()
    });
    let secret_key = non_empty_env(&secret_key_env).unwrap_or_else(|| {
        missing.push(secret_key_env.clone());
        String::new()
    });
    if !missing.is_empty() {
        println!(
            "{}",
            json!({"ok": false, "error": "missing required LangFuse query configuration", "missing": missing})
        );
        return ExitCode::from(78);
    }

    let endpoint = build_langfuse_traces_list_url(&base_url, limit, page);
    let request = LangFuseSessionsListRequest {
        endpoint: endpoint.clone(),
        limit,
        page,
        harness: non_empty_string(harness),
        provider: non_empty_string(provider),
        model: non_empty_string(model),
        environment: non_empty_string(environment),
        include_scores,
        score_limit,
    };
    match query_langfuse_json(&endpoint, &public_key, &secret_key) {
        Ok(response) => {
            let trace_request = LangFuseTracesListRequest {
                endpoint: endpoint.clone(),
                limit,
                page,
                harness: request.harness.clone(),
                provider: request.provider.clone(),
                model: request.model.clone(),
                environment: request.environment.clone(),
            };
            let discovery = summarize_langfuse_traces_response(&response, &trace_request);
            let summary = summarize_langfuse_sessions_response(
                &discovery,
                &base_url,
                &public_key,
                &secret_key,
                &request,
            );
            let result = match output {
                LangFuseTraceOutput::Summary => {
                    json!({"ok": true, "request": request, "summary": summary})
                }
                LangFuseTraceOutput::Full => {
                    json!({"ok": true, "request": request, "summary": summary, "response": response})
                }
            };
            println!("{}", serde_json::to_string_pretty(&result).unwrap());
            ExitCode::SUCCESS
        }
        Err(error) => {
            println!(
                "{}",
                serde_json::to_string_pretty(
                    &json!({"ok": false, "request": request, "error": error})
                )
                .unwrap()
            );
            ExitCode::from(1)
        }
    }
}

#[allow(clippy::too_many_arguments)]
pub(crate) fn handle_langfuse_score(
    trace_id: Option<String>,
    run_id: Option<String>,
    base_url: Option<String>,
    public_key_env: String,
    secret_key_env: String,
    name: String,
    value: String,
    data_type: LangFuseScoreDataType,
    comment: Option<String>,
    metadata_json: Option<String>,
    score_id: Option<String>,
    environment: Option<String>,
    output: LangFuseTraceOutput,
) -> ExitCode {
    let Some(trace_id) = trace_id.or_else(|| run_id.as_deref().map(langfuse_trace_id_for_run))
    else {
        println!(
            "{}",
            json!({
                "ok": false,
                "error": "provide exactly one of --trace-id or --run-id"
            })
        );
        return ExitCode::from(2);
    };

    let score_value = match data_type.parse_value(&value) {
        Ok(value) => value,
        Err(error) => {
            println!(
                "{}",
                serde_json::to_string_pretty(&json!({
                    "ok": false,
                    "error": error,
                }))
                .unwrap()
            );
            return ExitCode::from(2);
        }
    };

    let metadata = match metadata_json {
        Some(raw) => match serde_json::from_str::<Value>(&raw) {
            Ok(value @ Value::Object(_)) => Some(value),
            Ok(_) => {
                println!(
                    "{}",
                    serde_json::to_string_pretty(&json!({
                        "ok": false,
                        "error": "--metadata-json must be a JSON object",
                    }))
                    .unwrap()
                );
                return ExitCode::from(2);
            }
            Err(err) => {
                println!(
                    "{}",
                    serde_json::to_string_pretty(&json!({
                        "ok": false,
                        "error": format!("invalid --metadata-json: {err}"),
                    }))
                    .unwrap()
                );
                return ExitCode::from(2);
            }
        },
        None => None,
    };

    let mut missing = Vec::new();
    let base_url = base_url
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .or_else(|| non_empty_env("LANGFUSE_BASE_URL"))
        .unwrap_or_else(|| {
            missing.push("LANGFUSE_BASE_URL".to_string());
            String::new()
        });
    let public_key = non_empty_env(&public_key_env).unwrap_or_else(|| {
        missing.push(public_key_env.clone());
        String::new()
    });
    let secret_key = non_empty_env(&secret_key_env).unwrap_or_else(|| {
        missing.push(secret_key_env.clone());
        String::new()
    });

    if !missing.is_empty() {
        println!(
            "{}",
            json!({
                "ok": false,
                "error": "missing required LangFuse query configuration",
                "missing": missing,
            })
        );
        return ExitCode::from(78);
    }

    let endpoint = build_langfuse_score_create_url(&base_url);
    let request = LangFuseScoreCreateRequest {
        endpoint: endpoint.clone(),
        trace_id: trace_id.clone(),
        run_id,
        name: name.clone(),
        data_type: data_type.as_langfuse(),
        score_id: non_empty_string(score_id.clone()),
    };

    let mut body = json!({
        "traceId": trace_id,
        "name": name,
        "value": score_value,
        "dataType": data_type.as_langfuse(),
    });
    if let Some(body) = body.as_object_mut() {
        if let Some(score_id) = non_empty_string(score_id) {
            body.insert("id".to_string(), Value::String(score_id));
        }
        if let Some(comment) = non_empty_string(comment) {
            body.insert("comment".to_string(), Value::String(comment));
        }
        if let Some(metadata) = metadata {
            body.insert("metadata".to_string(), metadata);
        }
        if let Some(environment) = non_empty_string(environment) {
            body.insert("environment".to_string(), Value::String(environment));
        }
    }

    let body = serde_json::to_string(&body).unwrap();
    let response = ureq::post(&endpoint)
        .timeout(LANGFUSE_TRACE_QUERY_TIMEOUT)
        .set("Content-Type", "application/json")
        .set(
            "Authorization",
            &langfuse_basic_auth_header(&public_key, &secret_key),
        )
        .send_string(&body);

    match response {
        Ok(response) if (200..300).contains(&response.status()) => {
            let body = response.into_string().unwrap_or_default();
            let parsed = serde_json::from_str::<Value>(&body).unwrap_or_else(|err| {
                json!({
                    "parse_error": err.to_string(),
                    "body": body,
                })
            });
            let summary = summarize_langfuse_score_response(&parsed, &request);
            let output = match output {
                LangFuseTraceOutput::Summary => json!({
                    "ok": true,
                    "request": request,
                    "summary": summary,
                }),
                LangFuseTraceOutput::Full => json!({
                    "ok": true,
                    "request": request,
                    "summary": summary,
                    "response": parsed,
                }),
            };
            println!("{}", serde_json::to_string_pretty(&output).unwrap());
            ExitCode::SUCCESS
        }
        Ok(response) => {
            let status = response.status();
            let status_text = response.status_text().to_string();
            let body = response.into_string().unwrap_or_default();
            println!(
                "{}",
                serde_json::to_string_pretty(&json!({
                    "ok": false,
                    "request": request,
                    "status": status,
                    "status_text": status_text,
                    "body": body,
                }))
                .unwrap()
            );
            ExitCode::from(1)
        }
        Err(ureq::Error::Status(status, response)) => {
            let status_text = response.status_text().to_string();
            let body = response.into_string().unwrap_or_default();
            println!(
                "{}",
                serde_json::to_string_pretty(&json!({
                    "ok": false,
                    "request": request,
                    "status": status,
                    "status_text": status_text,
                    "body": body,
                }))
                .unwrap()
            );
            ExitCode::from(1)
        }
        Err(err) => {
            println!(
                "{}",
                serde_json::to_string_pretty(&json!({
                    "ok": false,
                    "request": request,
                    "error": err.to_string(),
                }))
                .unwrap()
            );
            ExitCode::from(1)
        }
    }
}

#[allow(clippy::too_many_arguments)]
pub(crate) fn handle_langfuse_scores(
    trace_id: Option<String>,
    run_id: Option<String>,
    base_url: Option<String>,
    public_key_env: String,
    secret_key_env: String,
    score_ids: Option<String>,
    name: Option<String>,
    data_type: Option<LangFuseScoreDataType>,
    limit: u32,
    page: u32,
    output: LangFuseTraceOutput,
) -> ExitCode {
    let trace_id = trace_id.or_else(|| run_id.as_deref().map(langfuse_trace_id_for_run));

    let mut missing = Vec::new();
    let base_url = base_url
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .or_else(|| non_empty_env("LANGFUSE_BASE_URL"))
        .unwrap_or_else(|| {
            missing.push("LANGFUSE_BASE_URL".to_string());
            String::new()
        });
    let public_key = non_empty_env(&public_key_env).unwrap_or_else(|| {
        missing.push(public_key_env.clone());
        String::new()
    });
    let secret_key = non_empty_env(&secret_key_env).unwrap_or_else(|| {
        missing.push(secret_key_env.clone());
        String::new()
    });

    if !missing.is_empty() {
        println!(
            "{}",
            json!({
                "ok": false,
                "error": "missing required LangFuse query configuration",
                "missing": missing,
            })
        );
        return ExitCode::from(78);
    }

    let endpoint = build_langfuse_scores_list_url(
        &base_url,
        trace_id.as_deref(),
        score_ids.as_deref(),
        name.as_deref(),
        data_type.map(LangFuseScoreDataType::as_langfuse),
        limit,
        page,
    );
    let request = LangFuseScoresListRequest {
        endpoint: endpoint.clone(),
        trace_id,
        run_id,
        score_ids: non_empty_string(score_ids),
        name: non_empty_string(name),
        data_type: data_type.map(LangFuseScoreDataType::as_langfuse),
        limit,
        page,
    };

    let response = ureq::get(&endpoint)
        .timeout(LANGFUSE_TRACE_QUERY_TIMEOUT)
        .set(
            "Authorization",
            &langfuse_basic_auth_header(&public_key, &secret_key),
        )
        .call();

    match response {
        Ok(response) if (200..300).contains(&response.status()) => {
            let body = response.into_string().unwrap_or_default();
            let parsed = serde_json::from_str::<Value>(&body).unwrap_or_else(|err| {
                json!({
                    "parse_error": err.to_string(),
                    "body": body,
                })
            });
            let summary = summarize_langfuse_scores_response(&parsed, &request);
            let output = match output {
                LangFuseTraceOutput::Summary => json!({
                    "ok": true,
                    "request": request,
                    "summary": summary,
                }),
                LangFuseTraceOutput::Full => json!({
                    "ok": true,
                    "request": request,
                    "summary": summary,
                    "response": parsed,
                }),
            };
            println!("{}", serde_json::to_string_pretty(&output).unwrap());
            ExitCode::SUCCESS
        }
        Ok(response) => {
            let status = response.status();
            let status_text = response.status_text().to_string();
            let body = response.into_string().unwrap_or_default();
            println!(
                "{}",
                serde_json::to_string_pretty(&json!({
                    "ok": false,
                    "request": request,
                    "status": status,
                    "status_text": status_text,
                    "body": body,
                }))
                .unwrap()
            );
            ExitCode::from(1)
        }
        Err(ureq::Error::Status(status, response)) => {
            let status_text = response.status_text().to_string();
            let body = response.into_string().unwrap_or_default();
            println!(
                "{}",
                serde_json::to_string_pretty(&json!({
                    "ok": false,
                    "request": request,
                    "status": status,
                    "status_text": status_text,
                    "body": body,
                }))
                .unwrap()
            );
            ExitCode::from(1)
        }
        Err(err) => {
            println!(
                "{}",
                serde_json::to_string_pretty(&json!({
                    "ok": false,
                    "request": request,
                    "error": err.to_string(),
                }))
                .unwrap()
            );
            ExitCode::from(1)
        }
    }
}

fn non_empty_env(key: &str) -> Option<String> {
    std::env::var(key)
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
}

fn non_empty_string(value: Option<String>) -> Option<String> {
    value
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
}

fn query_langfuse_json(endpoint: &str, public_key: &str, secret_key: &str) -> Result<Value, Value> {
    let response = ureq::get(endpoint)
        .timeout(LANGFUSE_TRACE_QUERY_TIMEOUT)
        .set(
            "Authorization",
            &langfuse_basic_auth_header(public_key, secret_key),
        )
        .call();

    match response {
        Ok(response) if (200..300).contains(&response.status()) => {
            let body = response.into_string().unwrap_or_default();
            Ok(serde_json::from_str::<Value>(&body).unwrap_or_else(|err| {
                json!({
                    "parse_error": err.to_string(),
                    "body": body,
                })
            }))
        }
        Ok(response) => {
            let status = response.status();
            let status_text = response.status_text().to_string();
            let body = response.into_string().unwrap_or_default();
            Err(json!({
                "status": status,
                "status_text": status_text,
                "body": body,
            }))
        }
        Err(ureq::Error::Status(status, response)) => {
            let status_text = response.status_text().to_string();
            let body = response.into_string().unwrap_or_default();
            Err(json!({
                "status": status,
                "status_text": status_text,
                "body": body,
            }))
        }
        Err(err) => Err(json!({
            "error": err.to_string(),
        })),
    }
}

fn summarize_langfuse_trace_response(response: &Value) -> Value {
    let trace = response
        .get("response")
        .and_then(Value::as_object)
        .map(|_| response.get("response").unwrap())
        .unwrap_or(response);
    let official_trace = infer_official_plugin_trace(trace);
    let observations = trace
        .get("observations")
        .and_then(Value::as_array)
        .cloned()
        .or_else(|| trace.get("data").and_then(Value::as_array).cloned())
        .unwrap_or_default();

    let mut names = BTreeSet::new();
    let mut types = BTreeSet::new();
    let mut environments = BTreeSet::new();
    let mut models = BTreeSet::new();
    let mut model_ids = BTreeSet::new();
    let mut harnesses = BTreeSet::new();
    let mut providers = BTreeSet::new();
    let mut total_tokens = 0_u64;
    let mut input_tokens = 0_u64;
    let mut output_tokens = 0_u64;
    let mut calculated_total_cost = 0.0_f64;
    let mut has_cost = false;
    let mut tool_stats: BTreeMap<String, ToolTraceStats> = BTreeMap::new();
    let mut tool_events = Vec::new();
    let mut operation_stats: BTreeMap<String, ToolTraceStats> = BTreeMap::new();
    let mut operation_events = Vec::new();
    let mut agent_tool_stats: BTreeMap<String, ToolTraceStats> = BTreeMap::new();
    let mut agent_tool_events = Vec::new();
    let mut harness_tool_stats: BTreeMap<String, ToolTraceStats> = BTreeMap::new();
    let mut harness_tool_events = Vec::new();
    let mut category_counts: BTreeMap<String, u64> = BTreeMap::new();
    let mut trace_events = Vec::new();
    let mut generation_stats: BTreeMap<String, GenerationTraceStats> = BTreeMap::new();
    let mut generation_events = Vec::new();

    for observation in &observations {
        insert_string(&mut names, observation.get("name"));
        insert_string(&mut types, observation.get("type"));
        insert_string(&mut environments, observation.get("environment"));
        insert_string(&mut models, observation.get("model"));
        insert_string(&mut model_ids, observation.get("modelId"));

        let observation_input_tokens = usage_number(observation, "input")
            .or_else(|| Some(number_u64(observation.get("promptTokens"))))
            .unwrap_or(0);
        let observation_output_tokens = usage_number(observation, "output")
            .or_else(|| Some(number_u64(observation.get("completionTokens"))))
            .unwrap_or(0);
        let observation_total_tokens = usage_number(observation, "total")
            .or_else(|| Some(number_u64(observation.get("totalTokens"))))
            .unwrap_or(0);
        let is_generation = is_generation_observation(observation, observation_total_tokens);
        if is_generation {
            input_tokens = input_tokens.saturating_add(observation_input_tokens);
            output_tokens = output_tokens.saturating_add(observation_output_tokens);
            total_tokens = total_tokens.saturating_add(observation_total_tokens);
        }

        if is_generation {
            if let Some(cost) = total_cost_number(observation) {
                calculated_total_cost += cost;
                has_cost = true;
            }
        }

        let attrs = observation
            .get("metadata")
            .and_then(|metadata| metadata.get("attributes"));
        let event_seq = attr_u64(attrs, "agentic.event.seq");
        insert_string(
            &mut harnesses,
            attrs.and_then(|attrs| attrs.get("agentic.harness")),
        );
        insert_string(
            &mut providers,
            attrs.and_then(|attrs| attrs.get("agentic.provider")),
        );
        insert_string(
            &mut models,
            attrs.and_then(|attrs| attrs.get("agentic.model")),
        );

        let metadata_event_type = attr_string(attrs, "agentic.event.type");
        let observation_type = observation.get("type").and_then(Value::as_str);
        let is_official_tool_observation = matches!(observation_type, Some("TOOL"))
            && !matches!(
                metadata_event_type.as_deref(),
                Some("tool_start" | "tool_end")
            );
        let official_tool_name = is_official_tool_observation
            .then(|| langfuse_tool_observation_name(observation, attrs));
        let event_type = metadata_event_type.clone().or_else(|| {
            if is_official_tool_observation {
                Some("tool".to_string())
            } else {
                observation
                    .get("name")
                    .and_then(Value::as_str)
                    .map(str::to_string)
            }
        });
        let tool_name = attr_string(attrs, "agentic.tool.name").or(official_tool_name);
        let category = if is_official_tool_observation {
            "agent_tool"
        } else {
            classify_trace_event(event_type.as_deref(), tool_name.as_deref())
        };
        *category_counts.entry(category.to_string()).or_default() += 1;
        if let Some(event_type) = event_type.clone() {
            trace_events.push(TraceEvent {
                seq: event_seq,
                sort_time: observation
                    .get("startTime")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                sort_id: observation
                    .get("id")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                event: event_type,
                name: observation
                    .get("name")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                category: category.to_string(),
                tool_name: tool_name.clone(),
                harness: attr_string(attrs, "agentic.harness"),
                provider: attr_string(attrs, "agentic.provider"),
                model: attr_string(attrs, "agentic.model").or_else(|| {
                    observation
                        .get("model")
                        .and_then(Value::as_str)
                        .map(str::to_string)
                }),
                success: attr_bool(attrs, "agentic.tool.success")
                    .or_else(|| attr_bool(attrs, "agentic.outcome.success")),
                total_tokens: number_u64(observation.get("totalTokens")),
                calculated_total_cost: number_f64(observation.get("calculatedTotalCost")),
            });
        }
        if is_generation {
            let model = observation
                .get("model")
                .and_then(Value::as_str)
                .map(str::to_string)
                .or_else(|| attr_string(attrs, "agentic.model"))
                .unwrap_or_else(|| "unknown".to_string());
            let model_id = observation
                .get("modelId")
                .and_then(Value::as_str)
                .map(str::to_string);
            let harness = attr_string(attrs, "agentic.harness");
            let provider = attr_string(attrs, "agentic.provider");
            let input_cost = cost_number(observation, "input")
                .or_else(|| number_f64(observation.get("calculatedInputCost")));
            let output_cost = cost_number(observation, "output")
                .or_else(|| number_f64(observation.get("calculatedOutputCost")));
            let total_cost =
                cost_number(observation, "total").or_else(|| total_cost_number(observation));
            let stats = generation_stats.entry(model.clone()).or_default();
            stats.count = stats.count.saturating_add(1);
            stats.input_tokens = stats.input_tokens.saturating_add(observation_input_tokens);
            stats.output_tokens = stats
                .output_tokens
                .saturating_add(observation_output_tokens);
            stats.total_tokens = stats.total_tokens.saturating_add(observation_total_tokens);
            if let Some(cost) = total_cost {
                stats.calculated_total_usd += cost;
                stats.has_cost = true;
            }
            if let Some(provider) = provider.as_ref() {
                stats.providers.insert(provider.clone());
            }
            if let Some(harness) = harness.as_ref() {
                stats.harnesses.insert(harness.clone());
            }
            if let Some(model_id) = model_id.as_ref() {
                stats.model_ids.insert(model_id.clone());
            }
            generation_events.push(GenerationTraceEvent {
                seq: event_seq,
                sort_time: observation
                    .get("startTime")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                sort_id: observation
                    .get("id")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                observation_id: observation
                    .get("id")
                    .and_then(Value::as_str)
                    .map(str::to_string),
                name: observation
                    .get("name")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                model,
                model_id,
                harness,
                provider,
                input_tokens: observation_input_tokens,
                output_tokens: observation_output_tokens,
                total_tokens: observation_total_tokens,
                cached_input_tokens: usage_number(observation, "cached_prompt_tokens")
                    .or_else(|| usage_number(observation, "cachedInput"))
                    .or_else(|| usage_number(observation, "cached_input_tokens")),
                reasoning_output_tokens: usage_number(observation, "reasoning_completion_tokens")
                    .or_else(|| usage_number(observation, "reasoningOutput"))
                    .or_else(|| usage_number(observation, "reasoning_output_tokens")),
                calculated_input_cost_usd: input_cost,
                calculated_output_cost_usd: output_cost,
                calculated_total_cost_usd: total_cost,
                pricing_tier: observation
                    .get("usagePricingTierName")
                    .and_then(Value::as_str)
                    .map(str::to_string),
                unit: observation
                    .get("unit")
                    .and_then(Value::as_str)
                    .map(str::to_string),
            });
        }
        if matches!(event_type.as_deref(), Some("tool_start" | "tool_end")) {
            let event_type_value = event_type.clone().unwrap_or_else(|| "unknown".to_string());
            let tool_name = tool_name.clone().unwrap_or_else(|| "unknown".to_string());
            let success = attr_bool(attrs, "agentic.tool.success");
            let stats = tool_stats.entry(tool_name.clone()).or_default();
            update_tool_trace_stats(stats, event_type.as_deref(), success);
            tool_events.push(ToolTraceEvent {
                seq: event_seq,
                sort_time: observation
                    .get("startTime")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                sort_id: observation
                    .get("id")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                event: event_type_value.clone(),
                tool_name: tool_name.clone(),
                success,
            });
            let category_group = match category {
                "operation" => Some((&mut operation_stats, &mut operation_events)),
                "agent_tool" => Some((&mut agent_tool_stats, &mut agent_tool_events)),
                "harness_tool" => Some((&mut harness_tool_stats, &mut harness_tool_events)),
                _ => None,
            };
            if let Some((stats_by_name, events)) = category_group {
                let stats = stats_by_name.entry(tool_name.clone()).or_default();
                update_tool_trace_stats(stats, event_type.as_deref(), success);
                events.push(ToolTraceEvent {
                    seq: event_seq,
                    sort_time: observation
                        .get("startTime")
                        .and_then(Value::as_str)
                        .unwrap_or_default()
                        .to_string(),
                    sort_id: observation
                        .get("id")
                        .and_then(Value::as_str)
                        .unwrap_or_default()
                        .to_string(),
                    event: event_type_value,
                    tool_name,
                    success,
                });
            }
        }
        if is_official_tool_observation {
            let tool_name = tool_name.unwrap_or_else(|| "unknown".to_string());
            let success = official_tool_observation_success(observation, attrs);
            let stats = tool_stats.entry(tool_name.clone()).or_default();
            record_completed_tool_observation(stats, success);
            tool_events.push(ToolTraceEvent {
                seq: event_seq,
                sort_time: observation
                    .get("startTime")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                sort_id: observation
                    .get("id")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                event: "tool".to_string(),
                tool_name: tool_name.clone(),
                success,
            });

            let stats = agent_tool_stats.entry(tool_name.clone()).or_default();
            record_completed_tool_observation(stats, success);
            agent_tool_events.push(ToolTraceEvent {
                seq: event_seq,
                sort_time: observation
                    .get("startTime")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                sort_id: observation
                    .get("id")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string(),
                event: "tool".to_string(),
                tool_name,
                success,
            });
        }
    }

    let category_counts = category_counts
        .into_iter()
        .map(|(category, count)| {
            json!({
                "category": category,
                "count": count,
            })
        })
        .collect::<Vec<_>>();
    let event_sequence_source = if trace_events.iter().any(|event| event.seq.is_some()) {
        Some("agentic.event.seq")
    } else {
        None
    };
    trace_events.sort_by(|a, b| {
        a.seq
            .unwrap_or(u64::MAX)
            .cmp(&b.seq.unwrap_or(u64::MAX))
            .then_with(|| a.sort_time.cmp(&b.sort_time))
            .then_with(|| a.sort_id.cmp(&b.sort_id))
    });
    let event_sequence_truncated = trace_events.len() > 200;
    let event_sequence = trace_events
        .into_iter()
        .take(200)
        .map(|event| {
            json!({
                "seq": event.seq,
                "event": event.event,
                "name": event.name,
                "category": event.category,
                "tool_name": event.tool_name,
                "harness": event.harness,
                "provider": event.provider,
                "model": event.model,
                "success": event.success,
                "total_tokens": event.total_tokens,
                "calculated_total_cost": event.calculated_total_cost,
            })
        })
        .collect::<Vec<_>>();
    let tools = summarize_tool_trace_group(tool_stats, tool_events, 100);
    let operations = summarize_tool_trace_group(operation_stats, operation_events, 100);
    let agent_tools = summarize_tool_trace_group(agent_tool_stats, agent_tool_events, 100);
    let harness_tools = summarize_tool_trace_group(harness_tool_stats, harness_tool_events, 100);
    let generations = summarize_generation_trace_group(generation_stats, generation_events, 100);
    if let Some(inference) = official_trace {
        harnesses.insert(inference.harness.to_string());
        providers.insert(inference.provider.to_string());
    }

    json!({
        "trace_id": trace.get("id").and_then(Value::as_str),
        "trace_name": trace.get("name").and_then(Value::as_str),
        "session_id": trace.get("sessionId").and_then(Value::as_str),
        "environment": trace.get("environment").and_then(Value::as_str),
        "observation_count": observations.len(),
        "observation_names": names.into_iter().collect::<Vec<_>>(),
        "observation_types": types.into_iter().collect::<Vec<_>>(),
        "environments": environments.into_iter().collect::<Vec<_>>(),
        "harnesses": harnesses.into_iter().collect::<Vec<_>>(),
        "providers": providers.into_iter().collect::<Vec<_>>(),
        "models": models.into_iter().collect::<Vec<_>>(),
        "model_ids": model_ids.into_iter().collect::<Vec<_>>(),
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        },
        "cost": {
            "calculated_total_usd": if has_cost { Some(calculated_total_cost) } else { None },
        },
        "events": {
            "sequence_source": event_sequence_source,
            "category_counts": category_counts,
            "sequence": event_sequence,
            "sequence_truncated": event_sequence_truncated,
        },
        "tools": tools,
        "operations": operations,
        "agent_tools": agent_tools,
        "harness_tools": harness_tools,
        "generations": generations,
    })
}

fn summarize_langfuse_score_response(
    response: &Value,
    request: &LangFuseScoreCreateRequest,
) -> Value {
    json!({
        "score_id": response.get("id").and_then(Value::as_str),
        "trace_id": request.trace_id,
        "run_id": request.run_id,
        "name": request.name,
        "data_type": request.data_type,
        "created": response.get("id").and_then(Value::as_str).is_some(),
    })
}

fn summarize_langfuse_scores_response(
    response: &Value,
    request: &LangFuseScoresListRequest,
) -> Value {
    let rows = response
        .get("data")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let scores = rows
        .iter()
        .filter(|score| score_matches_scores_request(score, request))
        .map(|score| {
            let trace = score.get("trace");
            json!({
                "score_id": score.get("id").and_then(Value::as_str),
                "trace_id": score.get("traceId").and_then(Value::as_str),
                "observation_id": score.get("observationId").and_then(Value::as_str),
                "name": score.get("name").and_then(Value::as_str),
                "data_type": score.get("dataType").and_then(Value::as_str),
                "value": score.get("value"),
                "string_value": score.get("stringValue").and_then(Value::as_str),
                "source": score.get("source").and_then(Value::as_str),
                "environment": score.get("environment").and_then(Value::as_str),
                "comment": score.get("comment").and_then(Value::as_str),
                "metadata": score.get("metadata"),
                "created_at": score.get("createdAt").and_then(Value::as_str),
                "updated_at": score.get("updatedAt").and_then(Value::as_str),
                "trace_environment": trace
                    .and_then(|trace| trace.get("environment"))
                    .and_then(Value::as_str),
                "trace_tags": trace
                    .and_then(|trace| trace.get("tags"))
                    .and_then(Value::as_array),
            })
        })
        .collect::<Vec<_>>();

    json!({
        "requested_trace_id": request.trace_id,
        "requested_run_id": request.run_id,
        "requested_name": request.name,
        "requested_score_ids": request.score_ids,
        "returned_count": scores.len(),
        "total_items": response
            .get("meta")
            .and_then(|meta| meta.get("totalItems"))
            .and_then(Value::as_u64),
        "scores": scores,
    })
}

fn score_matches_scores_request(score: &Value, request: &LangFuseScoresListRequest) -> bool {
    if let Some(expected) = request
        .trace_id
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
    {
        if score
            .get("traceId")
            .and_then(Value::as_str)
            .map(|actual| actual != expected)
            .unwrap_or(true)
        {
            return false;
        }
    }
    if let Some(expected_ids) = request
        .score_ids
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
    {
        let score_id = score.get("id").and_then(Value::as_str);
        let expected = expected_ids
            .split(',')
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .collect::<Vec<_>>();
        if !expected.is_empty() && !score_id.is_some_and(|actual| expected.contains(&actual)) {
            return false;
        }
    }
    if let Some(expected) = request
        .name
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
    {
        if score
            .get("name")
            .and_then(Value::as_str)
            .map(|actual| actual != expected)
            .unwrap_or(true)
        {
            return false;
        }
    }
    if let Some(expected) = request
        .data_type
        .map(str::trim)
        .filter(|value| !value.is_empty())
    {
        if score
            .get("dataType")
            .and_then(Value::as_str)
            .map(|actual| !actual.eq_ignore_ascii_case(expected))
            .unwrap_or(true)
        {
            return false;
        }
    }
    true
}

fn summarize_langfuse_traces_response(
    response: &Value,
    request: &LangFuseTracesListRequest,
) -> Value {
    let rows = response
        .get("data")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let mut traces = Vec::new();
    let mut harnesses = BTreeSet::new();
    let mut providers = BTreeSet::new();
    let mut models = BTreeSet::new();
    let mut environments = BTreeSet::new();
    let mut total_cost = 0.0_f64;
    let mut has_cost = false;

    for trace in rows {
        let metadata = trace.get("metadata");
        let official_trace = infer_official_plugin_trace(&trace);
        let harness = metadata_string(metadata, "harness")
            .or_else(|| {
                trace
                    .get("tags")
                    .and_then(Value::as_array)
                    .and_then(|tags| {
                        tags.iter().find_map(|tag| {
                            tag.as_str()
                                .and_then(|tag| tag.strip_prefix("harness:"))
                                .map(ToOwned::to_owned)
                        })
                    })
            })
            .or_else(|| official_trace.map(|inference| inference.harness.to_string()));
        let provider = metadata_string(metadata, "provider")
            .or_else(|| official_trace.map(|inference| inference.provider.to_string()));
        let model = metadata_string(metadata, "model");
        let environment = trace
            .get("environment")
            .and_then(Value::as_str)
            .map(ToOwned::to_owned)
            .or_else(|| metadata_string(metadata, "langfuse.environment"));

        if !filter_matches(&harness, request.harness.as_deref())
            || !filter_matches(&provider, request.provider.as_deref())
            || !filter_matches(&model, request.model.as_deref())
            || !filter_matches(&environment, request.environment.as_deref())
        {
            continue;
        }

        if let Some(value) = harness.as_ref() {
            harnesses.insert(value.clone());
        }
        if let Some(value) = provider.as_ref() {
            providers.insert(value.clone());
        }
        if let Some(value) = model.as_ref() {
            models.insert(value.clone());
        }
        if let Some(value) = environment.as_ref() {
            environments.insert(value.clone());
        }
        if let Some(cost) = number_f64(trace.get("totalCost")) {
            total_cost += cost;
            has_cost = true;
        }

        let observation_count = trace
            .get("observations")
            .and_then(Value::as_array)
            .map(|observations| observations.len())
            .unwrap_or(0);
        traces.push(json!({
            "trace_id": trace.get("id").and_then(Value::as_str),
            "run_id": metadata_string(metadata, "run_id")
                .or_else(|| trace.get("sessionId").and_then(Value::as_str).map(ToOwned::to_owned)),
            "session_id": trace.get("sessionId").and_then(Value::as_str),
            "name": trace.get("name").and_then(Value::as_str),
            "timestamp": trace.get("timestamp").and_then(Value::as_str),
            "created_at": trace.get("createdAt").and_then(Value::as_str),
            "updated_at": trace.get("updatedAt").and_then(Value::as_str),
            "environment": environment,
            "harness": harness,
            "provider": provider,
            "model": model,
            "total_cost": number_f64(trace.get("totalCost")),
            "latency_s": number_f64(trace.get("latency")),
            "observation_count": observation_count,
            "html_path": trace.get("htmlPath").and_then(Value::as_str),
        }));
    }

    json!({
        "page": request.page,
        "limit": request.limit,
        "returned_count": traces.len(),
        "backend_total_items": response.pointer("/meta/totalItems").and_then(Value::as_u64),
        "backend_total_pages": response.pointer("/meta/totalPages").and_then(Value::as_u64),
        "filters": {
            "harness": request.harness,
            "provider": request.provider,
            "model": request.model,
            "environment": request.environment,
        },
        "harnesses": harnesses.into_iter().collect::<Vec<_>>(),
        "providers": providers.into_iter().collect::<Vec<_>>(),
        "models": models.into_iter().collect::<Vec<_>>(),
        "environments": environments.into_iter().collect::<Vec<_>>(),
        "total_cost": if has_cost { Some(total_cost) } else { None },
        "traces": traces,
    })
}

fn summarize_langfuse_sessions_response(
    discovery: &Value,
    base_url: &str,
    public_key: &str,
    secret_key: &str,
    request: &LangFuseSessionsListRequest,
) -> Value {
    let traces = discovery
        .get("traces")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let mut sessions: BTreeMap<String, Vec<Value>> = BTreeMap::new();
    let mut unscoped_trace_count = 0_u64;
    let mut errors = Vec::new();

    for row in &traces {
        let Some(trace_id) = row.get("trace_id").and_then(Value::as_str) else {
            errors.push(json!({"trace": row, "error": "trace discovery row has no trace_id"}));
            continue;
        };
        let Some(session_id) = row.get("session_id").and_then(Value::as_str) else {
            unscoped_trace_count = unscoped_trace_count.saturating_add(1);
            continue;
        };
        let endpoint = build_langfuse_trace_query_url(
            LangFuseTraceApi::LegacyTrace,
            base_url,
            trace_id,
            DEFAULT_LANGFUSE_QUERY_FROM_START_TIME,
            DEFAULT_LANGFUSE_QUERY_TO_START_TIME,
            "core,basic,usage,trace_context",
            500,
        );
        let mut detail = match query_langfuse_json(&endpoint, public_key, secret_key) {
            Ok(payload) => summarize_langfuse_trace_response(&payload),
            Err(error) => {
                errors.push(json!({"trace_id": trace_id, "error": error}));
                continue;
            }
        };
        if request.include_scores {
            let scores_endpoint = build_langfuse_scores_list_url(
                base_url,
                Some(trace_id),
                None,
                None,
                None,
                request.score_limit,
                1,
            );
            match query_langfuse_json(&scores_endpoint, public_key, secret_key) {
                Ok(payload) => {
                    let score_request = LangFuseScoresListRequest {
                        endpoint: scores_endpoint,
                        trace_id: Some(trace_id.to_string()),
                        run_id: None,
                        score_ids: None,
                        name: None,
                        data_type: None,
                        limit: request.score_limit,
                        page: 1,
                    };
                    detail["scores"] = summarize_langfuse_scores_response(&payload, &score_request);
                }
                Err(error) => detail["scores_error"] = error,
            }
        }
        detail["timestamp"] = row.get("timestamp").cloned().unwrap_or(Value::Null);
        detail["html_path"] = row.get("html_path").cloned().unwrap_or(Value::Null);
        sessions
            .entry(session_id.to_string())
            .or_default()
            .push(detail);
    }

    let sessions = sessions
        .into_iter()
        .map(|(session_id, details)| {
            summarize_langfuse_session(&session_id, details, request.include_scores)
        })
        .collect::<Vec<_>>();
    json!({
        "page": request.page,
        "limit": request.limit,
        "filters": {
            "harness": request.harness,
            "provider": request.provider,
            "model": request.model,
            "environment": request.environment,
        },
        "session_count": sessions.len(),
        "unscoped_trace_count": unscoped_trace_count,
        "backend_total_trace_items": discovery.get("backend_total_items"),
        "sessions": sessions,
        "errors": errors,
    })
}

fn summarize_langfuse_session(
    session_id: &str,
    details: Vec<Value>,
    include_scores: bool,
) -> Value {
    let mut trace_ids = Vec::new();
    let mut harnesses = BTreeSet::new();
    let mut providers = BTreeSet::new();
    let mut models = BTreeSet::new();
    let mut environments = BTreeSet::new();
    let mut tool_names = BTreeSet::new();
    let mut total_tokens = 0_u64;
    let mut total_cost = 0.0_f64;
    let mut has_cost = false;
    let mut tool_count = 0_u64;
    let mut tool_success_count = 0_u64;
    let mut tool_failure_count = 0_u64;
    let mut scores = Vec::new();
    let mut trace_rows = Vec::new();

    for detail in details {
        if let Some(trace_id) = detail.get("trace_id").and_then(Value::as_str) {
            trace_ids.push(trace_id.to_string());
        }
        for (key, target) in [
            ("harnesses", &mut harnesses),
            ("providers", &mut providers),
            ("models", &mut models),
            ("environments", &mut environments),
        ] {
            if let Some(values) = detail.get(key).and_then(Value::as_array) {
                for value in values.iter().filter_map(Value::as_str) {
                    target.insert(value.to_string());
                }
            }
        }
        total_tokens = total_tokens.saturating_add(
            detail
                .pointer("/usage/total_tokens")
                .and_then(Value::as_u64)
                .unwrap_or(0),
        );
        if let Some(cost) = detail
            .pointer("/cost/calculated_total_usd")
            .and_then(|value| number_f64(Some(value)))
        {
            total_cost += cost;
            has_cost = true;
        }
        if let Some(agent_tools) = detail.get("agent_tools") {
            tool_count = tool_count.saturating_add(
                agent_tools
                    .get("end_count")
                    .and_then(Value::as_u64)
                    .unwrap_or(0),
            );
            tool_success_count = tool_success_count.saturating_add(
                agent_tools
                    .get("success_count")
                    .and_then(Value::as_u64)
                    .unwrap_or(0),
            );
            tool_failure_count = tool_failure_count.saturating_add(
                agent_tools
                    .get("failure_count")
                    .and_then(Value::as_u64)
                    .unwrap_or(0),
            );
            if let Some(names) = agent_tools.get("names").and_then(Value::as_array) {
                for name in names.iter().filter_map(Value::as_str) {
                    tool_names.insert(name.to_string());
                }
            }
        }
        if include_scores {
            if let Some(values) = detail.pointer("/scores/scores").and_then(Value::as_array) {
                scores.extend(values.iter().cloned());
            }
        }
        trace_rows.push(json!({
            "trace_id": detail.get("trace_id"),
            "trace_name": detail.get("trace_name"),
            "timestamp": detail.get("timestamp"),
            "html_path": detail.get("html_path"),
            "usage": detail.get("usage"),
            "cost": detail.get("cost"),
            "agent_tools": detail.get("agent_tools"),
        }));
    }

    json!({
        "session_id": session_id,
        "turn_count": trace_rows.len(),
        "trace_ids": trace_ids,
        "harnesses": harnesses.into_iter().collect::<Vec<_>>(),
        "providers": providers.into_iter().collect::<Vec<_>>(),
        "models": models.into_iter().collect::<Vec<_>>(),
        "environments": environments.into_iter().collect::<Vec<_>>(),
        "usage": {"total_tokens": total_tokens},
        "cost": {"calculated_total_usd": if has_cost { Some(total_cost) } else { None }},
        "tools": {
            "count": tool_count,
            "success_count": tool_success_count,
            "failure_count": tool_failure_count,
            "names": tool_names.into_iter().collect::<Vec<_>>(),
        },
        "scores": if include_scores { Some(scores) } else { None },
        "traces": trace_rows,
    })
}

#[derive(Debug, Clone, Copy)]
struct OfficialPluginTraceInference {
    harness: &'static str,
    provider: &'static str,
}

fn infer_official_plugin_trace(trace: &Value) -> Option<OfficialPluginTraceInference> {
    let name = trace
        .get("name")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if name.starts_with("Codex Turn") {
        return Some(OfficialPluginTraceInference {
            harness: "codex",
            provider: "openai",
        });
    }
    if name.starts_with("Claude Code") || name.starts_with("Conversational Turn") {
        return Some(OfficialPluginTraceInference {
            harness: "claude",
            provider: "anthropic",
        });
    }
    None
}

#[derive(Debug, Default)]
struct ToolTraceStats {
    starts: u64,
    ends: u64,
    successes: u64,
    failures: u64,
}

#[derive(Debug, Default)]
struct GenerationTraceStats {
    count: u64,
    input_tokens: u64,
    output_tokens: u64,
    total_tokens: u64,
    calculated_total_usd: f64,
    has_cost: bool,
    providers: BTreeSet<String>,
    harnesses: BTreeSet<String>,
    model_ids: BTreeSet<String>,
}

#[derive(Debug)]
struct ToolTraceEvent {
    seq: Option<u64>,
    sort_time: String,
    sort_id: String,
    event: String,
    tool_name: String,
    success: Option<bool>,
}

#[derive(Debug)]
struct GenerationTraceEvent {
    seq: Option<u64>,
    sort_time: String,
    sort_id: String,
    observation_id: Option<String>,
    name: String,
    model: String,
    model_id: Option<String>,
    harness: Option<String>,
    provider: Option<String>,
    input_tokens: u64,
    output_tokens: u64,
    total_tokens: u64,
    cached_input_tokens: Option<u64>,
    reasoning_output_tokens: Option<u64>,
    calculated_input_cost_usd: Option<f64>,
    calculated_output_cost_usd: Option<f64>,
    calculated_total_cost_usd: Option<f64>,
    pricing_tier: Option<String>,
    unit: Option<String>,
}

#[derive(Debug)]
struct TraceEvent {
    seq: Option<u64>,
    sort_time: String,
    sort_id: String,
    event: String,
    name: String,
    category: String,
    tool_name: Option<String>,
    harness: Option<String>,
    provider: Option<String>,
    model: Option<String>,
    success: Option<bool>,
    total_tokens: u64,
    calculated_total_cost: Option<f64>,
}

fn update_tool_trace_stats(
    stats: &mut ToolTraceStats,
    event_type: Option<&str>,
    success: Option<bool>,
) {
    match event_type {
        Some("tool_start") => stats.starts = stats.starts.saturating_add(1),
        Some("tool_end") => {
            stats.ends = stats.ends.saturating_add(1);
            match success {
                Some(true) => stats.successes = stats.successes.saturating_add(1),
                Some(false) => stats.failures = stats.failures.saturating_add(1),
                None => {}
            }
        }
        _ => {}
    }
}

fn record_completed_tool_observation(stats: &mut ToolTraceStats, success: Option<bool>) {
    stats.ends = stats.ends.saturating_add(1);
    match success {
        Some(true) => stats.successes = stats.successes.saturating_add(1),
        Some(false) => stats.failures = stats.failures.saturating_add(1),
        None => {}
    }
}

fn langfuse_tool_observation_name(observation: &Value, attrs: Option<&Value>) -> String {
    attr_string(attrs, "agentic.tool.name")
        .or_else(|| {
            observation
                .get("name")
                .and_then(Value::as_str)
                .map(|name| name.strip_prefix("Tool: ").unwrap_or(name).to_string())
        })
        .filter(|name| !name.trim().is_empty())
        .unwrap_or_else(|| "unknown".to_string())
}

fn official_tool_observation_success(observation: &Value, attrs: Option<&Value>) -> Option<bool> {
    attr_bool(attrs, "agentic.tool.success").or_else(|| {
        let level = observation
            .get("level")
            .and_then(Value::as_str)
            .unwrap_or_default();
        if level.eq_ignore_ascii_case("ERROR") {
            Some(false)
        } else {
            Some(true)
        }
    })
}

fn summarize_tool_trace_group(
    stats: BTreeMap<String, ToolTraceStats>,
    mut events: Vec<ToolTraceEvent>,
    limit: usize,
) -> Value {
    let start_count = stats.values().map(|stats| stats.starts).sum::<u64>();
    let end_count = stats.values().map(|stats| stats.ends).sum::<u64>();
    let success_count = stats.values().map(|stats| stats.successes).sum::<u64>();
    let failure_count = stats.values().map(|stats| stats.failures).sum::<u64>();
    let names = stats.keys().cloned().collect::<Vec<_>>();
    let by_name = stats
        .into_iter()
        .map(|(name, stats)| {
            json!({
                "name": name,
                "starts": stats.starts,
                "ends": stats.ends,
                "successes": stats.successes,
                "failures": stats.failures,
            })
        })
        .collect::<Vec<_>>();
    let sequence_source = if events.iter().any(|event| event.seq.is_some()) {
        Some("agentic.event.seq")
    } else {
        None
    };
    events.sort_by(|a, b| {
        a.seq
            .unwrap_or(u64::MAX)
            .cmp(&b.seq.unwrap_or(u64::MAX))
            .then_with(|| a.sort_time.cmp(&b.sort_time))
            .then_with(|| a.sort_id.cmp(&b.sort_id))
    });
    let sequence_truncated = events.len() > limit;
    let sequence = events
        .into_iter()
        .take(limit)
        .map(|event| {
            json!({
                "seq": event.seq,
                "event": event.event,
                "tool_name": event.tool_name,
                "success": event.success,
            })
        })
        .collect::<Vec<_>>();

    json!({
        "start_count": start_count,
        "end_count": end_count,
        "success_count": success_count,
        "failure_count": failure_count,
        "names": names,
        "by_name": by_name,
        "sequence_source": sequence_source,
        "sequence": sequence,
        "sequence_truncated": sequence_truncated,
    })
}

fn summarize_generation_trace_group(
    stats: BTreeMap<String, GenerationTraceStats>,
    mut events: Vec<GenerationTraceEvent>,
    max_sequence: usize,
) -> Value {
    let mut total_count = 0_u64;
    let mut input_tokens = 0_u64;
    let mut output_tokens = 0_u64;
    let mut total_tokens = 0_u64;
    let mut calculated_total_usd = 0.0_f64;
    let mut has_cost = false;
    let by_model = stats
        .into_iter()
        .map(|(model, stats)| {
            total_count = total_count.saturating_add(stats.count);
            input_tokens = input_tokens.saturating_add(stats.input_tokens);
            output_tokens = output_tokens.saturating_add(stats.output_tokens);
            total_tokens = total_tokens.saturating_add(stats.total_tokens);
            if stats.has_cost {
                calculated_total_usd += stats.calculated_total_usd;
                has_cost = true;
            }
            json!({
                "model": model,
                "model_ids": stats.model_ids.into_iter().collect::<Vec<_>>(),
                "providers": stats.providers.into_iter().collect::<Vec<_>>(),
                "harnesses": stats.harnesses.into_iter().collect::<Vec<_>>(),
                "count": stats.count,
                "input_tokens": stats.input_tokens,
                "output_tokens": stats.output_tokens,
                "total_tokens": stats.total_tokens,
                "calculated_total_usd": if stats.has_cost {
                    Some(stats.calculated_total_usd)
                } else {
                    None
                },
            })
        })
        .collect::<Vec<_>>();

    let sequence_source = if events.iter().any(|event| event.seq.is_some()) {
        Some("agentic.event.seq")
    } else {
        None
    };
    events.sort_by(|a, b| {
        a.seq
            .unwrap_or(u64::MAX)
            .cmp(&b.seq.unwrap_or(u64::MAX))
            .then_with(|| a.sort_time.cmp(&b.sort_time))
            .then_with(|| a.sort_id.cmp(&b.sort_id))
    });
    let sequence_truncated = events.len() > max_sequence;
    let sequence = events
        .into_iter()
        .take(max_sequence)
        .map(|event| {
            json!({
                "seq": event.seq,
                "observation_id": event.observation_id,
                "name": event.name,
                "model": event.model,
                "model_id": event.model_id,
                "harness": event.harness,
                "provider": event.provider,
                "input_tokens": event.input_tokens,
                "output_tokens": event.output_tokens,
                "total_tokens": event.total_tokens,
                "cached_input_tokens": event.cached_input_tokens,
                "reasoning_output_tokens": event.reasoning_output_tokens,
                "calculated_input_cost_usd": event.calculated_input_cost_usd,
                "calculated_output_cost_usd": event.calculated_output_cost_usd,
                "calculated_total_cost_usd": event.calculated_total_cost_usd,
                "pricing_tier": event.pricing_tier,
                "unit": event.unit,
            })
        })
        .collect::<Vec<_>>();

    json!({
        "count": total_count,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "calculated_total_usd": if has_cost {
            Some(calculated_total_usd)
        } else {
            None
        },
        "by_model": by_model,
        "sequence_source": sequence_source,
        "sequence": sequence,
        "sequence_truncated": sequence_truncated,
    })
}

fn classify_trace_event(event_type: Option<&str>, tool_name: Option<&str>) -> &'static str {
    match event_type {
        Some("tool_start" | "tool_end") => classify_tool_event(tool_name),
        Some("token_usage") => "usage",
        Some("hook_event") => "hook",
        Some("session_end") => "session",
        Some("agentic_primitives.run") => "root",
        Some(_) | None => "other",
    }
}

fn classify_tool_event(tool_name: Option<&str>) -> &'static str {
    match tool_name.unwrap_or_default() {
        "provision" | "launch" | "submit" | "await" | "capture" => "operation",
        name if name.starts_with("codex_exec.thread")
            || name.starts_with("codex_exec.turn")
            || name.starts_with("codex_exec.error")
            || name.starts_with("claude_transcript.") =>
        {
            "harness_tool"
        }
        name if name.starts_with("codex_exec.item.") => "agent_tool",
        "" | "unknown" => "other",
        _ => "agent_tool",
    }
}

fn insert_string(out: &mut BTreeSet<String>, value: Option<&Value>) {
    if let Some(value) = value.and_then(Value::as_str) {
        if !value.trim().is_empty() {
            out.insert(value.to_string());
        }
    }
}

fn attr_string(attrs: Option<&Value>, key: &str) -> Option<String> {
    attrs
        .and_then(|attrs| attrs.get(key))
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToOwned::to_owned)
}

fn attr_bool(attrs: Option<&Value>, key: &str) -> Option<bool> {
    attrs.and_then(|attrs| attrs.get(key)).and_then(|value| {
        value.as_bool().or_else(|| match value.as_str()?.trim() {
            "true" => Some(true),
            "false" => Some(false),
            _ => None,
        })
    })
}

fn attr_u64(attrs: Option<&Value>, key: &str) -> Option<u64> {
    attrs.and_then(|attrs| attrs.get(key)).and_then(|value| {
        value
            .as_u64()
            .or_else(|| value.as_str()?.trim().parse().ok())
    })
}

fn metadata_string(metadata: Option<&Value>, key: &str) -> Option<String> {
    metadata
        .and_then(|metadata| metadata.get(key))
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToOwned::to_owned)
}

fn filter_matches(value: &Option<String>, expected: Option<&str>) -> bool {
    let Some(expected) = expected.map(str::trim).filter(|value| !value.is_empty()) else {
        return true;
    };
    value
        .as_deref()
        .is_some_and(|value| value.eq_ignore_ascii_case(expected))
}

fn number_u64(value: Option<&Value>) -> u64 {
    value
        .and_then(|value| {
            value
                .as_u64()
                .or_else(|| value.as_f64().map(|v| v.max(0.0) as u64))
        })
        .unwrap_or(0)
}

fn number_f64(value: Option<&Value>) -> Option<f64> {
    value.and_then(|value| value.as_f64().or_else(|| value.as_u64().map(|v| v as f64)))
}

fn usage_number(observation: &Value, key: &str) -> Option<u64> {
    observation
        .get("usageDetails")
        .and_then(|details| details.get(key))
        .map(Some)
        .map(number_u64)
        .filter(|value| *value > 0)
        .or_else(|| {
            observation
                .get("usage")
                .and_then(|usage| usage.get(key))
                .map(Some)
                .map(number_u64)
                .filter(|value| *value > 0)
        })
}

fn cost_number(observation: &Value, key: &str) -> Option<f64> {
    observation
        .get("costDetails")
        .and_then(|details| details.get(key))
        .and_then(|value| number_f64(Some(value)))
}

fn total_cost_number(observation: &Value) -> Option<f64> {
    cost_number(observation, "total")
        .or_else(|| number_f64(observation.get("calculatedTotalCost")))
        .or_else(|| number_f64(observation.get("totalCost")))
}

fn is_generation_observation(observation: &Value, total_tokens: u64) -> bool {
    match observation.get("type").and_then(Value::as_str) {
        Some("GENERATION") => true,
        Some(_) => false,
        None => total_tokens > 0,
    }
}

fn build_langfuse_observations_v2_url(
    base_url: &str,
    trace_id: &str,
    from_start_time: &str,
    to_start_time: &str,
    fields: &str,
    limit: u32,
) -> String {
    let base = langfuse_api_base_url(base_url);
    format!(
        "{}/api/public/v2/observations?traceId={}&fromStartTime={}&toStartTime={}&fields={}&limit={}",
        base.trim_end_matches('/'),
        url_query_encode(trace_id),
        url_query_encode(from_start_time),
        url_query_encode(to_start_time),
        url_query_encode(fields),
        limit
    )
}

fn build_langfuse_trace_query_url(
    api: LangFuseTraceApi,
    base_url: &str,
    trace_id: &str,
    from_start_time: &str,
    to_start_time: &str,
    fields: &str,
    limit: u32,
) -> String {
    match api {
        LangFuseTraceApi::ObservationsV2 => build_langfuse_observations_v2_url(
            base_url,
            trace_id,
            from_start_time,
            to_start_time,
            fields,
            limit,
        ),
        LangFuseTraceApi::LegacyTrace => {
            let base = langfuse_api_base_url(base_url);
            format!(
                "{}/api/public/traces/{}",
                base.trim_end_matches('/'),
                url_path_encode(trace_id)
            )
        }
    }
}

fn build_langfuse_traces_list_url(base_url: &str, limit: u32, page: u32) -> String {
    let base = langfuse_api_base_url(base_url);
    format!(
        "{}/api/public/traces?limit={}&page={}",
        base.trim_end_matches('/'),
        limit,
        page
    )
}

fn build_langfuse_score_create_url(base_url: &str) -> String {
    let base = langfuse_api_base_url(base_url);
    format!("{}/api/public/scores", base.trim_end_matches('/'))
}

fn build_langfuse_scores_list_url(
    base_url: &str,
    trace_id: Option<&str>,
    score_ids: Option<&str>,
    name: Option<&str>,
    data_type: Option<&str>,
    limit: u32,
    page: u32,
) -> String {
    let base = langfuse_api_base_url(base_url);
    let mut params = vec![format!("limit={limit}"), format!("page={page}")];
    // LangFuse self-host score list filters can under-return when several
    // filters are combined. Send one narrowing filter to the backend, then
    // enforce every requested filter in summarize_langfuse_scores_response.
    if let Some(score_ids) = non_empty_str(score_ids) {
        params.push(format!("scoreIds={}", url_query_encode(score_ids)));
    } else if let Some(trace_id) = non_empty_str(trace_id) {
        params.push(format!("traceId={}", url_query_encode(trace_id)));
    } else if let Some(name) = non_empty_str(name) {
        params.push(format!("name={}", url_query_encode(name)));
    } else if let Some(data_type) = non_empty_str(data_type) {
        params.push(format!("dataType={}", url_query_encode(data_type)));
    }
    format!(
        "{}/api/public/scores?{}",
        base.trim_end_matches('/'),
        params.join("&")
    )
}

fn non_empty_str(value: Option<&str>) -> Option<&str> {
    value.map(str::trim).filter(|value| !value.is_empty())
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

fn url_query_encode(value: &str) -> String {
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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{Cli, Cmd};
    use clap::Parser;

    #[test]
    fn langfuse_trace_query_url_is_bounded_and_encoded() {
        let url = build_langfuse_trace_query_url(
            LangFuseTraceApi::ObservationsV2,
            "https://langfuse.example.com/api/public/otel/v1/traces",
            "abc123",
            "2026-07-07T20:00:00Z",
            "2026-07-07T20:30:00Z",
            "core,basic,usage,trace_context",
            25,
        );

        assert_eq!(
            url,
            "https://langfuse.example.com/api/public/v2/observations?traceId=abc123&fromStartTime=2026-07-07T20%3A00%3A00Z&toStartTime=2026-07-07T20%3A30%3A00Z&fields=core%2Cbasic%2Cusage%2Ctrace_context&limit=25"
        );
    }

    #[test]
    fn langfuse_trace_query_supports_legacy_self_host_trace_api() {
        let url = build_langfuse_trace_query_url(
            LangFuseTraceApi::LegacyTrace,
            "https://langfuse.example.com/api/public/otel",
            "trace id/with spaces",
            "2026-07-07T20:00:00Z",
            "2026-07-07T20:30:00Z",
            "core,basic",
            25,
        );

        assert_eq!(
            url,
            "https://langfuse.example.com/api/public/traces/trace%20id%2Fwith%20spaces"
        );
    }

    #[test]
    fn langfuse_trace_cli_defaults_are_agent_friendly() {
        let cli = Cli::try_parse_from([
            "itmux",
            "langfuse-trace",
            "--run-id",
            "run-query",
            "--api",
            "legacy-trace",
            "--output",
            "summary",
        ])
        .unwrap();

        let Cmd::LangFuseTrace {
            run_id,
            from_start_time,
            to_start_time,
            output,
            ..
        } = cli.cmd
        else {
            panic!("expected langfuse-trace command");
        };

        assert_eq!(run_id.as_deref(), Some("run-query"));
        assert_eq!(from_start_time, DEFAULT_LANGFUSE_QUERY_FROM_START_TIME);
        assert_eq!(to_start_time, DEFAULT_LANGFUSE_QUERY_TO_START_TIME);
        assert!(matches!(output, LangFuseTraceOutput::Summary));
    }

    #[test]
    fn langfuse_trace_cli_can_include_scores() {
        let cli = Cli::try_parse_from([
            "itmux",
            "langfuse-trace",
            "--run-id",
            "run-query",
            "--include-scores",
            "--score-limit",
            "7",
            "--output",
            "summary",
        ])
        .unwrap();

        let Cmd::LangFuseTrace {
            include_scores,
            score_limit,
            output,
            ..
        } = cli.cmd
        else {
            panic!("expected langfuse-trace command");
        };

        assert!(include_scores);
        assert_eq!(score_limit, 7);
        assert!(matches!(output, LangFuseTraceOutput::Summary));
    }

    #[test]
    fn langfuse_traces_list_url_uses_public_traces_endpoint() {
        let url = build_langfuse_traces_list_url(
            "https://langfuse.example.com/api/public/otel/v1/traces",
            25,
            2,
        );

        assert_eq!(
            url,
            "https://langfuse.example.com/api/public/traces?limit=25&page=2"
        );
    }

    #[test]
    fn langfuse_traces_cli_defaults_to_summary_output() {
        let cli = Cli::try_parse_from([
            "itmux",
            "langfuse-traces",
            "--limit",
            "5",
            "--harness",
            "claude",
        ])
        .unwrap();

        let Cmd::LangFuseTraces {
            limit,
            page,
            harness,
            output,
            ..
        } = cli.cmd
        else {
            panic!("expected langfuse-traces command");
        };

        assert_eq!(limit, 5);
        assert_eq!(page, 1);
        assert_eq!(harness.as_deref(), Some("claude"));
        assert!(matches!(output, LangFuseTraceOutput::Summary));
    }

    #[test]
    fn langfuse_sessions_cli_groups_turns_and_includes_scores_by_default() {
        let cli = Cli::try_parse_from([
            "itmux",
            "langfuse-sessions",
            "--limit",
            "5",
            "--harness",
            "codex",
        ])
        .unwrap();

        let Cmd::LangFuseSessions {
            limit,
            page,
            harness,
            include_scores,
            output,
            ..
        } = cli.cmd
        else {
            panic!("expected langfuse-sessions command");
        };

        assert_eq!(limit, 5);
        assert_eq!(page, 1);
        assert_eq!(harness.as_deref(), Some("codex"));
        assert!(include_scores);
        assert!(matches!(output, LangFuseTraceOutput::Summary));
    }

    #[test]
    fn langfuse_session_summary_rolls_up_turn_cost_tools_and_scores() {
        let summary = summarize_langfuse_session(
            "session-1",
            vec![
                json!({
                    "trace_id": "trace-1",
                    "trace_name": "Codex Turn 1",
                    "timestamp": "2026-07-13T00:00:00Z",
                    "harnesses": ["codex"],
                    "providers": ["openai"],
                    "models": ["gpt-5.6"],
                    "environments": ["local-macbook"],
                    "usage": {"total_tokens": 100},
                    "cost": {"calculated_total_usd": 0.25},
                    "agent_tools": {"end_count": 2, "success_count": 1, "failure_count": 1, "names": ["exec_command"]},
                    "scores": {"scores": [{"score_id": "score-1", "value": 1}]}
                }),
                json!({
                    "trace_id": "trace-2",
                    "trace_name": "Codex Turn 2",
                    "harnesses": ["codex"],
                    "providers": ["openai"],
                    "models": ["gpt-5.6"],
                    "environments": ["local-macbook"],
                    "usage": {"total_tokens": 40},
                    "cost": {"calculated_total_usd": 0.10},
                    "agent_tools": {"end_count": 1, "success_count": 1, "failure_count": 0, "names": ["read_file"]},
                    "scores": {"scores": []}
                }),
            ],
            true,
        );

        assert_eq!(summary["session_id"], "session-1");
        assert_eq!(summary["turn_count"], 2);
        assert_eq!(summary["usage"]["total_tokens"], 140);
        assert_eq!(summary["cost"]["calculated_total_usd"], json!(0.35));
        assert_eq!(summary["tools"]["count"], 3);
        assert_eq!(summary["tools"]["failure_count"], 1);
        assert_eq!(summary["scores"][0]["score_id"], "score-1");
    }

    #[test]
    fn langfuse_score_create_url_uses_public_scores_endpoint() {
        let url = build_langfuse_score_create_url(
            "https://langfuse.example.com/api/public/otel/v1/traces",
        );

        assert_eq!(url, "https://langfuse.example.com/api/public/scores");
    }

    #[test]
    fn langfuse_score_value_parser_matches_public_api_contract() {
        assert_eq!(
            LangFuseScoreDataType::Numeric.parse_value("0.75").unwrap(),
            json!(0.75)
        );
        assert_eq!(
            LangFuseScoreDataType::Boolean.parse_value("true").unwrap(),
            json!(1)
        );
        assert_eq!(
            LangFuseScoreDataType::Categorical
                .parse_value("useful")
                .unwrap(),
            json!("useful")
        );
        assert!(LangFuseScoreDataType::Numeric
            .parse_value("useful")
            .is_err());
    }

    #[test]
    fn langfuse_score_cli_defaults_to_summary_output() {
        let cli = Cli::try_parse_from([
            "itmux",
            "langfuse-score",
            "--run-id",
            "run-query",
            "--name",
            "agentic.learning_loop_probe",
            "--value",
            "1",
        ])
        .unwrap();

        let Cmd::LangFuseScore {
            run_id,
            name,
            data_type,
            output,
            ..
        } = cli.cmd
        else {
            panic!("expected langfuse-score command");
        };

        assert_eq!(run_id.as_deref(), Some("run-query"));
        assert_eq!(name, "agentic.learning_loop_probe");
        assert!(matches!(data_type, LangFuseScoreDataType::Numeric));
        assert!(matches!(output, LangFuseTraceOutput::Summary));
    }

    #[test]
    fn langfuse_scores_list_url_filters_feedback_fields() {
        let url = build_langfuse_scores_list_url(
            "https://langfuse.example.com/api/public/otel/v1/traces",
            Some("trace id/with spaces"),
            Some("score-a,score-b"),
            Some("agentic.learning_loop_probe"),
            Some("BOOLEAN"),
            10,
            2,
        );

        assert_eq!(
            url,
            "https://langfuse.example.com/api/public/scores?limit=10&page=2&scoreIds=score-a%2Cscore-b"
        );
    }

    #[test]
    fn langfuse_scores_list_url_uses_single_backend_filter_then_local_filtering() {
        let trace_and_name = build_langfuse_scores_list_url(
            "https://langfuse.example.com",
            Some("trace-wanted"),
            None,
            Some("agentic.learning_loop_probe"),
            Some("BOOLEAN"),
            20,
            1,
        );
        assert_eq!(
            trace_and_name,
            "https://langfuse.example.com/api/public/scores?limit=20&page=1&traceId=trace-wanted"
        );

        let name_and_type = build_langfuse_scores_list_url(
            "https://langfuse.example.com",
            None,
            None,
            Some("agentic.learning_loop_probe"),
            Some("BOOLEAN"),
            20,
            1,
        );
        assert_eq!(
            name_and_type,
            "https://langfuse.example.com/api/public/scores?limit=20&page=1&name=agentic.learning_loop_probe"
        );
    }

    #[test]
    fn langfuse_scores_cli_defaults_to_summary_output() {
        let cli = Cli::try_parse_from([
            "itmux",
            "langfuse-scores",
            "--run-id",
            "run-query",
            "--score-ids",
            "score-a",
            "--name",
            "agentic.learning_loop_probe",
        ])
        .unwrap();

        let Cmd::LangFuseScores {
            run_id,
            score_ids,
            name,
            limit,
            page,
            output,
            ..
        } = cli.cmd
        else {
            panic!("expected langfuse-scores command");
        };

        assert_eq!(run_id.as_deref(), Some("run-query"));
        assert_eq!(score_ids.as_deref(), Some("score-a"));
        assert_eq!(name.as_deref(), Some("agentic.learning_loop_probe"));
        assert_eq!(limit, 20);
        assert_eq!(page, 1);
        assert!(matches!(output, LangFuseTraceOutput::Summary));
    }

    #[test]
    fn langfuse_scores_summary_filters_backend_rows_client_side() {
        let response = json!({
            "meta": {"totalItems": 3},
            "data": [
                {
                    "id": "score-good",
                    "traceId": "trace-wanted",
                    "name": "agentic.learning_loop_probe",
                    "dataType": "BOOLEAN",
                    "value": 1
                },
                {
                    "id": "score-other-trace",
                    "traceId": "trace-other",
                    "name": "agentic.learning_loop_probe",
                    "dataType": "BOOLEAN",
                    "value": 1
                },
                {
                    "id": "score-other-name",
                    "traceId": "trace-wanted",
                    "name": "agentic.other",
                    "dataType": "BOOLEAN",
                    "value": 1
                }
            ]
        });
        let request = LangFuseScoresListRequest {
            endpoint: "https://langfuse.example.com/api/public/scores".to_string(),
            trace_id: Some("trace-wanted".to_string()),
            run_id: Some("run-wanted".to_string()),
            score_ids: Some("score-good,missing-score".to_string()),
            name: Some("agentic.learning_loop_probe".to_string()),
            data_type: Some("BOOLEAN"),
            limit: 20,
            page: 1,
        };

        let summary = summarize_langfuse_scores_response(&response, &request);

        assert_eq!(summary["returned_count"], 1);
        assert_eq!(summary["total_items"], 3);
        assert_eq!(summary["scores"][0]["score_id"], "score-good");
        assert_eq!(summary["scores"][0]["trace_id"], "trace-wanted");
    }

    #[test]
    fn langfuse_traces_summary_filters_and_extracts_learning_loop_fields() {
        let response = json!({
            "data": [
                {
                    "id": "trace-codex",
                    "name": "agentic_primitives.run",
                    "timestamp": "2026-07-08T03:26:12.000Z",
                    "createdAt": "2026-07-08T03:26:14.571Z",
                    "updatedAt": "2026-07-08T03:26:14.584Z",
                    "environment": "local-macbook",
                    "sessionId": "run-codex",
                    "metadata": {
                        "run_id": "run-codex",
                        "harness": "codex",
                        "provider": "openai",
                        "model": "gpt-5.5"
                    },
                    "observations": ["obs-1", "obs-2"],
                    "totalCost": 0.25,
                    "latency": 2.0,
                    "htmlPath": "/project/p/traces/trace-codex"
                },
                {
                    "id": "trace-claude",
                    "name": "agentic_primitives.run",
                    "timestamp": "2026-07-08T03:15:34.000Z",
                    "environment": "local-macbook",
                    "sessionId": "run-claude",
                    "metadata": {
                        "run_id": "run-claude",
                        "harness": "claude",
                        "provider": "anthropic",
                        "model": "claude-sonnet-4-6"
                    },
                    "observations": ["obs-1"],
                    "totalCost": 0.5,
                    "latency": 6.0,
                    "htmlPath": "/project/p/traces/trace-claude"
                }
            ],
            "meta": {
                "page": 1,
                "limit": 2,
                "totalItems": 2,
                "totalPages": 1
            }
        });
        let request = LangFuseTracesListRequest {
            endpoint: "https://langfuse.example.com/api/public/traces?limit=2&page=1".to_string(),
            limit: 2,
            page: 1,
            harness: Some("claude".to_string()),
            provider: None,
            model: None,
            environment: None,
        };

        let summary = summarize_langfuse_traces_response(&response, &request);

        assert_eq!(summary["returned_count"], 1);
        assert_eq!(summary["backend_total_items"], 2);
        assert_eq!(summary["harnesses"], json!(["claude"]));
        assert_eq!(summary["providers"], json!(["anthropic"]));
        assert_eq!(summary["models"], json!(["claude-sonnet-4-6"]));
        assert_eq!(summary["total_cost"], json!(0.5));
        assert_eq!(summary["traces"][0]["trace_id"], "trace-claude");
        assert_eq!(summary["traces"][0]["run_id"], "run-claude");
        assert_eq!(summary["traces"][0]["observation_count"], 1);
        assert_eq!(
            summary["traces"][0]["html_path"],
            "/project/p/traces/trace-claude"
        );
    }

    #[test]
    fn langfuse_traces_summary_infers_official_plugin_harnesses() {
        let response = json!({
            "data": [
                {
                    "id": "trace-codex-official",
                    "name": "Codex Turn",
                    "timestamp": "2026-07-08T19:00:00.000Z",
                    "environment": "local-macbook",
                    "sessionId": "codex-session",
                    "observations": ["agent", "generation", "tool"],
                    "totalCost": 0.17
                },
                {
                    "id": "trace-claude-official",
                    "name": "Claude Code - Turn 1 (abcd1234)",
                    "timestamp": "2026-07-08T18:59:00.000Z",
                    "environment": "local-macbook",
                    "sessionId": "claude-session",
                    "observations": ["span", "generation", "tool"],
                    "totalCost": 0.11
                }
            ],
            "meta": {"totalItems": 2}
        });
        let request = LangFuseTracesListRequest {
            endpoint: "https://langfuse.example.com/api/public/traces?limit=20&page=1".to_string(),
            limit: 20,
            page: 1,
            harness: Some("codex".to_string()),
            provider: None,
            model: None,
            environment: Some("local-macbook".to_string()),
        };

        let summary = summarize_langfuse_traces_response(&response, &request);

        assert_eq!(summary["returned_count"], 1);
        assert_eq!(summary["harnesses"], json!(["codex"]));
        assert_eq!(summary["providers"], json!(["openai"]));
        assert_eq!(summary["traces"][0]["trace_id"], "trace-codex-official");
        assert_eq!(summary["traces"][0]["run_id"], "codex-session");
        assert_eq!(summary["traces"][0]["session_id"], "codex-session");
        assert_eq!(summary["traces"][0]["observation_count"], 3);
    }

    #[test]
    fn langfuse_trace_summary_extracts_learning_loop_fields() {
        let response = json!({
            "id": "trace-1",
            "name": "agentic_primitives.run",
            "sessionId": "run-1",
            "environment": "local-test",
            "observations": [
                {
                    "name": "token_usage",
                    "type": "GENERATION",
                    "environment": "local-test",
                    "model": "gpt-4o-mini",
                    "modelId": "model-row-id",
                    "promptTokens": 10,
                    "completionTokens": 3,
                    "totalTokens": 13,
                    "usage": {"input": 10, "output": 3, "total": 13, "cached_prompt_tokens": 4},
                    "costDetails": {"input": 0.000002, "output": 0.0000013, "total": 0.0000033},
                    "calculatedTotalCost": 0.0000033,
                    "totalCost": 99.0,
                    "metadata": {
                        "attributes": {
                            "agentic.event.seq": "2",
                            "agentic.harness": "codex",
                            "agentic.provider": "openai",
                            "agentic.model": "gpt-4o-mini"
                        }
                    }
                },
                {
                    "name": "aggregate_span",
                    "type": "SPAN",
                    "totalTokens": 999,
                    "calculatedTotalCost": 99.0
                },
                {
                    "name": "tool_start",
                    "id": "obs-0",
                    "startTime": "2026-07-07T23:59:59.000Z",
                    "type": "SPAN",
                    "metadata": {
                        "attributes": {
                            "agentic.event.type": "tool_start",
                            "agentic.event.seq": "0",
                            "agentic.tool.name": "provision"
                        }
                    }
                },
                {
                    "name": "tool_end",
                    "id": "obs-1",
                    "startTime": "2026-07-07T23:59:59.000Z",
                    "type": "SPAN",
                    "metadata": {
                        "attributes": {
                            "agentic.event.type": "tool_end",
                            "agentic.event.seq": "1",
                            "agentic.tool.name": "provision",
                            "agentic.tool.success": "true"
                        }
                    }
                },
                {
                    "name": "tool_start",
                    "id": "obs-3",
                    "startTime": "2026-07-08T00:00:00.000Z",
                    "type": "SPAN",
                    "metadata": {
                        "attributes": {
                            "agentic.event.type": "tool_start",
                            "agentic.event.seq": "3",
                            "agentic.tool.name": "Bash",
                            "agentic.tool.input_redacted": "true"
                        }
                    }
                },
                {
                    "name": "tool_end",
                    "id": "obs-5",
                    "startTime": "2026-07-08T00:00:00.000Z",
                    "type": "SPAN",
                    "metadata": {
                        "attributes": {
                            "agentic.event.type": "tool_end",
                            "agentic.event.seq": "5",
                            "agentic.tool.name": "TodoWrite",
                            "agentic.tool.success": "false"
                        }
                    }
                },
                {
                    "name": "tool_end",
                    "id": "obs-4",
                    "startTime": "2026-07-08T00:00:00.000Z",
                    "type": "SPAN",
                    "metadata": {
                        "attributes": {
                            "agentic.event.type": "tool_end",
                            "agentic.event.seq": 4,
                            "agentic.tool.name": "Bash",
                            "agentic.tool.success": "true"
                        }
                    }
                }
            ]
        });

        let summary = summarize_langfuse_trace_response(&response);

        assert_eq!(summary["trace_id"], "trace-1");
        assert_eq!(summary["observation_count"], 7);
        assert_eq!(summary["harnesses"], json!(["codex"]));
        assert_eq!(summary["providers"], json!(["openai"]));
        assert_eq!(summary["models"], json!(["gpt-4o-mini"]));
        assert_eq!(summary["model_ids"], json!(["model-row-id"]));
        assert_eq!(summary["usage"]["input_tokens"], 10);
        assert_eq!(summary["usage"]["output_tokens"], 3);
        assert_eq!(summary["usage"]["total_tokens"], 13);
        assert_eq!(summary["cost"]["calculated_total_usd"], 0.0000033);
        assert_eq!(summary["generations"]["count"], 1);
        assert_eq!(summary["generations"]["input_tokens"], 10);
        assert_eq!(summary["generations"]["output_tokens"], 3);
        assert_eq!(summary["generations"]["total_tokens"], 13);
        assert_eq!(
            summary["generations"]["calculated_total_usd"],
            json!(0.0000033)
        );
        assert_eq!(
            summary["generations"]["by_model"],
            json!([
                {
                    "model": "gpt-4o-mini",
                    "model_ids": ["model-row-id"],
                    "providers": ["openai"],
                    "harnesses": ["codex"],
                    "count": 1,
                    "input_tokens": 10,
                    "output_tokens": 3,
                    "total_tokens": 13,
                    "calculated_total_usd": 0.0000033
                }
            ])
        );
        assert_eq!(
            summary["generations"]["sequence_source"],
            "agentic.event.seq"
        );
        assert_eq!(summary["generations"]["sequence"][0]["seq"], 2);
        assert_eq!(
            summary["generations"]["sequence"][0]["observation_id"],
            json!(null)
        );
        assert_eq!(
            summary["generations"]["sequence"][0]["model"],
            "gpt-4o-mini"
        );
        assert_eq!(
            summary["generations"]["sequence"][0]["cached_input_tokens"],
            4
        );
        assert_eq!(
            summary["generations"]["sequence"][0]["calculated_input_cost_usd"],
            0.000002
        );
        assert_eq!(
            summary["generations"]["sequence"][0]["calculated_output_cost_usd"],
            0.0000013
        );
        assert_eq!(
            summary["generations"]["sequence"][0]["calculated_total_cost_usd"],
            0.0000033
        );
        assert_eq!(summary["generations"]["sequence_truncated"], false);
        assert_eq!(summary["events"]["sequence_source"], "agentic.event.seq");
        assert_eq!(summary["events"]["sequence"][0]["seq"], 0);
        assert_eq!(summary["events"]["sequence"][0]["category"], "operation");
        assert_eq!(summary["events"]["sequence"][2]["event"], "token_usage");
        assert_eq!(summary["events"]["sequence"][2]["category"], "usage");
        assert_eq!(summary["events"]["sequence"][2]["total_tokens"], json!(13));
        assert_eq!(
            summary["events"]["sequence"][2]["calculated_total_cost"],
            json!(0.0000033)
        );
        assert_eq!(summary["events"]["sequence"][3]["seq"], 3);
        assert_eq!(summary["events"]["sequence"][3]["category"], "agent_tool");
        assert_eq!(
            summary["events"]["category_counts"],
            json!([
                {"category": "agent_tool", "count": 3},
                {"category": "operation", "count": 2},
                {"category": "other", "count": 1},
                {"category": "usage", "count": 1}
            ])
        );
        assert_eq!(summary["events"]["sequence_truncated"], false);
        assert_eq!(summary["tools"]["start_count"], 2);
        assert_eq!(summary["tools"]["end_count"], 3);
        assert_eq!(summary["tools"]["success_count"], 2);
        assert_eq!(summary["tools"]["failure_count"], 1);
        assert_eq!(
            summary["tools"]["names"],
            json!(["Bash", "TodoWrite", "provision"])
        );
        assert_eq!(
            summary["tools"]["by_name"],
            json!([
                {"name": "Bash", "starts": 1, "ends": 1, "successes": 1, "failures": 0},
                {"name": "TodoWrite", "starts": 0, "ends": 1, "successes": 0, "failures": 1},
                {"name": "provision", "starts": 1, "ends": 1, "successes": 1, "failures": 0}
            ])
        );
        assert_eq!(summary["tools"]["sequence_source"], "agentic.event.seq");
        assert_eq!(summary["tools"]["sequence"][0]["seq"], 0);
        assert_eq!(summary["tools"]["sequence"][2]["seq"], 3);
        assert_eq!(summary["tools"]["sequence"][3]["seq"], 4);
        assert_eq!(summary["tools"]["sequence"][4]["seq"], 5);
        assert_eq!(summary["tools"]["sequence"][2]["tool_name"], "Bash");
        assert_eq!(summary["tools"]["sequence"][3]["success"], true);
        assert_eq!(summary["tools"]["sequence"][4]["success"], false);
        assert_eq!(summary["tools"]["sequence_truncated"], false);
        assert_eq!(summary["operations"]["names"], json!(["provision"]));
        assert_eq!(summary["operations"]["start_count"], 1);
        assert_eq!(summary["operations"]["end_count"], 1);
        assert_eq!(summary["operations"]["success_count"], 1);
        assert_eq!(
            summary["agent_tools"]["names"],
            json!(["Bash", "TodoWrite"])
        );
        assert_eq!(summary["agent_tools"]["start_count"], 1);
        assert_eq!(summary["agent_tools"]["end_count"], 2);
        assert_eq!(summary["agent_tools"]["success_count"], 1);
        assert_eq!(summary["agent_tools"]["failure_count"], 1);
        assert_eq!(summary["harness_tools"]["names"], json!([]));
    }

    #[test]
    fn langfuse_trace_summary_counts_official_plugin_tool_observations() {
        let response = json!({
            "id": "trace-official-tools",
            "name": "Claude Code - Turn 1 (abcd1234)",
            "sessionId": "session-1",
            "environment": "local-test",
            "observations": [
                {
                    "name": "Tool: Read",
                    "id": "claude-tool",
                    "startTime": "2026-07-08T19:10:20.000Z",
                    "type": "TOOL",
                    "level": "DEFAULT",
                    "input": {"file_path": "README.md"},
                    "output": "contents"
                },
                {
                    "name": "exec_command",
                    "id": "codex-tool",
                    "startTime": "2026-07-08T19:10:21.000Z",
                    "type": "TOOL",
                    "input": {"cmd": "pwd"},
                    "output": {"exit_code": 0}
                },
                {
                    "name": "LLM Call 1",
                    "id": "generation",
                    "startTime": "2026-07-08T19:10:22.000Z",
                    "type": "GENERATION",
                    "model": "claude-sonnet-5",
                    "promptTokens": 10,
                    "completionTokens": 3,
                    "totalTokens": 13,
                    "calculatedTotalCost": 0.001
                }
            ]
        });

        let summary = summarize_langfuse_trace_response(&response);

        assert_eq!(summary["observation_types"], json!(["GENERATION", "TOOL"]));
        assert_eq!(summary["harnesses"], json!(["claude"]));
        assert_eq!(summary["providers"], json!(["anthropic"]));
        assert_eq!(
            summary["events"]["category_counts"],
            json!([
                {"category": "agent_tool", "count": 2},
                {"category": "other", "count": 1}
            ])
        );
        assert_eq!(summary["events"]["sequence"][0]["event"], "tool");
        assert_eq!(summary["events"]["sequence"][0]["category"], "agent_tool");
        assert_eq!(summary["events"]["sequence"][0]["tool_name"], "Read");
        assert_eq!(
            summary["events"]["sequence"][1]["tool_name"],
            "exec_command"
        );
        assert_eq!(summary["tools"]["names"], json!(["Read", "exec_command"]));
        assert_eq!(summary["tools"]["start_count"], 0);
        assert_eq!(summary["tools"]["end_count"], 2);
        assert_eq!(summary["tools"]["success_count"], 2);
        assert_eq!(summary["tools"]["failure_count"], 0);
        assert_eq!(
            summary["agent_tools"]["names"],
            json!(["Read", "exec_command"])
        );
        assert_eq!(summary["agent_tools"]["start_count"], 0);
        assert_eq!(summary["agent_tools"]["end_count"], 2);
        assert_eq!(summary["agent_tools"]["success_count"], 2);
        assert_eq!(summary["agent_tools"]["failure_count"], 0);
    }

    #[test]
    fn non_empty_env_rejects_blank_values() {
        std::env::set_var("ITMUX_TEST_BLANK_ENV", "  ");
        std::env::set_var("ITMUX_TEST_VALUE_ENV", " value ");

        assert_eq!(non_empty_env("ITMUX_TEST_BLANK_ENV"), None);
        assert_eq!(
            non_empty_env("ITMUX_TEST_VALUE_ENV").as_deref(),
            Some("value")
        );
        assert_eq!(non_empty_env("ITMUX_TEST_MISSING_ENV"), None);

        std::env::remove_var("ITMUX_TEST_BLANK_ENV");
        std::env::remove_var("ITMUX_TEST_VALUE_ENV");
    }
}
