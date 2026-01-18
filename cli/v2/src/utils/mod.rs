//! Shared utilities for the CLI

pub mod pattern;

pub use pattern::{matches_only_patterns, parse_only_patterns, warn_if_empty_match};
