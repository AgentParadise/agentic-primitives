//! Per-agent credential staging and in-container transfer.
//!
//! Each adapter copies (never moves) the relevant host directory under a
//! per-workspace throwaway dir (`/tmp/interactive-tmux-<name>-<random>/`)
//! so the container can receive fresh credential bytes without ever
//! mutating the operator's live `~/.claude`, `~/.codex`, `~/.gemini`.
//!
//! Synthesised files (claude's `~/.claude.json`, gemini's `settings.json`
//! patch) follow the Python driver's policy bit-for-bit so the two
//! implementations produce interchangeable payloads.
//!
//! # Delivery: `docker exec` transfer, not `-v` bind mounts
//!
//! Syntropic137 runs this driver INSIDE a container (docker-out-of-docker).
//! A `docker run -v host:container` bind mount is resolved by the *outer*
//! docker daemon against its own filesystem - it cannot see a staging dir
//! that only exists in this driver's own mount namespace. So instead of
//! bind-mounting, the container is started bare (`docker run ... sleep
//! infinity`, see `workspace::Workspace::start`) and credential bytes are
//! pushed into the already-running container over `docker exec` stdin:
//! files via base64, directories file-by-file (mirrors the Python driver's
//! `os.walk` transfer at PY:1540-1563 exactly, rather than a `tar` stream,
//! for byte-for-byte parity with the source of truth). See
//! `_write_bytes_to_container` / `_transfer_path_to_container` /
//! `_secure_container_path` in `driver/interactive_tmux.py` (PY:1493-1583).
//!
//! Credentials never appear in `docker exec` argv - only ever in stdin
//! (PY:1506-1517). `argv` is world-readable via `ps` / `/proc/<pid>/cmdline`
//! for the lifetime of the exec; stdin is not.

use std::fs;
use std::io::{Error, ErrorKind, Result};
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

use serde_json::{json, Map, Value};

use crate::adapter::Agent;
use crate::tmux;

/// One credential file or directory staged locally, awaiting transfer into
/// the container's filesystem at `container` via `stage_into_container`.
///
/// Replaces the old `-v host:container` bind-mount shape (docker-out-of-
/// docker fix, see module docs).
#[derive(Debug, Clone)]
pub struct StagedPath {
    pub host: PathBuf,
    pub container: String,
}

/// All per-agent staged credential paths for one workspace, ready to be
/// pushed into the running container.
///
/// Derefs to `Vec<StagedPath>` so callers can use slice/iterator methods
/// (`len()`, `iter()`, indexing) directly.
#[derive(Debug, Clone, Default)]
pub struct PreparedAuth(pub Vec<StagedPath>);

impl PreparedAuth {
    pub fn is_empty(&self) -> bool {
        self.0.is_empty()
    }

    pub fn extend(&mut self, other: PreparedAuth) {
        self.0.extend(other.0);
    }
}

impl std::ops::Deref for PreparedAuth {
    type Target = Vec<StagedPath>;
    fn deref(&self) -> &Vec<StagedPath> {
        &self.0
    }
}

impl FromIterator<StagedPath> for PreparedAuth {
    fn from_iter<T: IntoIterator<Item = StagedPath>>(iter: T) -> Self {
        Self(iter.into_iter().collect())
    }
}

#[derive(Debug, Clone)]
pub struct AuthContext {
    pub workdir: String,
    pub throwaway_dir: PathBuf,
    /// Explicit override for the operator's `~/.claude.json` source. `None`
    /// falls back to `host_src.parent() / .claude.json`. Set by callers that
    /// run from inside another container where the host's dotjson is mounted
    /// at an unrelated path - see `StartOptions::host_claude_dotjson` and
    /// the DooD discussion in `_default_claude_dotjson_from_env` (Python).
    pub host_claude_dotjson: Option<PathBuf>,
    /// When `true`, claude staging omits `.credentials.json` and stages ONLY
    /// the seeded `.claude.json` (trust/onboarding). Used by `itmux run`'s
    /// OAuth env-var path (R1/R8): the token is injected as the
    /// `CLAUDE_CODE_OAUTH_TOKEN` env var via `secret_env`, so synthesizing a
    /// `.credentials.json` (and shipping a possibly-stale one) is both
    /// unnecessary and the 401 hazard we are removing. Default `false` keeps
    /// the `itmux start` behaviour (stage `.credentials.json`) unchanged.
    pub claude_omit_credentials: bool,
}

/// Best-effort chmod on the LOCAL staging copy (defense in depth only - the
/// bytes are re-secured again in-container by `secure_path_plan` once
/// transferred, which is the guarantee that actually matters since the
/// staging dir is transient and never mounted into anything).
fn chmod_file(path: &Path, mode: u32) {
    let _ = fs::set_permissions(path, fs::Permissions::from_mode(mode));
}

fn copy_file(src: &Path, dst: &Path) -> Result<()> {
    if let Some(parent) = dst.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::copy(src, dst)?;
    Ok(())
}

/// Copy only the top-level regular files of `src` whose names are in
/// `allow_names` into `dst`. Directories and any other entries are ignored.
///
/// For agents whose home directory mixes a tiny auth/config surface with hundreds of
/// megabytes of operational state (caches, session transcripts, sqlite
/// journals), an allowlist is the only stable way to keep credential staging
/// from crawling. New bloat directories can appear at any release without
/// breaking the stage, because nothing outside `allow_names` is ever copied.
///
/// The file-type decision follows symlinks (`fs::metadata`, not
/// `DirEntry::file_type`, which stats the link itself): dotfile managers like
/// stow/chezmoi routinely symlink `auth.json`/`config.toml` into `~/.codex`,
/// and those must be staged as their target regular files. This also keeps
/// parity with the Python driver, whose `Path.is_file()` follows symlinks.
fn copy_named_files(src: &Path, dst: &Path, allow_names: &[&str]) -> Result<()> {
    if !src.exists() {
        return Ok(());
    }
    fs::create_dir_all(dst)?;
    for entry in fs::read_dir(src)? {
        let entry = entry?;
        let name = entry.file_name();
        if !allow_names.iter().any(|s| **s == *name.to_string_lossy()) {
            continue;
        }
        let path = entry.path();
        // `fs::metadata` follows symlinks; a symlink-to-regular-file counts as
        // a file and is copied by-value (`fs::copy` also follows the link).
        if fs::metadata(&path).map(|m| m.is_file()).unwrap_or(false) {
            fs::copy(&path, dst.join(&name))?;
        }
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// Claude - EXP-01 + EXP-05a

/// Build the synthetic `~/.claude.json` (mirrors Python
/// `_build_seeded_claude_dotjson`): copies `oauthAccount` through, forces
/// onboarding markers, pre-accepts the workspace project's trust dialog.
fn build_seeded_claude_dotjson(host_dotjson: &Path, workdir: &str) -> Value {
    let base: Value = if host_dotjson.is_file() {
        fs::read_to_string(host_dotjson)
            .ok()
            .and_then(|s| serde_json::from_str(&s).ok())
            .unwrap_or_else(|| Value::Object(Map::new()))
    } else {
        Value::Object(Map::new())
    };

    let num_startups = base
        .get("numStartups")
        .and_then(Value::as_i64)
        .filter(|n| *n > 0)
        .unwrap_or(5);
    let theme = base
        .get("theme")
        .and_then(Value::as_str)
        .unwrap_or("dark")
        .to_string();

    let mut seeded = Map::new();
    seeded.insert("numStartups".to_string(), json!(num_startups));
    seeded.insert("installMethod".to_string(), json!("npm-global"));
    seeded.insert("autoUpdates".to_string(), json!(false));
    seeded.insert("hasCompletedOnboarding".to_string(), json!(true));
    seeded.insert("theme".to_string(), json!(theme));
    if let Some(account) = base.get("oauthAccount") {
        seeded.insert("oauthAccount".to_string(), account.clone());
    }
    seeded.insert(
        "projects".to_string(),
        json!({
            workdir: {
                "hasTrustDialogAccepted": true,
                "hasCompletedProjectOnboarding": true,
            }
        }),
    );
    Value::Object(seeded)
}

pub fn prepare_claude(host_src: &Path, ctx: &AuthContext) -> Result<PreparedAuth> {
    if !host_src.is_dir() {
        return Err(Error::new(
            ErrorKind::NotFound,
            format!("claude auth dir not found: {}", host_src.display()),
        ));
    }

    // OAuth env-var mode (R1/R8): stage ONLY the seeded `.claude.json`
    // (trust/onboarding). The token arrives as the `CLAUDE_CODE_OAUTH_TOKEN`
    // env var via `secret_env`, so `.credentials.json` is neither required nor
    // staged (staging a stale one is the recurring 401 we are eliminating).
    let dotjson_only = ctx.claude_omit_credentials;

    let mut mounts: Vec<StagedPath> = Vec::new();
    if !dotjson_only {
        let creds = host_src.join(".credentials.json");
        if !creds.is_file() {
            return Err(Error::new(
                ErrorKind::NotFound,
                format!(
                    "claude .credentials.json missing under {}; cannot mount Max-plan auth",
                    host_src.display()
                ),
            ));
        }
        // Throwaway ~/.claude/ - copy only .credentials.json (no session history).
        let dst_dir = ctx.throwaway_dir.join("claude.dir");
        fs::create_dir_all(&dst_dir)?;
        let dst_creds = dst_dir.join(".credentials.json");
        copy_file(&creds, &dst_creds)?;
        chmod_file(&dst_creds, 0o600);
        mounts.push(StagedPath {
            host: dst_dir,
            container: "/home/agent/.claude".to_string(),
        });
    }

    // Throwaway ~/.claude.json - synthesised regardless of host presence.
    // Resolution order (caller > sibling > nothing): if the caller passed
    // `host_claude_dotjson` (via `StartOptions` or the `ITMUX_CLAUDE_JSON`
    // env var), use it directly. Otherwise fall back to the sibling-of-
    // CLAUDE_HOME path, which is correct outside a container. If neither
    // resolves, `build_seeded_claude_dotjson` synthesises a fresh dotjson
    // with onboarding/trust markers only (no `oauthAccount` passthrough).
    let dotjson_src = ctx.host_claude_dotjson.clone().unwrap_or_else(|| {
        host_src
            .parent()
            .map_or_else(|| PathBuf::from(".claude.json"), |p| p.join(".claude.json"))
    });
    let dotjson_dst = ctx.throwaway_dir.join("claude.json");
    let seeded = build_seeded_claude_dotjson(&dotjson_src, &ctx.workdir);
    fs::write(&dotjson_dst, serde_json::to_vec_pretty(&seeded)?)?;
    chmod_file(&dotjson_dst, 0o600);
    mounts.push(StagedPath {
        host: dotjson_dst,
        container: "/home/agent/.claude.json".to_string(),
    });

    Ok(PreparedAuth(mounts))
}

// ---------------------------------------------------------------------------
// Codex - EXP-02

/// Top-level `~/.codex` entries that make up the codex auth/config surface.
/// Everything else (session transcripts, sqlite journals, caches, plugin
/// bundles, `.tmp/`) is operational bloat and must never be staged. Keep in
/// sync with the Python driver's `_CodexAdapter` allowlist.
const CODEX_AUTH_FILES: [&str; 4] = ["auth.json", "config.toml", "config.json", "AGENTS.md"];

pub fn prepare_codex(host_src: &Path, ctx: &AuthContext) -> Result<PreparedAuth> {
    if !host_src.is_dir() {
        return Err(Error::new(
            ErrorKind::NotFound,
            format!("codex auth dir not found: {}", host_src.display()),
        ));
    }
    let dst_dir = ctx.throwaway_dir.join("codex.dir");
    // Stage ONLY the codex auth/config surface via an allowlist. A modern
    // `~/.codex` (codex-cli 0.139.0) mixes a few small credential/config files
    // (`auth.json`, `config.toml`) with hundreds of megabytes of operational
    // state under directories that vary by release: `.tmp/`, `sessions/`,
    // `archived_sessions/`, `logs_2.sqlite*`, `computer-use/`, `plugins/`,
    // `cache/`, etc. The old `{tmp, log, logs, plugins}` denylist missed all of
    // those, turning start_workspace into a multi-minute, thousands-of-`docker
    // exec` crawl that never completes (the `--startup-timeout` bound only
    // covers the post-launch readiness wait, not credential staging). An
    // allowlist is the only stable fix: it can't regress when codex adds new
    // state directories. `auth.json` carries the credentials; `config.toml`
    // pins the model/approval settings; `config.json`/`AGENTS.md` are copied
    // when present so per-user config/instructions survive.
    copy_named_files(host_src, &dst_dir, &CODEX_AUTH_FILES)?;
    Ok(PreparedAuth(vec![StagedPath {
        host: dst_dir,
        container: "/home/agent/.codex".to_string(),
    }]))
}

// ---------------------------------------------------------------------------
// Gemini - EXP-03

/// Gemini's durable authentication/configuration surface. Session recordings,
/// temporary files and caches are recreated by the CLI and must not turn
/// workspace startup into a per-file Docker transfer crawl.
///
/// `oauth_creds.json` holds OAuth refresh credentials; `settings.json`
/// selects the auth mode and is patched below; `google_accounts.json` and
/// `projects.json` preserve the selected account/project for Code Assist;
/// `user_id` is Gemini's stable local installation identity.
const GEMINI_AUTH_FILES: [&str; 5] = [
    "oauth_creds.json",
    "settings.json",
    "google_accounts.json",
    "projects.json",
    "user_id",
];

pub fn prepare_gemini(host_src: &Path, ctx: &AuthContext) -> Result<PreparedAuth> {
    if !host_src.is_dir() {
        return Err(Error::new(
            ErrorKind::NotFound,
            format!("gemini auth dir not found: {}", host_src.display()),
        ));
    }
    let dst_dir = ctx.throwaway_dir.join("gemini.dir");
    copy_named_files(host_src, &dst_dir, &GEMINI_AUTH_FILES)?;
    // Patch settings.json with security.folderTrust.enabled = false (EXP-03).
    let settings_path = dst_dir.join("settings.json");
    let mut settings: Value = if settings_path.is_file() {
        fs::read_to_string(&settings_path)
            .ok()
            .and_then(|s| serde_json::from_str(&s).ok())
            .unwrap_or_else(|| Value::Object(Map::new()))
    } else {
        Value::Object(Map::new())
    };
    let obj = settings
        .as_object_mut()
        .expect("settings root is an object (constructed or parsed)");
    let security = obj
        .entry("security".to_string())
        .or_insert_with(|| Value::Object(Map::new()));
    let security_obj = security
        .as_object_mut()
        .ok_or_else(|| Error::new(ErrorKind::InvalidData, "security key is not an object"))?;
    let folder_trust = security_obj
        .entry("folderTrust".to_string())
        .or_insert_with(|| Value::Object(Map::new()));
    let folder_trust_obj = folder_trust
        .as_object_mut()
        .ok_or_else(|| Error::new(ErrorKind::InvalidData, "folderTrust key is not an object"))?;
    folder_trust_obj.insert("enabled".to_string(), Value::Bool(false));
    fs::write(&settings_path, serde_json::to_vec_pretty(&settings)?)?;

    Ok(PreparedAuth(vec![StagedPath {
        host: dst_dir,
        container: "/home/agent/.gemini".to_string(),
    }]))
}

// ---------------------------------------------------------------------------
// Dispatch

pub fn prepare(agent: Agent, host_src: &Path, ctx: &AuthContext) -> Result<PreparedAuth> {
    match agent {
        Agent::Claude => prepare_claude(host_src, ctx),
        Agent::Codex => prepare_codex(host_src, ctx),
        Agent::Gemini => prepare_gemini(host_src, ctx),
    }
}

// ---------------------------------------------------------------------------
// Transfer plan (pure, testable without a docker daemon) + execution.

/// One step of a credential transfer/secure plan: a `docker exec <container>
/// <argv...>` invocation, optionally fed `stdin` bytes.
///
/// Built as plain data (rather than shelling out directly) so the plan can
/// be asserted on in tests without a running docker daemon - see
/// `tests/cred_transfer.rs`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExecStep {
    pub argv: Vec<String>,
    pub stdin: Option<Vec<u8>>,
}

/// POSIX `dirname`, matching Python's `posixpath.dirname` for the ASCII
/// forward-slash paths this driver deals with exclusively (in-container
/// Linux paths).
fn posix_dirname(path: &str) -> String {
    match path.rfind('/') {
        Some(0) => "/".to_string(),
        Some(idx) => path[..idx].to_string(),
        None => String::new(),
    }
}

/// Shell-quote a single argument, matching Python's `shlex.quote`: safe
/// (alnum + `-_./:`) strings pass through unquoted; anything else is
/// wrapped in single quotes with embedded quotes escaped as `'\''`.
fn shell_quote(s: &str) -> String {
    if !s.is_empty()
        && s.chars()
            .all(|c| c.is_ascii_alphanumeric() || "-_./:".contains(c))
    {
        return s.to_string();
    }
    format!("'{}'", s.replace('\'', "'\\''"))
}

/// Minimal std-only base64 encoder (standard alphabet, `=` padding)  -
/// avoids pulling in a dependency for the one encode call this crate needs
/// (decoding happens in-container via the coreutils `base64 -d`).
fn base64_encode(data: &[u8]) -> Vec<u8> {
    const ALPHABET: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut out = Vec::with_capacity(data.len().div_ceil(3) * 4);
    for chunk in data.chunks(3) {
        let b0 = chunk[0];
        let b1 = chunk.get(1).copied();
        let b2 = chunk.get(2).copied();
        out.push(ALPHABET[(b0 >> 2) as usize]);
        out.push(ALPHABET[(((b0 & 0x03) << 4) | (b1.unwrap_or(0) >> 4)) as usize]);
        if let Some(b1) = b1 {
            out.push(ALPHABET[(((b1 & 0x0F) << 2) | (b2.unwrap_or(0) >> 6)) as usize]);
        } else {
            out.push(b'=');
        }
        if let Some(b2) = b2 {
            out.push(ALPHABET[(b2 & 0x3F) as usize]);
        } else {
            out.push(b'=');
        }
    }
    out
}

/// Mirrors Python `_write_bytes_to_container`: `mkdir -p` the destination's
/// parent (if non-empty), truncate/create the destination, then push the
/// payload as base64 over stdin to an in-container `base64 -d`. Credentials
/// never appear in argv (PY:1506-1517) - only inside `ExecStep::stdin`.
pub fn write_bytes_plan(container_path: &str, data: &[u8]) -> Vec<ExecStep> {
    let mut steps = Vec::new();
    let parent = posix_dirname(container_path);
    if !parent.is_empty() {
        steps.push(ExecStep {
            argv: vec!["mkdir".to_string(), "-p".to_string(), parent],
            stdin: None,
        });
    }
    let quoted = shell_quote(container_path);
    steps.push(ExecStep {
        argv: vec!["sh".to_string(), "-c".to_string(), format!("> {quoted}")],
        stdin: None,
    });
    steps.push(ExecStep {
        argv: vec![
            "sh".to_string(),
            "-c".to_string(),
            format!("base64 -d >> {quoted}"),
        ],
        stdin: Some(base64_encode(data)),
    });
    steps
}

fn walk_files_sorted(dir: &Path) -> Result<Vec<PathBuf>> {
    let mut out = Vec::new();
    let mut stack = vec![dir.to_path_buf()];
    while let Some(d) = stack.pop() {
        for entry in fs::read_dir(&d)? {
            let entry = entry?;
            let path = entry.path();
            let kind = entry.file_type()?;
            if kind.is_dir() {
                stack.push(path);
            } else if kind.is_file() {
                out.push(path);
            }
        }
    }
    out.sort();
    Ok(out)
}

/// Mirrors Python `_transfer_path_to_container`'s directory branch: walks
/// `host_dir` (matching `os.walk`) and builds a `write_bytes_plan` for every
/// regular file, keyed by its path relative to `host_dir` joined onto
/// `container_path`. Deliberately per-file (not a `tar` stream) for exact
/// parity with the Python source of truth (PY:1554-1561).
pub fn transfer_dir_plan(host_dir: &Path, container_path: &str) -> Result<Vec<ExecStep>> {
    let mut steps = Vec::new();
    let base = container_path.trim_end_matches('/');
    for file in walk_files_sorted(host_dir)? {
        let rel = file
            .strip_prefix(host_dir)
            .expect("walked file is under host_dir")
            .to_string_lossy()
            .replace(std::path::MAIN_SEPARATOR, "/");
        let dst = format!("{base}/{rel}");
        let data = fs::read(&file)?;
        steps.extend(write_bytes_plan(&dst, &data));
    }
    Ok(steps)
}

/// Mirrors Python `_secure_container_path`: chown the transferred path to
/// the in-container `agent` user (uid/gid 1000) and lock file permissions
/// to 0600. For a directory, `chown -R` the whole tree and `chmod 600`
/// every regular file under it via `find` - matching PY:1566-1583 exactly,
/// including that the directory's own mode is intentionally left
/// untouched (Python does not `chmod` the directory itself, only the files
/// inside it).
pub fn secure_path_plan(container_path: &str, is_dir: bool) -> ExecStep {
    let quoted = shell_quote(container_path);
    let cmd = if is_dir {
        format!("chown -R 1000:1000 {quoted} && find {quoted} -type f -exec chmod 600 {{}} +")
    } else {
        format!("chown 1000:1000 {quoted} && chmod 600 {quoted}")
    };
    ExecStep {
        argv: vec!["sh".to_string(), "-c".to_string(), cmd],
        stdin: None,
    }
}

/// Full plan (transfer steps + trailing secure step) for one staged path.
/// Pure and side-effect-free: reads the local staged bytes (needed to embed
/// them in the plan) but performs no `docker exec` calls. Exposed for
/// tests that assert the plan shape without a docker daemon.
pub fn plan_for_staged_path(staged: &StagedPath) -> Result<Vec<ExecStep>> {
    let is_dir = staged.host.is_dir();
    let mut steps = if is_dir {
        transfer_dir_plan(&staged.host, &staged.container)?
    } else {
        let data = fs::read(&staged.host)?;
        write_bytes_plan(&staged.container, &data)
    };
    steps.push(secure_path_plan(&staged.container, is_dir));
    Ok(steps)
}

fn run_exec_step(container: &str, step: &ExecStep, timeout: Duration) -> Result<()> {
    let argv_refs: Vec<&str> = step.argv.iter().map(String::as_str).collect();
    match &step.stdin {
        Some(bytes) => {
            tmux::docker_exec_with_stdin_timeout(container, &argv_refs, bytes, timeout)?;
        }
        None => {
            tmux::docker_exec_timeout(container, &argv_refs, timeout)?;
        }
    }
    Ok(())
}

fn staging_step_timeout(deadline: Instant, now: Instant) -> Result<Duration> {
    deadline
        .checked_duration_since(now)
        .ok_or_else(|| {
            Error::new(
                ErrorKind::TimedOut,
                "credential staging exceeded the 60s total deadline",
            )
        })
        .map(|remaining| remaining.min(Duration::from_secs_f64(tmux::DEFAULT_EXEC_TIMEOUT_S)))
}

/// Push every staged path in `prepared` into `container`'s filesystem over
/// `docker exec` and lock down ownership/permissions in-container.
///
/// The container is assumed already started (bare `docker run ... sleep
/// infinity`, no credential bind mounts - see `workspace::Workspace::start`).
/// This is the "PUSHES credential files ... then secures them in-container"
/// half of the docker-out-of-docker fix (PY:1850-1869).
pub fn stage_into_container(container: &str, prepared: &PreparedAuth) -> Result<()> {
    // Per-command bounds prevent a wedged Docker operation; this aggregate
    // deadline prevents a large (or accidentally unbounded) credential tree
    // from converting startup into an unbounded sequence of otherwise-valid
    // transfers. Each command receives only the remaining budget.
    const STAGING_TIMEOUT: Duration = Duration::from_secs(60);
    let deadline = Instant::now() + STAGING_TIMEOUT;
    for staged in prepared.iter() {
        for step in plan_for_staged_path(staged)? {
            let timeout = staging_step_timeout(deadline, Instant::now())?;
            run_exec_step(container, &step, timeout)?;
        }
    }
    Ok(())
}

#[cfg(test)]
mod base64_tests {
    use super::{base64_encode, staging_step_timeout};
    use std::io::ErrorKind;
    use std::time::{Duration, Instant};

    // RFC 4648 section 10 test vectors, plus high-bit bytes to guard the
    // std-only encoder against sign/padding regressions (the whole credential
    // path depends on this being byte-exact; the container-side `base64 -d`
    // only runs under real docker).
    #[test]
    fn rfc4648_and_high_bit_vectors() {
        let cases: &[(&[u8], &[u8])] = &[
            (b"", b""),
            (b"f", b"Zg=="),
            (b"fo", b"Zm8="),
            (b"foo", b"Zm9v"),
            (b"foob", b"Zm9vYg=="),
            (b"fooba", b"Zm9vYmE="),
            (b"foobar", b"Zm9vYmFy"),
            (b"\x00", b"AA=="),
            (b"\xff", b"/w=="),
            (b"\xff\xff", b"//8="),
            (b"\xff\xff\xff", b"////"),
            (b"\x00\x10\x83", b"ABCD"),
        ];
        for (input, expected) in cases {
            assert_eq!(
                base64_encode(input),
                expected.to_vec(),
                "base64_encode({input:?}) mismatch"
            );
        }
    }

    #[test]
    fn staging_timeout_caps_each_step_and_rejects_an_expired_deadline() {
        let start = Instant::now();
        assert_eq!(
            staging_step_timeout(start + Duration::from_secs(60), start).unwrap(),
            Duration::from_secs(15)
        );
        let err = staging_step_timeout(start, start + Duration::from_nanos(1)).unwrap_err();
        assert_eq!(err.kind(), ErrorKind::TimedOut);
    }
}
