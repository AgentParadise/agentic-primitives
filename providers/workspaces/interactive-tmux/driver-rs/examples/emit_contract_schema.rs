//! Regenerates the JSON Schema files under `docs/contract/` from the serde
//! structs in `src/run/contract.rs` (single source of truth: the Rust
//! types, via `schemars`).
//!
//! Run after changing the contract:
//! ```sh
//! cargo run --example emit_contract_schema
//! ```
//! then `git diff docs/contract/` to review the schema drift, and commit
//! the regenerated files alongside the struct change.

use std::fs;
use std::path::Path;

use schemars::schema_for;

use itmux::run::contract::{AgentRunEvent, AgentRunResult, AgentRunSpec};

fn write_schema<T: schemars::JsonSchema>(dir: &Path, file_name: &str) {
    let schema = schema_for!(T);
    let json = serde_json::to_string_pretty(&schema).expect("schema serializes");
    let path = dir.join(file_name);
    fs::write(&path, format!("{json}\n")).unwrap_or_else(|e| panic!("write {path:?}: {e}"));
    println!("wrote {}", path.display());
}

fn main() {
    let dir = Path::new(env!("CARGO_MANIFEST_DIR")).join("docs/contract");
    fs::create_dir_all(&dir).expect("create docs/contract");

    write_schema::<AgentRunSpec>(&dir, "agent-run-spec.schema.json");
    write_schema::<AgentRunResult>(&dir, "agent-run-result.schema.json");
    write_schema::<AgentRunEvent>(&dir, "agent-run-event.schema.json");
}
