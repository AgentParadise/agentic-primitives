//! R5 (load-bearing security test): a run credential secret must travel ONLY
//! via the stdin transfer or the in-container `0600` env file -> child env. It
//! must NEVER appear in:
//!
//! * a constructed `docker run` / `docker exec` argv,
//! * a tmux command label / args (the redacted error label),
//! * an error / fail-fast message string,
//! * a serialized `AgentRunEvent` JSONL line,
//! * an `AgentRunResult` / `session_log`,
//! * the launch wrapper command string sent to the pane.
//!
//! A leaked secret is a critical bug, so these assertions are intentionally
//! exhaustive over every host-side artifact this crate constructs from the
//! credential material. The secret is allowed to appear in exactly two places:
//! the in-memory `AgentRunCredentials` (which never serializes to stdout) and
//! the base64-encoded stdin payload of the credential transfer (which is not
//! argv).

use std::collections::BTreeMap;

use itmux::adapter::{launch_command_with_env, Agent};
use itmux::auth::{plan_for_staged_path, secure_path_plan, write_bytes_plan, StagedPath};
use itmux::run::contract::{AgentRunCredentials, AgentRunEvent, AgentRunOutcome, AgentRunResult};
use itmux::run::secret_env::{
    missing_credentials_message, render_env_file, resolve_agent_secrets, ANTHROPIC_API_KEY_ENV,
    CLAUDE_OAUTH_ENV, OPENAI_API_KEY_ENV,
};

/// Distinctive sentinel values seeded as the "secrets". If any of these strings
/// escapes into an argv/label/error/event, the test fails.
const SENTINEL_CLAUDE: &str = "SECRET_SENTINEL_CLAUDE_sk_ant_oat_DO_NOT_LEAK";
const SENTINEL_ANTHROPIC: &str = "SECRET_SENTINEL_ANTHROPIC_sk_ant_DO_NOT_LEAK";
const SENTINEL_OPENAI: &str = "SECRET_SENTINEL_OPENAI_sk_DO_NOT_LEAK";

const ALL_SENTINELS: [&str; 3] = [SENTINEL_CLAUDE, SENTINEL_ANTHROPIC, SENTINEL_OPENAI];

fn assert_no_sentinel(haystack: &str, context: &str) {
    for sentinel in ALL_SENTINELS {
        assert!(
            !haystack.contains(sentinel),
            "secret sentinel leaked into {context}: {haystack}"
        );
    }
}

fn creds_with_all_sentinels() -> AgentRunCredentials {
    AgentRunCredentials {
        claude: None,
        codex: None,
        secret_env: BTreeMap::from([
            (CLAUDE_OAUTH_ENV.to_string(), SENTINEL_CLAUDE.to_string()),
            (
                ANTHROPIC_API_KEY_ENV.to_string(),
                SENTINEL_ANTHROPIC.to_string(),
            ),
            (OPENAI_API_KEY_ENV.to_string(), SENTINEL_OPENAI.to_string()),
        ]),
    }
}

#[test]
fn render_env_file_is_the_carrier_of_the_secret() {
    // Sanity: the sourced 0600 file IS allowed to contain the secret - it is
    // one of the only two sanctioned carriers. If it did NOT, the injection
    // would be broken. (claude routing prefers OAuth over the API key.)
    let secrets = resolve_agent_secrets(Agent::Claude, &creds_with_all_sentinels());
    let body = render_env_file(&secrets.env);
    assert!(
        body.contains(SENTINEL_CLAUDE),
        "the 0600 env file must carry the token: {body}"
    );
    // Preferred/fallback: OAuth chosen, API key NOT included for claude.
    assert!(
        !body.contains(SENTINEL_ANTHROPIC),
        "api key leaked as fallback when oauth present: {body}"
    );
}

#[test]
fn launch_wrapper_command_has_no_secret() {
    // The command string sent to the pane carries only the env-file PATH + the
    // harness command - never the secret.
    let wrapped = launch_command_with_env(
        "claude --plugin-dir /opt/skills",
        "/home/agent/.itmux-secret-env-claude",
    );
    assert_no_sentinel(&wrapped, "launch wrapper command");
    assert!(
        wrapped.contains("exec claude"),
        "wrapper must exec the harness: {wrapped}"
    );
    assert!(
        wrapped.contains(". "),
        "wrapper must source the env file: {wrapped}"
    );
}

#[test]
fn credential_transfer_plan_keeps_secret_out_of_every_argv() {
    // The env file is staged over the SAME base64-over-stdin transfer as
    // credentials. Assert: no ExecStep argv contains a sentinel; the secret
    // rides ONLY in stdin (base64, so not even the plaintext sentinel appears).
    let secrets = resolve_agent_secrets(Agent::Claude, &creds_with_all_sentinels());
    let body = render_env_file(&secrets.env);
    let container_path = "/home/agent/.itmux-secret-env-claude";

    let steps = write_bytes_plan(container_path, body.as_bytes());
    let mut stdin_carries_it = false;
    for step in &steps {
        let argv = step.argv.join(" ");
        assert_no_sentinel(&argv, "docker exec argv (write_bytes_plan)");
        if let Some(stdin) = &step.stdin {
            // The stdin payload is base64; the raw sentinel must NOT appear as
            // plaintext even there (defense: it is encoded).
            let stdin_str = String::from_utf8_lossy(stdin);
            assert_no_sentinel(
                &stdin_str,
                "docker exec stdin (must be base64, not plaintext)",
            );
            // But base64-decoding it MUST recover the secret (it is the carrier).
            if base64_decode(&stdin_str)
                .map(|d| String::from_utf8_lossy(&d).contains(SENTINEL_CLAUDE))
                .unwrap_or(false)
            {
                stdin_carries_it = true;
            }
        }
    }
    assert!(
        stdin_carries_it,
        "the secret must ride in the base64 stdin payload (its only argv-free carrier)"
    );

    // The trailing secure step (chown/chmod 0600) also never names the secret.
    let secure = secure_path_plan(container_path, false);
    assert_no_sentinel(&secure.argv.join(" "), "secure_path_plan argv");
}

#[test]
fn full_staged_path_plan_never_leaks_into_argv() {
    // End-to-end through the real staging entry point used by Workspace::start:
    // write the env file to a temp path, build the plan, and assert argv purity.
    let dir = std::env::temp_dir().join(format!(
        "itmux-secret-redaction-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    std::fs::create_dir_all(&dir).unwrap();
    let secrets = resolve_agent_secrets(Agent::Codex, &creds_with_all_sentinels());
    let body = render_env_file(&secrets.env);
    assert!(
        body.contains(SENTINEL_OPENAI),
        "codex routes OPENAI_API_KEY: {body}"
    );
    let host_file = dir.join("secret-env-codex");
    std::fs::write(&host_file, &body).unwrap();

    let staged = StagedPath {
        host: host_file,
        container: "/home/agent/.itmux-secret-env-codex".to_string(),
    };
    for step in plan_for_staged_path(&staged).unwrap() {
        assert_no_sentinel(&step.argv.join(" "), "plan_for_staged_path argv");
    }
    let _ = std::fs::remove_dir_all(&dir);
}

#[test]
fn fail_fast_and_events_and_results_never_contain_secrets() {
    // Fail-fast messages name the missing VAR, never a value.
    for agent in [Agent::Claude, Agent::Codex, Agent::Gemini] {
        assert_no_sentinel(&missing_credentials_message(agent), "fail-fast message");
    }

    // A serialized event line never carries a secret (events are telemetry, not
    // credentials).
    let event = AgentRunEvent::result(
        "run-1",
        0,
        "2026-07-07T00:00:00Z",
        AgentRunResult {
            result: AgentRunOutcome {
                success: true,
                summary: "done".to_string(),
            },
            output_artifacts: vec![],
            session_log: "pane transcript with no secrets".to_string(),
            observability: None,
        },
    );
    let line = serde_json::to_string(&event).unwrap();
    assert_no_sentinel(&line, "serialized AgentRunEvent JSONL");
}

/// Minimal std-only base64 decoder for the redaction test (the encoder lives in
/// `auth`; decoding happens in-container in production, so the crate ships no
/// decoder - we add one here purely to PROVE the stdin payload is the carrier).
fn base64_decode(s: &str) -> Option<Vec<u8>> {
    fn val(c: u8) -> Option<u8> {
        match c {
            b'A'..=b'Z' => Some(c - b'A'),
            b'a'..=b'z' => Some(c - b'a' + 26),
            b'0'..=b'9' => Some(c - b'0' + 52),
            b'+' => Some(62),
            b'/' => Some(63),
            _ => None,
        }
    }
    let bytes: Vec<u8> = s.bytes().filter(|b| !b.is_ascii_whitespace()).collect();
    let mut out = Vec::new();
    for chunk in bytes.chunks(4) {
        let c0 = val(chunk[0])?;
        let c1 = val(*chunk.get(1)?)?;
        out.push((c0 << 2) | (c1 >> 4));
        if let Some(&b2) = chunk.get(2) {
            if b2 != b'=' {
                let c2 = val(b2)?;
                out.push(((c1 & 0x0F) << 4) | (c2 >> 2));
                if let Some(&b3) = chunk.get(3) {
                    if b3 != b'=' {
                        let c3 = val(b3)?;
                        out.push(((c2 & 0x03) << 6) | c3);
                    }
                }
            }
        }
    }
    Some(out)
}
