//! Host-side driver for the `interactive-tmux` workspace provider — Rust port.
//!
//! This crate is a parity port of `providers/workspaces/interactive-tmux/driver/
//! interactive_tmux.py`. The protocol, per-agent matrix (EXP-01..04, EXP-05a,
//! `experiments/ANALYTICS.md` §4), and structured-result shapes
//! (`AwaitResult` mirrors Python's `ExecuteResult`) are preserved byte-for-byte
//! so the two implementations can share the on-disk workspace registry at
//! `/tmp/interactive-tmux-workspaces/<name>.json` and round-trip with `smoke.sh`.
//!
//! Five public primitives (matching the EXP-05 contract):
//!
//! ```text
//! Workspace::start(opts)         -> Workspace
//!   ws.send_message(agent, text) -> ()
//!   ws.await_completion(...)     -> AwaitResult
//!   ws.capture_response(agent)   -> String
//!   ws.stop()                    -> ()
//! ```
//!
//! Plus a sixth `exec` primitive that shells out to `docker exec` for ad-hoc
//! commands in the container (used by the smoke harness to verify the
//! container is alive without going through tmux).

pub mod adapter;
pub mod auth;
pub mod registry;
pub mod result;
pub mod tmux;
pub mod workspace;

pub use adapter::{Agent, AGENTS};
pub use result::AwaitResult;
pub use workspace::{StartOptions, Workspace};
