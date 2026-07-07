//! Harness-specific observers that normalize raw harness streams into
//! `AgentRunEventPayload` values.
//!
//! Exporters stay backend-agnostic: observers know how to read Claude, Codex,
//! or future harness surfaces; fanout exporters only receive normalized run
//! events.

use std::error::Error;
use std::fmt;

use serde::Deserialize;

use crate::run::contract::AgentRunEventPayload;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum HarnessEventSource {
    CodexExecJson,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ObservedAgentEvent {
    pub source: HarnessEventSource,
    pub payload: AgentRunEventPayload,
}

pub trait HarnessObserver {
    fn observe_jsonl_line(&mut self, line: &str) -> Result<Vec<ObservedAgentEvent>, ObserverError>;
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ObserverError {
    message: String,
}

impl ObserverError {
    fn invalid_json(source: serde_json::Error) -> Self {
        Self {
            message: format!("invalid harness json: {source}"),
        }
    }
}

impl fmt::Display for ObserverError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.message)
    }
}

impl Error for ObserverError {}

#[derive(Debug, Default)]
pub struct CodexExecJsonObserver {
    turn_open: bool,
}

impl CodexExecJsonObserver {
    pub fn new() -> Self {
        Self::default()
    }

    fn event(payload: AgentRunEventPayload) -> ObservedAgentEvent {
        ObservedAgentEvent {
            source: HarnessEventSource::CodexExecJson,
            payload,
        }
    }
}

impl HarnessObserver for CodexExecJsonObserver {
    fn observe_jsonl_line(&mut self, line: &str) -> Result<Vec<ObservedAgentEvent>, ObserverError> {
        if line.trim().is_empty() {
            return Ok(Vec::new());
        }

        let event: CodexExecJsonEvent =
            serde_json::from_str(line).map_err(ObserverError::invalid_json)?;
        let mut out = Vec::new();

        match event {
            CodexExecJsonEvent::ThreadStarted { thread_id } => {
                out.push(Self::event(AgentRunEventPayload::ToolStart {
                    tool_name: "codex_exec.thread".to_string(),
                    tool_input: serde_json::json!({ "thread_id": thread_id }),
                }));
            }
            CodexExecJsonEvent::TurnStarted => {
                self.turn_open = true;
                out.push(Self::event(AgentRunEventPayload::ToolStart {
                    tool_name: "codex_exec.turn".to_string(),
                    tool_input: serde_json::Value::Null,
                }));
            }
            CodexExecJsonEvent::ItemCompleted { item } => {
                out.push(Self::event(AgentRunEventPayload::ToolEnd {
                    tool_name: format!("codex_exec.item.{}", item.item_type),
                    success: item.item_type != "error",
                    output_summary: item.summary(),
                }));
            }
            CodexExecJsonEvent::TurnCompleted { usage } => {
                if self.turn_open {
                    out.push(Self::event(AgentRunEventPayload::ToolEnd {
                        tool_name: "codex_exec.turn".to_string(),
                        success: true,
                        output_summary: Some("turn completed".to_string()),
                    }));
                    self.turn_open = false;
                }
                out.push(Self::event(AgentRunEventPayload::TokenUsage {
                    input_tokens: usage.input_tokens,
                    output_tokens: usage.output_tokens,
                    cached_input_tokens: usage.cached_input_tokens,
                    reasoning_output_tokens: usage.reasoning_output_tokens,
                    cost_usd: None,
                }));
            }
            CodexExecJsonEvent::TurnFailed { error } => {
                out.push(Self::event(AgentRunEventPayload::ToolEnd {
                    tool_name: "codex_exec.turn".to_string(),
                    success: false,
                    output_summary: Some(error.message),
                }));
                self.turn_open = false;
            }
            CodexExecJsonEvent::Error { message } => {
                out.push(Self::event(AgentRunEventPayload::ToolEnd {
                    tool_name: "codex_exec.error".to_string(),
                    success: false,
                    output_summary: Some(message),
                }));
            }
            CodexExecJsonEvent::Other => {}
        }

        Ok(out)
    }
}

#[derive(Debug, Deserialize)]
#[serde(tag = "type")]
enum CodexExecJsonEvent {
    #[serde(rename = "thread.started")]
    ThreadStarted { thread_id: String },
    #[serde(rename = "turn.started")]
    TurnStarted,
    #[serde(rename = "item.completed")]
    ItemCompleted { item: CodexItem },
    #[serde(rename = "turn.completed")]
    TurnCompleted { usage: CodexUsage },
    #[serde(rename = "turn.failed")]
    TurnFailed { error: CodexError },
    #[serde(rename = "error")]
    Error { message: String },
    #[serde(other)]
    Other,
}

#[derive(Debug, Deserialize)]
struct CodexItem {
    #[serde(rename = "type")]
    item_type: String,
    #[serde(default)]
    text: Option<String>,
    #[serde(default)]
    message: Option<String>,
}

impl CodexItem {
    fn summary(self) -> Option<String> {
        self.text.or(self.message).map(trim_summary)
    }
}

#[derive(Debug, Deserialize)]
struct CodexUsage {
    input_tokens: u64,
    output_tokens: u64,
    #[serde(default)]
    cached_input_tokens: Option<u64>,
    #[serde(default)]
    reasoning_output_tokens: Option<u64>,
}

#[derive(Debug, Deserialize)]
struct CodexError {
    message: String,
}

fn trim_summary(text: String) -> String {
    const MAX_CHARS: usize = 240;
    let mut iter = text.chars();
    let summary: String = iter.by_ref().take(MAX_CHARS).collect();
    if iter.next().is_some() {
        format!("{summary}...")
    } else {
        summary
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn codex_exec_json_maps_successful_turn_usage() {
        let lines = [
            r#"{"type":"thread.started","thread_id":"019f3dba-df0e-7282-8614-7ded2fd6dae7"}"#,
            r#"{"type":"turn.started"}"#,
            r#"{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"CODEX_EXEC_OBSERVABILITY_OK"}}"#,
            r#"{"type":"turn.completed","usage":{"input_tokens":15919,"cached_input_tokens":9600,"output_tokens":11,"reasoning_output_tokens":0}}"#,
        ];
        let mut observer = CodexExecJsonObserver::new();

        let events: Vec<_> = lines
            .iter()
            .flat_map(|line| observer.observe_jsonl_line(line).expect("parse line"))
            .collect();

        assert!(matches!(
            events[0].payload,
            AgentRunEventPayload::ToolStart { ref tool_name, .. }
                if tool_name == "codex_exec.thread"
        ));
        assert!(matches!(
            events[1].payload,
            AgentRunEventPayload::ToolStart { ref tool_name, .. }
                if tool_name == "codex_exec.turn"
        ));
        assert!(matches!(
            events[2].payload,
            AgentRunEventPayload::ToolEnd { ref tool_name, success: true, .. }
                if tool_name == "codex_exec.item.agent_message"
        ));
        assert!(matches!(
            events[3].payload,
            AgentRunEventPayload::ToolEnd { ref tool_name, success: true, .. }
                if tool_name == "codex_exec.turn"
        ));
        match &events[4].payload {
            AgentRunEventPayload::TokenUsage {
                input_tokens,
                output_tokens,
                cached_input_tokens,
                reasoning_output_tokens,
                cost_usd,
            } => {
                assert_eq!(*input_tokens, 15919);
                assert_eq!(*output_tokens, 11);
                assert_eq!(*cached_input_tokens, Some(9600));
                assert_eq!(*reasoning_output_tokens, Some(0));
                assert_eq!(*cost_usd, None);
            }
            other => panic!("expected token usage, got {other:?}"),
        }
    }

    #[test]
    fn codex_exec_json_maps_failed_turn() {
        let mut observer = CodexExecJsonObserver::new();
        let events = observer
            .observe_jsonl_line(
                r#"{"type":"turn.failed","error":{"message":"model is not supported"}}"#,
            )
            .expect("parse failure line");

        assert_eq!(events.len(), 1);
        assert!(matches!(
            events[0].payload,
            AgentRunEventPayload::ToolEnd {
                ref tool_name,
                success: false,
                ref output_summary
            } if tool_name == "codex_exec.turn"
                && output_summary.as_deref() == Some("model is not supported")
        ));
    }
}
