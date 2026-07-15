//! Docker-out-of-docker credential transfer parity tests.
//!
//! Syntropic137 runs this driver INSIDE a container. A sibling
//! `docker run -v host:container` bind mount resolves `host` against the
//! OUTER daemon's filesystem and can't see this driver's own staging dir  -
//! so credentials must be pushed into the container over `docker exec`
//! stdin instead (mirrors `driver/interactive_tmux.py` PY:1493-1583,
//! PY:1850-1869). These tests assert the command *plan* built by pure
//! functions in `auth` and `workspace` - no docker daemon required.

use std::fs;
use std::path::PathBuf;

use itmux::auth::{
    plan_for_staged_path, prepare, secure_path_plan, stage_into_container, write_bytes_plan,
    AuthContext,
};
use itmux::workspace::build_docker_run_argv;
use itmux::Agent;

fn tmp(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!(
        "itmux-cred-transfer-{name}-{}-{}",
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
fn docker_run_argv_carries_no_v_flags() {
    let argv = build_docker_run_argv(
        "interactive-tmux-foo-abcd1234",
        "/workspace",
        "my-image:latest",
    );
    assert!(
        !argv.iter().any(|a| a == "-v"),
        "docker run argv must not bind-mount credentials in DooD: {argv:?}"
    );
    assert_eq!(
        argv,
        vec![
            "run",
            "-d",
            "--name",
            "interactive-tmux-foo-abcd1234",
            "--workdir",
            "/workspace",
            "my-image:latest",
            "sleep",
            "infinity",
        ]
    );
}

#[test]
fn prepare_yields_staged_destination_paths_not_mount_bind_args() {
    let host_root = tmp("claude-host-root");
    let claude_dir = host_root.join(".claude");
    fs::create_dir_all(&claude_dir).unwrap();
    fs::write(claude_dir.join(".credentials.json"), b"{}").unwrap();

    let ctx = AuthContext {
        workdir: "/workspace".to_string(),
        throwaway_dir: tmp("claude-throwaway"),
        host_claude_dotjson: None,
    };

    let prepared = prepare(Agent::Claude, &claude_dir, &ctx).unwrap();
    assert_eq!(prepared.len(), 2);
    // Destinations are in-container paths meant for exec-transfer, never a
    // "host:container" bind-mount argument string.
    for staged in prepared.iter() {
        assert!(staged.container.starts_with("/home/agent/"));
        assert!(
            !staged.container.contains(':'),
            "container dest must not look like a `-v host:container` arg: {}",
            staged.container
        );
        assert!(staged.host.exists(), "locally staged file must exist");
    }
}

#[test]
fn write_bytes_plan_never_puts_payload_in_argv() {
    let secret = b"super-secret-oauth-token-xyz";
    let steps = write_bytes_plan("/home/agent/.claude.json", secret);

    // mkdir -p parent, truncate, then base64-decode-from-stdin.
    assert_eq!(steps.len(), 3);
    assert_eq!(steps[0].argv, vec!["mkdir", "-p", "/home/agent"]);
    assert!(steps[0].stdin.is_none());

    assert_eq!(steps[1].argv[0], "sh");
    assert!(steps[1].argv[2].starts_with('>'));
    assert!(steps[1].stdin.is_none());

    assert_eq!(steps[2].argv[0], "sh");
    assert!(steps[2].argv[2].contains("base64 -d"));
    let stdin = steps[2].stdin.as_ref().expect("payload travels via stdin");

    // The secret bytes must never appear in any argv string.
    for step in &steps {
        for arg in &step.argv {
            assert!(
                !arg.as_bytes()
                    .windows(secret.len())
                    .any(|w| w == secret.as_slice()),
                "credential payload leaked into argv: {arg}"
            );
        }
    }
    // But the (base64-encoded) payload must be present in stdin somewhere.
    assert!(!stdin.is_empty());
}

#[test]
fn secure_path_plan_chowns_1000_1000_and_chmods_600_for_a_file() {
    let step = secure_path_plan("/home/agent/.claude.json", false);
    assert_eq!(step.argv[0], "sh");
    assert_eq!(step.argv[1], "-c");
    let cmd = &step.argv[2];
    assert!(cmd.contains("chown 1000:1000"), "got: {cmd}");
    assert!(cmd.contains("chmod 600"), "got: {cmd}");
    assert!(step.stdin.is_none());
}

#[test]
fn secure_path_plan_chowns_recursively_and_chmods_600_every_file_for_a_dir() {
    let step = secure_path_plan("/home/agent/.codex", true);
    let cmd = &step.argv[2];
    assert!(cmd.contains("chown -R 1000:1000"), "got: {cmd}");
    assert!(cmd.contains("chmod 600"), "got: {cmd}");
    assert!(cmd.contains("find"), "dir secure step must use find: {cmd}");
}

#[test]
fn plan_for_prepared_claude_auth_includes_transfer_and_secure_steps_for_every_staged_path() {
    let host_root = tmp("claude-host-root-2");
    let claude_dir = host_root.join(".claude");
    fs::create_dir_all(&claude_dir).unwrap();
    fs::write(claude_dir.join(".credentials.json"), b"{}").unwrap();

    let ctx = AuthContext {
        workdir: "/workspace".to_string(),
        throwaway_dir: tmp("claude-throwaway-2"),
        host_claude_dotjson: None,
    };
    let prepared = prepare(Agent::Claude, &claude_dir, &ctx).unwrap();

    // Two staged paths (the .claude dir, the synthesised .claude.json)  -
    // each must get its own secure (chown+chmod) step after transfer.
    let mut secure_steps_seen = 0;
    for staged in prepared.iter() {
        let plan = itmux::auth::plan_for_staged_path(staged).unwrap();
        let last = plan.last().expect("plan has at least the secure step");
        assert!(last.argv[2].contains("chown"));
        assert!(last.argv[2].contains("1000:1000"));
        assert!(last.argv[2].contains("chmod 600"));
        secure_steps_seen += 1;
    }
    assert_eq!(secure_steps_seen, 2);
}

#[test]
fn stage_into_container_without_docker_fails_cleanly_not_via_v_mount() {
    // No docker daemon / container named this in the test environment  -
    // `stage_into_container` must attempt a `docker exec` (and fail with an
    // I/O or nonzero-exit error) rather than silently succeeding via some
    // bind-mount fallback. This exercises the real code path end-to-end
    // (argv construction, stdin plumbing) even though the outer assertion
    // is just "it does not panic and returns a Result".
    let host_root = tmp("claude-host-root-3");
    let claude_dir = host_root.join(".claude");
    fs::create_dir_all(&claude_dir).unwrap();
    fs::write(claude_dir.join(".credentials.json"), b"{}").unwrap();
    let ctx = AuthContext {
        workdir: "/workspace".to_string(),
        throwaway_dir: tmp("claude-throwaway-3"),
        host_claude_dotjson: None,
    };
    let prepared = prepare(Agent::Claude, &claude_dir, &ctx).unwrap();

    let result = stage_into_container("itmux-cred-transfer-test-nonexistent-container", &prepared);
    // Either docker isn't installed (I/O error) or the container doesn't
    // exist (nonzero exit) - both surface as Err, never a silent Ok that
    // would mean credentials were dropped via some other, unaudited path.
    assert!(result.is_err());
}

#[test]
fn gemini_stages_only_durable_auth_and_config_files() {
    let host_root = tmp("gemini-host-root");
    let gemini_dir = host_root.join(".gemini");
    fs::create_dir_all(gemini_dir.join("tmp/session-1")).unwrap();
    fs::create_dir_all(gemini_dir.join("cache")).unwrap();
    for name in [
        "oauth_creds.json",
        "settings.json",
        "google_accounts.json",
        "projects.json",
        "user_id",
    ] {
        fs::write(gemini_dir.join(name), b"{}").unwrap();
    }
    fs::write(gemini_dir.join("tmp/session-1/chat.json"), b"history").unwrap();
    fs::write(gemini_dir.join("cache/blob"), b"cache").unwrap();

    let ctx = AuthContext {
        workdir: "/workspace".to_string(),
        throwaway_dir: tmp("gemini-throwaway"),
        host_claude_dotjson: None,
    };
    let prepared = prepare(Agent::Gemini, &gemini_dir, &ctx).unwrap();
    let staged = prepared.first().expect("Gemini has one staged directory");
    assert!(staged.host.join("oauth_creds.json").is_file());
    assert!(staged.host.join("settings.json").is_file());
    assert!(!staged.host.join("tmp").exists());
    assert!(!staged.host.join("cache").exists());

    let plan = plan_for_staged_path(staged).unwrap();
    assert!(plan.len() < 20, "only durable Gemini files are transferred");
}
