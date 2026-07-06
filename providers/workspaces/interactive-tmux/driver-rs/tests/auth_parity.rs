//! Auth-mount preparation parity tests — verify the synthesised
//! `~/.claude.json` and patched gemini `settings.json` match the Python
//! driver's bytes for the parts the smoke depends on.

use std::fs;
use std::path::PathBuf;

use itmux::adapter::Agent;
use itmux::auth::{prepare, AuthContext};

fn tmp(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!(
        "itmux-test-{name}-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir_all(&dir).unwrap();
    dir
}

#[test]
fn claude_seeds_synthetic_dotjson_when_host_missing() {
    // Arrange: host .claude/ with only .credentials.json, no .claude.json.
    let host_root = tmp("claude-host-root");
    let claude_dir = host_root.join(".claude");
    fs::create_dir_all(&claude_dir).unwrap();
    fs::write(claude_dir.join(".credentials.json"), b"{}").unwrap();

    let throwaway = tmp("claude-throwaway");
    let ctx = AuthContext {
        workdir: "/workspace".to_string(),
        throwaway_dir: throwaway.clone(),
        host_claude_dotjson: None,
    };

    let mounts = prepare(Agent::Claude, &claude_dir, &ctx).unwrap();
    assert_eq!(mounts.len(), 2);

    let dotjson_mount = mounts
        .iter()
        .find(|m| m.container == "/home/agent/.claude.json")
        .expect("claude adapter mounts .claude.json");
    let body: serde_json::Value =
        serde_json::from_slice(&fs::read(&dotjson_mount.host).unwrap()).unwrap();
    assert_eq!(body["hasCompletedOnboarding"], true);
    assert_eq!(body["installMethod"], "npm-global");
    assert_eq!(body["autoUpdates"], false);
    assert_eq!(body["theme"], "dark");
    assert_eq!(
        body["projects"]["/workspace"]["hasTrustDialogAccepted"],
        true
    );
    assert_eq!(
        body["projects"]["/workspace"]["hasCompletedProjectOnboarding"],
        true
    );
}

#[test]
fn claude_seeds_carry_oauth_account_through_when_host_present() {
    let host_root = tmp("claude-host-with-dotjson");
    let claude_dir = host_root.join(".claude");
    fs::create_dir_all(&claude_dir).unwrap();
    fs::write(claude_dir.join(".credentials.json"), b"{}").unwrap();
    fs::write(
        host_root.join(".claude.json"),
        r#"{"oauthAccount":{"email":"neural@example.com","uuid":"abc"},"theme":"light","numStartups":42}"#,
    )
    .unwrap();

    let throwaway = tmp("claude-throwaway-2");
    let ctx = AuthContext {
        workdir: "/workspace".to_string(),
        throwaway_dir: throwaway.clone(),
        host_claude_dotjson: None,
    };
    let mounts = prepare(Agent::Claude, &claude_dir, &ctx).unwrap();
    let dotjson_mount = mounts
        .iter()
        .find(|m| m.container == "/home/agent/.claude.json")
        .unwrap();
    let body: serde_json::Value =
        serde_json::from_slice(&fs::read(&dotjson_mount.host).unwrap()).unwrap();
    assert_eq!(body["oauthAccount"]["email"], "neural@example.com");
    assert_eq!(body["theme"], "light");
    assert_eq!(body["numStartups"], 42);
}

#[test]
fn claude_honors_explicit_dotjson_override_dood_case() {
    // DooD case (PR #202 follow-up): the operator's `.claude/` is mounted
    // into the calling container at one path, and the operator's
    // `.claude.json` is mounted at a DIFFERENT path (not the parent of
    // `.claude/`). The sibling-fallback would look in the wrong place and
    // synthesise a fresh dotjson without `oauthAccount` passthrough.
    // With `host_claude_dotjson` set, the override path is used directly.
    let claude_dir = tmp("claude-dir-dood");
    fs::write(claude_dir.join(".credentials.json"), b"{}").unwrap();

    let dotjson_path = tmp("claude-json-dood").join("mounted-claude.json");
    fs::write(
        &dotjson_path,
        r#"{"oauthAccount":{"email":"dood@example.com","uuid":"d00d"},"theme":"dark"}"#,
    )
    .unwrap();

    let throwaway = tmp("claude-throwaway-dood");
    let ctx = AuthContext {
        workdir: "/workspace".to_string(),
        throwaway_dir: throwaway.clone(),
        host_claude_dotjson: Some(dotjson_path.clone()),
    };

    let mounts = prepare(Agent::Claude, &claude_dir, &ctx).unwrap();
    let dotjson_mount = mounts
        .iter()
        .find(|m| m.container == "/home/agent/.claude.json")
        .unwrap();
    let body: serde_json::Value =
        serde_json::from_slice(&fs::read(&dotjson_mount.host).unwrap()).unwrap();
    // Came from the explicit override, not from a sibling-of-claude-dir
    // lookup (the sibling does NOT exist in this layout).
    assert_eq!(body["oauthAccount"]["email"], "dood@example.com");
    assert_eq!(body["oauthAccount"]["uuid"], "d00d");
}

#[test]
fn claude_rejects_missing_credentials_file() {
    let host_root = tmp("claude-host-bad");
    let claude_dir = host_root.join(".claude");
    fs::create_dir_all(&claude_dir).unwrap();
    let ctx = AuthContext {
        workdir: "/workspace".to_string(),
        throwaway_dir: tmp("claude-throwaway-bad"),
        host_claude_dotjson: None,
    };
    let err = prepare(Agent::Claude, &claude_dir, &ctx).unwrap_err();
    assert!(err.to_string().contains(".credentials.json"));
}

#[test]
fn gemini_patches_folder_trust_in_settings() {
    let host = tmp("gemini-host");
    fs::write(host.join("settings.json"), r#"{"unrelated":true}"#).unwrap();
    let throwaway = tmp("gemini-throwaway");
    let ctx = AuthContext {
        workdir: "/workspace".to_string(),
        throwaway_dir: throwaway.clone(),
        host_claude_dotjson: None,
    };
    let mounts = prepare(Agent::Gemini, &host, &ctx).unwrap();
    assert_eq!(mounts.len(), 1);
    let patched: serde_json::Value =
        serde_json::from_slice(&fs::read(mounts[0].host.join("settings.json")).unwrap()).unwrap();
    assert_eq!(patched["security"]["folderTrust"]["enabled"], false);
    // Original unrelated field preserved.
    assert_eq!(patched["unrelated"], true);
}

#[test]
fn codex_stages_only_the_auth_allowlist() {
    // Codex staging is an ALLOWLIST: only the small auth/config files at the
    // top of `~/.codex` are staged. Every operational directory (`.tmp/`,
    // `sessions/`, `logs_2.sqlite*`, `computer-use/`, `plugins/`, ...) is left
    // behind so start_workspace can't crawl hundreds of megabytes over
    // per-file `docker exec` and hang forever.
    let host = tmp("codex-host");
    // Allowed auth/config surface (full declared allowlist).
    fs::write(host.join("auth.json"), b"{}").unwrap();
    fs::write(host.join("config.toml"), b"model = \"x\"").unwrap();
    fs::write(host.join("config.json"), b"{}").unwrap();
    fs::write(host.join("AGENTS.md"), b"# global instructions").unwrap();
    // Non-auth bloat that MUST NOT be staged.
    fs::create_dir_all(host.join(".tmp")).unwrap();
    fs::create_dir_all(host.join("sessions")).unwrap();
    fs::create_dir_all(host.join("plugins")).unwrap();
    fs::create_dir_all(host.join("computer-use")).unwrap();
    fs::write(host.join(".tmp").join("racy-argv.bin"), b"vanish").unwrap();
    fs::write(host.join("sessions").join("01.json"), b"{}").unwrap();
    fs::write(host.join("plugins").join("node_modules_stub"), b"heavy").unwrap();
    fs::write(host.join("logs_2.sqlite"), vec![0u8; 4096]).unwrap();

    let ctx = AuthContext {
        workdir: "/workspace".to_string(),
        throwaway_dir: tmp("codex-throwaway"),
        host_claude_dotjson: None,
    };
    let mounts = prepare(Agent::Codex, &host, &ctx).unwrap();
    assert_eq!(mounts.len(), 1);
    let dst = &mounts[0].host;
    // Auth surface staged.
    assert!(dst.join("auth.json").is_file(), "auth.json must be staged");
    assert!(
        dst.join("config.toml").is_file(),
        "config.toml must be staged"
    );
    assert!(
        dst.join("config.json").is_file(),
        "config.json must be staged"
    );
    assert!(dst.join("AGENTS.md").is_file(), "AGENTS.md must be staged");
    // Everything else left behind.
    assert!(!dst.join(".tmp").exists(), ".tmp/ must NOT be staged");
    assert!(
        !dst.join("sessions").exists(),
        "sessions/ must NOT be staged"
    );
    assert!(!dst.join("plugins").exists(), "plugins/ must NOT be staged");
    assert!(
        !dst.join("computer-use").exists(),
        "computer-use/ must NOT be staged"
    );
    assert!(
        !dst.join("logs_2.sqlite").exists(),
        "sqlite journals must NOT be staged"
    );
}

#[cfg(unix)]
#[test]
fn codex_stages_symlinked_auth_files() {
    // Dotfile managers (stow/chezmoi) symlink `auth.json`/`config.toml` into
    // `~/.codex`. The allowlist decision must follow symlinks (parity with
    // Python's `Path.is_file()`), or the exact files the fix exists to
    // preserve get silently dropped.
    use std::os::unix::fs::symlink;

    let real = tmp("codex-real-store");
    fs::write(real.join("auth.json"), b"{\"token\":\"real\"}").unwrap();
    fs::write(real.join("config.toml"), b"model = \"y\"").unwrap();

    let host = tmp("codex-symlink-host");
    symlink(real.join("auth.json"), host.join("auth.json")).unwrap();
    symlink(real.join("config.toml"), host.join("config.toml")).unwrap();

    let ctx = AuthContext {
        workdir: "/workspace".to_string(),
        throwaway_dir: tmp("codex-symlink-throwaway"),
        host_claude_dotjson: None,
    };
    let mounts = prepare(Agent::Codex, &host, &ctx).unwrap();
    let dst = &mounts[0].host;
    // Symlinked entries are staged as their target's regular-file contents.
    assert!(
        dst.join("auth.json").is_file(),
        "symlinked auth.json must be staged"
    );
    assert!(
        dst.join("config.toml").is_file(),
        "symlinked config.toml must be staged"
    );
    assert_eq!(
        fs::read(dst.join("auth.json")).unwrap(),
        b"{\"token\":\"real\"}",
        "staged copy must carry the symlink target's bytes"
    );
}
