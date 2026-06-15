//! On-disk workspace registry shared with the Python driver.
//!
//! Schema is byte-identical to `_save_workspace`/`_load_workspace` in
//! `interactive_tmux.py` so a Rust `start` and a Python `stop` round-trip
//! (and vice versa). Files live at
//! `/tmp/interactive-tmux-workspaces/<name>.json`.

use std::env;
use std::fs;
use std::io::{Error, Result};
use std::path::PathBuf;

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkspaceRecord {
    pub name: String,
    pub container: String,
    pub image: String,
    pub workdir: String,
    pub tmux_size: [u32; 2],
    pub host_throwaway_dir: String,
    pub enabled_agents: Vec<String>,
}

pub fn registry_dir() -> PathBuf {
    env::temp_dir().join("interactive-tmux-workspaces")
}

/// Workspace names become registry filenames and reach `docker rm -f` /
/// `remove_dir_all` via the stored record. Constrain them to a strict
/// allowlist so a crafted name (absolute path, `..`, separators) cannot
/// escape the registry dir. Kept byte-identical to the Python driver's
/// `_WORKSPACE_NAME_RE`.
pub fn validate_name(name: &str) -> Result<()> {
    let ok = !name.is_empty()
        && name != "."
        && name != ".."
        && name
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '.' || c == '-');
    if ok {
        Ok(())
    } else {
        Err(Error::other(format!(
            "invalid workspace name {name:?}: must match [A-Za-z0-9_.-]+ and not be '.' or '..'"
        )))
    }
}

pub fn record_path(name: &str) -> Result<PathBuf> {
    validate_name(name)?;
    Ok(registry_dir().join(format!("{name}.json")))
}

pub fn save(record: &WorkspaceRecord) -> Result<()> {
    let path = record_path(&record.name)?;
    fs::create_dir_all(registry_dir())?;
    fs::write(&path, serde_json::to_vec_pretty(record)?)?;
    Ok(())
}

pub fn load(name: &str) -> Result<WorkspaceRecord> {
    let path = record_path(name)?;
    let bytes = fs::read(&path)?;
    let record: WorkspaceRecord = serde_json::from_slice(&bytes)?;
    // Defense in depth: a record's own name must match the one requested,
    // so a swapped or planted file can't redirect the caller's intent.
    if record.name != name {
        return Err(Error::other(format!(
            "workspace record at {} has name {:?}, expected {name:?}",
            path.display(),
            record.name
        )));
    }
    Ok(record)
}

pub fn forget(name: &str) -> Result<()> {
    let path = record_path(name)?;
    match fs::remove_file(&path) {
        Ok(()) => Ok(()),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(e) => Err(e),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn validate_name_accepts_generated_and_simple_names() {
        for n in ["itws-deadbeef", "abc", "a.b-c_d", "Workspace1"] {
            assert!(validate_name(n).is_ok(), "{n} should be valid");
        }
    }

    #[test]
    fn validate_name_rejects_traversal_and_separators() {
        for n in ["", ".", "..", "../etc", "a/b", "/abs/path", "a b", "name$"] {
            assert!(validate_name(n).is_err(), "{n:?} should be rejected");
        }
    }

    #[test]
    fn record_path_errors_on_bad_name_and_stays_in_registry() {
        assert!(record_path("..").is_err());
        assert!(record_path("../escape").is_err());
        let p = record_path("ok").unwrap();
        assert!(p.starts_with(registry_dir()));
        assert!(p.ends_with("ok.json"));
    }
}
