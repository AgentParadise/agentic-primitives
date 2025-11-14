//! CLI command implementations

pub mod init;
pub mod inspect;
pub mod list;
pub mod migrate;
pub mod new;
pub mod validate;
pub mod version;

// TODO: Wave 9 commands
pub mod build; // Build provider outputs
pub mod install; // Install to provider dirs
                 // pub mod test_hook;    // Test hook locally
