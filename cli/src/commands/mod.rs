//! CLI command implementations

pub mod build; // Build provider outputs
pub mod build_v2; // V2 primitives discovery
pub mod config_cmd; // Per-project configuration management
pub mod init;
pub mod inspect;
pub mod install; // Install to provider dirs
pub mod list;
pub mod migrate;
pub mod new;
pub mod test_hook; // Test hook locally
pub mod validate;
pub mod version;
