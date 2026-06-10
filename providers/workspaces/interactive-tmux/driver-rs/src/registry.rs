//! On-disk workspace registry shared with the Python driver.
//!
//! Schema is byte-identical to `_save_workspace`/`_load_workspace` in
//! `interactive_tmux.py` so a Rust `start` and a Python `stop` round-trip
//! (and vice versa). Files live at
//! `/tmp/interactive-tmux-workspaces/<name>.json`.

use std::env;
use std::fs;
use std::io::Result;
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

pub fn record_path(name: &str) -> PathBuf {
    registry_dir().join(format!("{name}.json"))
}

pub fn save(record: &WorkspaceRecord) -> Result<()> {
    let dir = registry_dir();
    fs::create_dir_all(&dir)?;
    let path = dir.join(format!("{}.json", record.name));
    fs::write(&path, serde_json::to_vec_pretty(record)?)?;
    Ok(())
}

pub fn load(name: &str) -> Result<WorkspaceRecord> {
    let path = record_path(name);
    let bytes = fs::read(&path)?;
    let record: WorkspaceRecord = serde_json::from_slice(&bytes)?;
    Ok(record)
}

pub fn forget(name: &str) -> Result<()> {
    let path = record_path(name);
    match fs::remove_file(&path) {
        Ok(()) => Ok(()),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(e) => Err(e),
    }
}
