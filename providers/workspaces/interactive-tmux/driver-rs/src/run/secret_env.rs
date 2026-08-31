//! `.env` / process-env credential loading for `itmux run`, plus the
//! per-harness routing that decides which secret env vars reach which pane.
//!
//! # Why this exists (the stale-file 401)
//!
//! Before this module, `itmux run` built its run spec with empty
//! `credentials`, so the executor always fell back to the host `$HOME/.claude`
//! file. On macOS that `.credentials.json` expires within hours (the live
//! token lives in the Keychain), so `itmux run` recurringly 401'd. This loader
//! populates `AgentRunCredentials` from a `.env` file / process env so a fresh,
//! long-lived credential (a `claude setup-token` OAuth token, or an API key) is
//! injected instead.
//!
//! # Security model (R1/R5)
//!
//! The loaded secret VALUES flow only into `AgentRunCredentials` in memory and,
//! from there, into a `0600` env file the harness pane `source`s at launch (via
//! the base64-over-stdin `docker exec` transfer). They NEVER reach a `docker
//! run`/`docker exec` argv or a `tmux` command line. The only artifacts that
//! ever contain a raw secret are this in-memory struct, the base64 stdin
//! payload, and the in-container `0600` file. See `tests/secret_redaction.rs`.

use std::collections::BTreeMap;
use std::fmt;
use std::io;
use std::path::{Path, PathBuf};

use crate::adapter::Agent;
use crate::run::contract::{AgentRunCredentials, CodexCredentials};

/// Preferred Claude credential env var: a long-lived OAuth token from
/// `claude setup-token`, consumed by Claude Code as an env var (NOT a
/// synthesized `.credentials.json`).
pub const CLAUDE_OAUTH_ENV: &str = "CLAUDE_CODE_OAUTH_TOKEN";
/// Fallback Claude credential env var: a raw Anthropic API key.
pub const ANTHROPIC_API_KEY_ENV: &str = "ANTHROPIC_API_KEY";
/// Fallback Codex credential env var: a raw OpenAI API key.
pub const OPENAI_API_KEY_ENV: &str = "OPENAI_API_KEY";
/// Path (NOT a secret value) pointing at a Codex `auth.json`. Its CONTENTS are
/// read and staged as a file; the path itself is not injected as an env var.
pub const CODEX_AUTH_FILE_ENV: &str = "CODEX_AUTH_FILE";

/// The ONLY env-var names the loader will ever read as secret values (R2). A
/// strict allowlist so an unrelated env var (or a typo) can never be swept into
/// the container.
pub const ALLOWED_SECRET_ENV: [&str; 3] =
    [CLAUDE_OAUTH_ENV, ANTHROPIC_API_KEY_ENV, OPENAI_API_KEY_ENV];

// ---------------------------------------------------------------------------
// `.env` parser (R4): KEY=VALUE, `#` comments, single/double quotes, blanks.
// No variable expansion, no multiline, no `export`. Unsupported syntax is
// rejected with filename + line number.

/// A `.env` parse failure carrying the file and 1-based line number (R4). The
/// message NEVER contains a secret value - only structural context.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EnvParseError {
    pub file: String,
    pub line: usize,
    pub message: String,
}

impl fmt::Display for EnvParseError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}:{}: {}", self.file, self.line, self.message)
    }
}

impl std::error::Error for EnvParseError {}

fn parse_err(file: &str, line: usize, message: impl Into<String>) -> EnvParseError {
    EnvParseError {
        file: file.to_string(),
        line,
        message: message.into(),
    }
}

/// A valid shell/env variable name: `[A-Za-z_][A-Za-z0-9_]*`.
fn is_valid_key(key: &str) -> bool {
    let mut chars = key.chars();
    match chars.next() {
        Some(c) if c.is_ascii_alphabetic() || c == '_' => {}
        _ => return false,
    }
    chars.all(|c| c.is_ascii_alphanumeric() || c == '_')
}

/// Parse a single `VALUE` token. Single/double quoted values are taken
/// literally (NO expansion, NO escape processing besides quote stripping);
/// unquoted values are used verbatim. A value that opens a quote but does not
/// close it on the same line is rejected (no multiline support, R4).
fn parse_value(raw: &str) -> Result<String, String> {
    let bytes = raw.as_bytes();
    if let Some(&first) = bytes.first() {
        if first == b'"' || first == b'\'' {
            if raw.len() >= 2 && bytes[raw.len() - 1] == first {
                return Ok(raw[1..raw.len() - 1].to_string());
            }
            let kind = if first == b'"' { "double" } else { "single" };
            return Err(format!(
                "unterminated {kind} quote (multiline values are not supported)"
            ));
        }
    }
    Ok(raw.to_string())
}

/// Parse `.env` file `contents` (R4). `filename` is used only for error
/// context. Later duplicate keys overwrite earlier ones.
pub fn parse_env_file(
    contents: &str,
    filename: &str,
) -> Result<BTreeMap<String, String>, EnvParseError> {
    let mut out = BTreeMap::new();
    for (idx, raw_line) in contents.lines().enumerate() {
        let line_no = idx + 1;
        // `lines()` strips `\n`; strip a trailing `\r` for CRLF files too.
        let line = raw_line.strip_suffix('\r').unwrap_or(raw_line);
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }
        if trimmed == "export" || trimmed.starts_with("export ") || trimmed.starts_with("export\t")
        {
            return Err(parse_err(
                filename,
                line_no,
                "`export` syntax is not supported; use a bare KEY=VALUE line",
            ));
        }
        let Some(eq) = trimmed.find('=') else {
            return Err(parse_err(
                filename,
                line_no,
                "expected KEY=VALUE (no '=' found)",
            ));
        };
        let key = trimmed[..eq].trim();
        let value_raw = trimmed[eq + 1..].trim();
        if !is_valid_key(key) {
            return Err(parse_err(
                filename,
                line_no,
                format!("invalid variable name '{key}'; expected [A-Za-z_][A-Za-z0-9_]*"),
            ));
        }
        let value = parse_value(value_raw).map_err(|m| parse_err(filename, line_no, m))?;
        out.insert(key.to_string(), value);
    }
    Ok(out)
}

// ---------------------------------------------------------------------------
// Credential loading (source precedence: --env-file > process env).

/// Failure loading credentials. Messages NEVER contain a secret value.
#[derive(Debug)]
pub enum LoadCredentialsError {
    /// The `--env-file` path could not be read.
    EnvFileRead { path: String, source: io::Error },
    /// The `.env` file parsed with a syntax error (R4).
    Parse(EnvParseError),
    /// `CODEX_AUTH_FILE` was set but its target could not be read.
    CodexAuthRead { path: String, source: io::Error },
}

impl fmt::Display for LoadCredentialsError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::EnvFileRead { path, source } => {
                write!(f, "failed to read --env-file '{path}': {source}")
            }
            Self::Parse(e) => write!(f, "failed to parse --env-file: {e}"),
            Self::CodexAuthRead { path, source } => {
                write!(f, "failed to read CODEX_AUTH_FILE '{path}': {source}")
            }
        }
    }
}

impl std::error::Error for LoadCredentialsError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::EnvFileRead { source, .. } | Self::CodexAuthRead { source, .. } => Some(source),
            Self::Parse(e) => Some(e),
        }
    }
}

/// Expand a leading `~/` (or bare `~`) against `$HOME`. Only the leading tilde
/// is expanded - this is a path convenience, NOT `.env` variable expansion.
fn expand_tilde(path: &str) -> PathBuf {
    if path == "~" {
        if let Some(home) = std::env::var_os("HOME") {
            return PathBuf::from(home);
        }
    } else if let Some(rest) = path.strip_prefix("~/") {
        if let Some(home) = std::env::var_os("HOME") {
            return PathBuf::from(home).join(rest);
        }
    }
    PathBuf::from(path)
}

/// Load `AgentRunCredentials` from an optional `.env` file overlaid on process
/// env (precedence: `--env-file` > process env). Populates `secret_env` with
/// the ALLOWLISTED names present, and `codex.auth_json` from `CODEX_AUTH_FILE`
/// contents when that path is set. Does NOT fail on "no credentials" - the
/// per-agent fail-fast (R3) lives in the executor, which knows which harness
/// the recipe runs. Fails only on unreadable / malformed inputs.
pub fn load_credentials(
    env_file: Option<&Path>,
) -> Result<AgentRunCredentials, LoadCredentialsError> {
    let mut env_file_map = BTreeMap::new();
    if let Some(path) = env_file {
        let contents =
            std::fs::read_to_string(path).map_err(|e| LoadCredentialsError::EnvFileRead {
                path: path.display().to_string(),
                source: e,
            })?;
        env_file_map = parse_env_file(&contents, &path.display().to_string())
            .map_err(LoadCredentialsError::Parse)?;
    }
    resolve_credentials(&env_file_map, &|name| std::env::var(name).ok(), &|path| {
        std::fs::read_to_string(expand_tilde(path))
    })
}

/// Pure credential resolver, factored out so unit tests can inject the process
/// env and file reads deterministically (never touching real global env).
///
/// `env_file_map` takes precedence over `get_env`. `read_file` reads a
/// `CODEX_AUTH_FILE` path's contents.
fn resolve_credentials(
    env_file_map: &BTreeMap<String, String>,
    get_env: &dyn Fn(&str) -> Option<String>,
    read_file: &dyn Fn(&str) -> io::Result<String>,
) -> Result<AgentRunCredentials, LoadCredentialsError> {
    let resolve = |name: &str| -> Option<String> {
        env_file_map
            .get(name)
            .cloned()
            .or_else(|| get_env(name))
            .filter(|v| !v.is_empty())
    };

    let mut secret_env = BTreeMap::new();
    for name in ALLOWED_SECRET_ENV {
        if let Some(value) = resolve(name) {
            secret_env.insert(name.to_string(), value);
        }
    }

    let codex = match resolve(CODEX_AUTH_FILE_ENV) {
        Some(path) => {
            let contents = read_file(&path)
                .map_err(|source| LoadCredentialsError::CodexAuthRead { path, source })?;
            Some(CodexCredentials {
                auth_json: contents,
            })
        }
        None => None,
    };

    Ok(AgentRunCredentials {
        claude: None,
        codex,
        secret_env,
    })
}

// ---------------------------------------------------------------------------
// Per-harness routing (R2): which secrets reach which pane.

/// The secrets destined for one harness pane. `env` vars are sourced from a
/// `0600` env file before the CLI launches; `codex_auth_json` (codex only) is
/// staged as a file the CLI reads.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct AgentLaunchSecrets {
    pub env: BTreeMap<String, String>,
    pub codex_auth_json: Option<String>,
}

impl AgentLaunchSecrets {
    pub fn is_empty(&self) -> bool {
        self.env.is_empty() && self.codex_auth_json.is_none()
    }
}

/// Route `creds` to the secrets for `agent` (R2), applying the confirmed
/// preferred/fallback + compat precedence (R8):
///
/// * claude: `secret_env[CLAUDE_CODE_OAUTH_TOKEN]` (preferred) ELSE the legacy
///   `claude.oauth_token` (translated to that SAME env var - no
///   `.credentials.json` synthesis, R1) ELSE `secret_env[ANTHROPIC_API_KEY]`.
/// * codex: `codex.auth_json` file contents (preferred - covers `CODEX_AUTH_FILE`
///   and the legacy field) ELSE `secret_env[OPENAI_API_KEY]`.
/// * gemini: nothing (no allowlisted secret var).
pub fn resolve_agent_secrets(agent: Agent, creds: &AgentRunCredentials) -> AgentLaunchSecrets {
    let mut out = AgentLaunchSecrets::default();
    match agent {
        Agent::Claude => {
            if let Some(token) = creds.secret_env.get(CLAUDE_OAUTH_ENV) {
                out.env.insert(CLAUDE_OAUTH_ENV.to_string(), token.clone());
            } else if let Some(claude) = &creds.claude {
                out.env
                    .insert(CLAUDE_OAUTH_ENV.to_string(), claude.oauth_token.clone());
            } else if let Some(key) = creds.secret_env.get(ANTHROPIC_API_KEY_ENV) {
                out.env
                    .insert(ANTHROPIC_API_KEY_ENV.to_string(), key.clone());
            }
        }
        Agent::Codex => {
            if let Some(codex) = &creds.codex {
                out.codex_auth_json = Some(codex.auth_json.clone());
            } else if let Some(key) = creds.secret_env.get(OPENAI_API_KEY_ENV) {
                out.env.insert(OPENAI_API_KEY_ENV.to_string(), key.clone());
            }
        }
        Agent::Gemini => {}
    }
    out
}

/// The actionable fail-fast message (R3) when a harness has NO credentials and
/// host fallback is not enabled. Names the missing var(s) and points at
/// `--env-file` / `--allow-host-auth-fallback`. Contains no secret value.
pub fn missing_credentials_message(agent: Agent) -> String {
    match agent {
        Agent::Claude => format!(
            "no Claude credentials found. Set {CLAUDE_OAUTH_ENV} (preferred; from `claude \
             setup-token`) or {ANTHROPIC_API_KEY_ENV} in your environment or an --env-file, or \
             pass --allow-host-auth-fallback to use the host $HOME/.claude file (may be stale -> \
             401)."
        ),
        Agent::Codex => format!(
            "no Codex credentials found. Set {CODEX_AUTH_FILE_ENV} (preferred; path to auth.json) \
             or {OPENAI_API_KEY_ENV} in your environment or an --env-file, or pass \
             --allow-host-auth-fallback to use the host $HOME/.codex file."
        ),
        Agent::Gemini => "no Gemini credentials configured for itmux run. Set them in your \
             environment or an --env-file, or pass --allow-host-auth-fallback to use the host \
             $HOME/.gemini file."
            .to_string(),
    }
}

// ---------------------------------------------------------------------------
// Env-file body rendering (the sourced 0600 file).

/// Shell single-quote a value (close-escape-reopen), so a secret containing any
/// character survives `. <file>` sourcing intact.
fn single_quote(s: &str) -> String {
    format!("'{}'", s.replace('\'', "'\\''"))
}

/// Render the body of the sourced `0600` env file: one `KEY='value'` line per
/// entry (deterministic order via the `BTreeMap`). The launch wrapper runs
/// `set -a; . <file>; set +a; exec <cmd>`, so `set -a` exports every KEY into
/// the harness child's environment. This body is the ONLY launch-side artifact
/// that contains raw secret values; it is written `0600` and removed on
/// teardown. NEVER log it.
pub fn render_env_file(env: &BTreeMap<String, String>) -> String {
    let mut out = String::new();
    for (key, value) in env {
        out.push_str(key);
        out.push('=');
        out.push_str(&single_quote(value));
        out.push('\n');
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_basic_key_value_comments_and_blanks() {
        let src = "\
# a comment
CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat-abc

ANTHROPIC_API_KEY=sk-ant-123   # not a comment: taken verbatim
";
        let map = parse_env_file(src, ".env").unwrap();
        assert_eq!(map.get(CLAUDE_OAUTH_ENV).unwrap(), "sk-ant-oat-abc");
        // Trailing text after the value is NOT treated as an inline comment
        // (narrow parser): the whole remainder is the value.
        assert_eq!(
            map.get(ANTHROPIC_API_KEY_ENV).unwrap(),
            "sk-ant-123   # not a comment: taken verbatim"
        );
    }

    #[test]
    fn strips_single_and_double_quotes_without_expansion() {
        let src = "A=\"sk-$NOTEXPANDED\"\nB='literal value with spaces'\n";
        let map = parse_env_file(src, ".env").unwrap();
        assert_eq!(map.get("A").unwrap(), "sk-$NOTEXPANDED");
        assert_eq!(map.get("B").unwrap(), "literal value with spaces");
    }

    #[test]
    fn rejects_export_with_file_and_line() {
        let src = "OK=1\nexport FOO=bar\n";
        let err = parse_env_file(src, "creds.env").unwrap_err();
        assert_eq!(err.file, "creds.env");
        assert_eq!(err.line, 2);
        assert!(err.to_string().contains("creds.env:2:"), "{err}");
        assert!(err.message.contains("export"), "{err}");
    }

    #[test]
    fn rejects_missing_equals_with_line_number() {
        let src = "GOOD=1\nBADLINE\n";
        let err = parse_env_file(src, ".env").unwrap_err();
        assert_eq!(err.line, 2);
        assert!(err.message.contains("KEY=VALUE"), "{err}");
    }

    #[test]
    fn rejects_unterminated_quote() {
        let src = "A='unterminated\n";
        let err = parse_env_file(src, ".env").unwrap_err();
        assert_eq!(err.line, 1);
        assert!(err.message.contains("unterminated"), "{err}");
    }

    #[test]
    fn rejects_invalid_key() {
        let err = parse_env_file("1BAD=x\n", ".env").unwrap_err();
        assert!(err.message.contains("invalid variable name"), "{err}");
    }

    #[test]
    fn env_file_present_populates_allowlisted_secret_env_only() {
        let env_file = BTreeMap::from([
            (CLAUDE_OAUTH_ENV.to_string(), "sk-ant-oat-file".to_string()),
            // A non-allowlisted name in the file is IGNORED.
            ("RANDOM_SECRET".to_string(), "nope".to_string()),
        ]);
        let creds = resolve_credentials(&env_file, &|_| None, &|_| {
            Err(io::Error::other("no codex file"))
        })
        .unwrap();
        assert_eq!(
            creds.secret_env.get(CLAUDE_OAUTH_ENV).unwrap(),
            "sk-ant-oat-file"
        );
        assert!(!creds.secret_env.contains_key("RANDOM_SECRET"));
        assert!(creds.codex.is_none());
    }

    #[test]
    fn process_env_used_when_no_env_file() {
        let creds = resolve_credentials(
            &BTreeMap::new(),
            &|name| (name == OPENAI_API_KEY_ENV).then(|| "sk-openai-proc".to_string()),
            &|_| Err(io::Error::other("unused")),
        )
        .unwrap();
        assert_eq!(
            creds.secret_env.get(OPENAI_API_KEY_ENV).unwrap(),
            "sk-openai-proc"
        );
    }

    #[test]
    fn env_file_overrides_process_env() {
        let env_file = BTreeMap::from([(CLAUDE_OAUTH_ENV.to_string(), "from-file".to_string())]);
        let creds = resolve_credentials(
            &env_file,
            &|name| (name == CLAUDE_OAUTH_ENV).then(|| "from-process".to_string()),
            &|_| Err(io::Error::other("unused")),
        )
        .unwrap();
        assert_eq!(creds.secret_env.get(CLAUDE_OAUTH_ENV).unwrap(), "from-file");
    }

    #[test]
    fn codex_auth_file_contents_read_into_auth_json() {
        let env_file = BTreeMap::from([(
            CODEX_AUTH_FILE_ENV.to_string(),
            "/path/to/auth.json".to_string(),
        )]);
        let creds = resolve_credentials(&env_file, &|_| None, &|path| {
            assert_eq!(path, "/path/to/auth.json");
            Ok(r#"{"token":"codex-abc"}"#.to_string())
        })
        .unwrap();
        assert_eq!(creds.codex.unwrap().auth_json, r#"{"token":"codex-abc"}"#);
    }

    #[test]
    fn claude_prefers_oauth_over_api_key_and_legacy_field() {
        // secret_env OAuth beats both the API key AND the legacy oauth_token.
        let creds = AgentRunCredentials {
            claude: Some(crate::run::contract::ClaudeCredentials {
                oauth_token: "legacy".to_string(),
            }),
            codex: None,
            secret_env: BTreeMap::from([
                (CLAUDE_OAUTH_ENV.to_string(), "preferred-oauth".to_string()),
                (ANTHROPIC_API_KEY_ENV.to_string(), "api-key".to_string()),
            ]),
        };
        let secrets = resolve_agent_secrets(Agent::Claude, &creds);
        assert_eq!(
            secrets.env.get(CLAUDE_OAUTH_ENV).unwrap(),
            "preferred-oauth"
        );
        assert!(!secrets.env.contains_key(ANTHROPIC_API_KEY_ENV));
    }

    #[test]
    fn claude_legacy_oauth_token_becomes_env_var_not_credentials_file() {
        // R1/R8: legacy claude.oauth_token is translated to the env var.
        let creds = AgentRunCredentials {
            claude: Some(crate::run::contract::ClaudeCredentials {
                oauth_token: "legacy-oauth".to_string(),
            }),
            codex: None,
            secret_env: BTreeMap::new(),
        };
        let secrets = resolve_agent_secrets(Agent::Claude, &creds);
        assert_eq!(secrets.env.get(CLAUDE_OAUTH_ENV).unwrap(), "legacy-oauth");
    }

    #[test]
    fn claude_falls_back_to_api_key() {
        let creds = AgentRunCredentials {
            claude: None,
            codex: None,
            secret_env: BTreeMap::from([(
                ANTHROPIC_API_KEY_ENV.to_string(),
                "sk-ant-key".to_string(),
            )]),
        };
        let secrets = resolve_agent_secrets(Agent::Claude, &creds);
        assert_eq!(
            secrets.env.get(ANTHROPIC_API_KEY_ENV).unwrap(),
            "sk-ant-key"
        );
    }

    #[test]
    fn codex_prefers_auth_json_over_openai_key() {
        let creds = AgentRunCredentials {
            claude: None,
            codex: Some(CodexCredentials {
                auth_json: "{}".to_string(),
            }),
            secret_env: BTreeMap::from([(OPENAI_API_KEY_ENV.to_string(), "sk-openai".to_string())]),
        };
        let secrets = resolve_agent_secrets(Agent::Codex, &creds);
        assert_eq!(secrets.codex_auth_json.as_deref(), Some("{}"));
        assert!(secrets.env.is_empty());
    }

    #[test]
    fn none_yields_empty_secrets_and_fail_fast_message() {
        let creds = AgentRunCredentials::default();
        assert!(resolve_agent_secrets(Agent::Claude, &creds).is_empty());
        let msg = missing_credentials_message(Agent::Claude);
        assert!(msg.contains(CLAUDE_OAUTH_ENV), "{msg}");
        assert!(msg.contains("--env-file"), "{msg}");
        assert!(msg.contains("--allow-host-auth-fallback"), "{msg}");
    }

    #[test]
    fn render_env_file_single_quotes_values() {
        let env = BTreeMap::from([(CLAUDE_OAUTH_ENV.to_string(), "sk-ant-'quote".to_string())]);
        let body = render_env_file(&env);
        assert_eq!(body, "CLAUDE_CODE_OAUTH_TOKEN='sk-ant-'\\''quote'\n");
    }
}
