//! Per-agent host-auth mount preparation.
//!
//! Each adapter copies (never moves) the relevant host directory under a
//! per-workspace throwaway dir (`/tmp/interactive-tmux-<name>-<random>/`)
//! so the container can bind-mount fresh credential bytes without ever
//! mutating the operator's live `~/.claude`, `~/.codex`, `~/.gemini`.
//!
//! Synthesised files (claude's `~/.claude.json`, gemini's `settings.json`
//! patch) follow the Python driver's policy bit-for-bit so the two
//! implementations produce interchangeable mounts.

use std::fs;
use std::io::{Error, ErrorKind, Result};
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};

use serde_json::{json, Map, Value};

use crate::adapter::Agent;

/// One `-v host:container` pair to hand to `docker run`.
#[derive(Debug, Clone)]
pub struct Mount {
    pub host: PathBuf,
    pub container: String,
}

impl Mount {
    pub fn as_docker_arg(&self) -> String {
        format!("{}:{}", self.host.display(), self.container)
    }
}

#[derive(Debug, Clone)]
pub struct AuthContext {
    pub workdir: String,
    pub throwaway_dir: PathBuf,
    /// Explicit override for the operator's `~/.claude.json` source. `None`
    /// falls back to `host_src.parent() / .claude.json`. Set by callers that
    /// run from inside another container where the host's dotjson is mounted
    /// at an unrelated path — see `StartOptions::host_claude_dotjson` and
    /// the DooD discussion in `_default_claude_dotjson_from_env` (Python).
    pub host_claude_dotjson: Option<PathBuf>,
}

/// Best-effort chmod (non-fatal — docker will run as the requested uid
/// inside the container regardless).
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

fn copy_tree(src: &Path, dst: &Path, skip_names: &[&str]) -> Result<()> {
    if !src.exists() {
        return Ok(());
    }
    fs::create_dir_all(dst)?;
    for entry in fs::read_dir(src)? {
        let entry = entry?;
        let name = entry.file_name();
        if skip_names.iter().any(|s| **s == *name.to_string_lossy()) {
            continue;
        }
        let kind = entry.file_type()?;
        let src_path = entry.path();
        let dst_path = dst.join(&name);
        if kind.is_dir() {
            copy_tree(&src_path, &dst_path, &[])?;
        } else if kind.is_file() {
            fs::copy(&src_path, &dst_path)?;
        }
        // Ignore unsupported entries (symlinks to vanished files, sockets):
        // the Python adapter does the same — the auth surface is regular
        // files in practice.
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// Claude — EXP-01 + EXP-05a

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

pub fn prepare_claude(host_src: &Path, ctx: &AuthContext) -> Result<Vec<Mount>> {
    if !host_src.is_dir() {
        return Err(Error::new(
            ErrorKind::NotFound,
            format!("claude auth dir not found: {}", host_src.display()),
        ));
    }
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

    // Throwaway ~/.claude/ — copy only .credentials.json (no session history).
    let dst_dir = ctx.throwaway_dir.join("claude.dir");
    fs::create_dir_all(&dst_dir)?;
    let dst_creds = dst_dir.join(".credentials.json");
    copy_file(&creds, &dst_creds)?;
    chmod_file(&dst_creds, 0o600);

    // Throwaway ~/.claude.json — synthesised regardless of host presence.
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

    Ok(vec![
        Mount {
            host: dst_dir,
            container: "/home/agent/.claude".to_string(),
        },
        Mount {
            host: dotjson_dst,
            container: "/home/agent/.claude.json".to_string(),
        },
    ])
}

// ---------------------------------------------------------------------------
// Codex — EXP-02

pub fn prepare_codex(host_src: &Path, ctx: &AuthContext) -> Result<Vec<Mount>> {
    if !host_src.is_dir() {
        return Err(Error::new(
            ErrorKind::NotFound,
            format!("codex auth dir not found: {}", host_src.display()),
        ));
    }
    let dst_dir = ctx.throwaway_dir.join("codex.dir");
    // Skip tmp/log/logs: codex races there during normal operation. The auth
    // surface lives at `auth.json` / `config.toml` / `sessions/`.
    copy_tree(host_src, &dst_dir, &["tmp", "log", "logs"])?;
    Ok(vec![Mount {
        host: dst_dir,
        container: "/home/agent/.codex".to_string(),
    }])
}

// ---------------------------------------------------------------------------
// Gemini — EXP-03

pub fn prepare_gemini(host_src: &Path, ctx: &AuthContext) -> Result<Vec<Mount>> {
    if !host_src.is_dir() {
        return Err(Error::new(
            ErrorKind::NotFound,
            format!("gemini auth dir not found: {}", host_src.display()),
        ));
    }
    let dst_dir = ctx.throwaway_dir.join("gemini.dir");
    copy_tree(host_src, &dst_dir, &[])?;
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

    Ok(vec![Mount {
        host: dst_dir,
        container: "/home/agent/.gemini".to_string(),
    }])
}

// ---------------------------------------------------------------------------
// Dispatch

pub fn prepare(agent: Agent, host_src: &Path, ctx: &AuthContext) -> Result<Vec<Mount>> {
    match agent {
        Agent::Claude => prepare_claude(host_src, ctx),
        Agent::Codex => prepare_codex(host_src, ctx),
        Agent::Gemini => prepare_gemini(host_src, ctx),
    }
}
