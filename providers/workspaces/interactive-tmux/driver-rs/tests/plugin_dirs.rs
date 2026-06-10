//! Unit tests for the `--plugin-dir` flag construction in the claude
//! launch command, mirroring the Python
//! `test_interactive_tmux_plugin_dirs.py`.
//!
//! Surfaced by Syntropic137's workflow-skills bridge experiment
//! (`docs/plans/workflow-skills.md` §9): `~/.claude.json`
//! `installedPlugins` injection is silently ignored by the TUI; only the
//! `--plugin-dir` CLI flag actually loads plugins.

use std::path::PathBuf;

use itmux::adapter::claude_launch_command;

#[test]
fn no_plugin_dirs_yields_bare_claude() {
    assert_eq!(claude_launch_command(&[]), "claude");
}

#[test]
fn single_plugin_dir() {
    assert_eq!(
        claude_launch_command(&[PathBuf::from("/opt/skills")]),
        "claude --plugin-dir /opt/skills"
    );
}

#[test]
fn multiple_plugin_dirs_emit_one_flag_per_path() {
    let cmd = claude_launch_command(&[
        PathBuf::from("/opt/skills"),
        PathBuf::from("/opt/observability"),
        PathBuf::from("/opt/notifications"),
    ]);
    assert_eq!(
        cmd,
        "claude --plugin-dir /opt/skills --plugin-dir /opt/observability --plugin-dir /opt/notifications"
    );
    // Sanity: one flag per path.
    assert_eq!(cmd.matches("--plugin-dir").count(), 3);
}

#[test]
fn paths_with_spaces_get_shell_quoted() {
    let cmd = claude_launch_command(&[
        PathBuf::from("/opt/skills"),
        PathBuf::from("/opt/with space/here"),
    ]);
    // Single-quoted to survive a shell tokenizer.
    assert!(cmd.contains("'/opt/with space/here'"), "cmd={cmd}");
    // The plain path is NOT quoted (only chars that need it are).
    assert!(cmd.contains(" /opt/skills "), "cmd={cmd}");
}

#[test]
fn paths_with_embedded_single_quote_safely_escaped() {
    let cmd = claude_launch_command(&[PathBuf::from("/opt/it's mine")]);
    // shlex-style close-escape-reopen: `'…it'\''s mine…'`
    assert!(cmd.contains("'/opt/it'\\''s mine'"), "cmd={cmd}");
}

#[test]
fn flag_order_matches_input_order() {
    let cmd = claude_launch_command(&[
        PathBuf::from("/p1"),
        PathBuf::from("/p2"),
        PathBuf::from("/p3"),
    ]);
    let p1 = cmd.find("/p1").expect("p1 in cmd");
    let p2 = cmd.find("/p2").expect("p2 in cmd");
    let p3 = cmd.find("/p3").expect("p3 in cmd");
    assert!(p1 < p2 && p2 < p3, "out of order: cmd={cmd}");
}
