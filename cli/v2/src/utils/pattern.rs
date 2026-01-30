//! Pattern matching utilities for --only flag filtering

use anyhow::{bail, Result};
use colored::Colorize;
use glob::Pattern;

/// Parse comma-separated glob patterns from --only flag
/// Returns an error if any pattern is invalid
pub fn parse_only_patterns(only: &str) -> Result<Vec<Pattern>> {
    let mut patterns = Vec::new();
    let mut invalid_patterns = Vec::new();

    for p in only.split(',').map(|p| p.trim()).filter(|p| !p.is_empty()) {
        match Pattern::new(p) {
            Ok(pattern) => patterns.push(pattern),
            Err(_) => invalid_patterns.push(p.to_string()),
        }
    }

    if !invalid_patterns.is_empty() {
        bail!(
            "Invalid glob pattern(s) in --only: {}",
            invalid_patterns.join(", ")
        );
    }

    Ok(patterns)
}

/// Check if a primitive ID matches any of the --only patterns
/// Returns true if no patterns are provided (include all)
pub fn matches_only_patterns(primitive_id: &str, patterns: &[Pattern]) -> bool {
    if patterns.is_empty() {
        return true; // No filter = include all
    }
    patterns.iter().any(|p| p.matches(primitive_id))
}

/// Warn if --only filter resulted in no matches
pub fn warn_if_empty_match(count: usize, patterns: &[Pattern], context: &str) {
    if !patterns.is_empty() && count == 0 {
        eprintln!(
            "{} --only filter matched 0 {} (patterns: {})",
            "Warning:".yellow().bold(),
            context,
            patterns
                .iter()
                .map(|p| p.as_str())
                .collect::<Vec<_>>()
                .join(", ")
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_only_patterns_valid() {
        let patterns = parse_only_patterns("qa/*,devops/commit").unwrap();
        assert_eq!(patterns.len(), 2);
    }

    #[test]
    fn test_parse_only_patterns_single() {
        let patterns = parse_only_patterns("qa/*").unwrap();
        assert_eq!(patterns.len(), 1);
    }

    #[test]
    fn test_parse_only_patterns_with_spaces() {
        let patterns = parse_only_patterns("qa/* , devops/commit , docs/*").unwrap();
        assert_eq!(patterns.len(), 3);
    }

    #[test]
    fn test_parse_only_patterns_empty_parts() {
        let patterns = parse_only_patterns("qa/*,,devops/commit,").unwrap();
        assert_eq!(patterns.len(), 2);
    }

    #[test]
    fn test_parse_only_patterns_invalid() {
        let result = parse_only_patterns("qa/*,[unclosed");
        assert!(result.is_err());
        let err = result.unwrap_err().to_string();
        assert!(err.contains("Invalid glob pattern"));
        assert!(err.contains("[unclosed"));
    }

    #[test]
    fn test_parse_only_patterns_multiple_invalid() {
        let result = parse_only_patterns("[bad1,[bad2");
        assert!(result.is_err());
        let err = result.unwrap_err().to_string();
        assert!(err.contains("[bad1"));
        assert!(err.contains("[bad2"));
    }

    #[test]
    fn test_matches_only_patterns_empty() {
        // Empty patterns = match everything
        assert!(matches_only_patterns("anything", &[]));
    }

    #[test]
    fn test_matches_only_patterns_exact() {
        let patterns = parse_only_patterns("qa/review").unwrap();
        assert!(matches_only_patterns("qa/review", &patterns));
        assert!(!matches_only_patterns("qa/other", &patterns));
    }

    #[test]
    fn test_matches_only_patterns_wildcard() {
        let patterns = parse_only_patterns("qa/*").unwrap();
        assert!(matches_only_patterns("qa/review", &patterns));
        assert!(matches_only_patterns("qa/test", &patterns));
        assert!(!matches_only_patterns("devops/commit", &patterns));
    }

    #[test]
    fn test_matches_only_patterns_multiple() {
        let patterns = parse_only_patterns("qa/*,devops/commit").unwrap();
        assert!(matches_only_patterns("qa/review", &patterns));
        assert!(matches_only_patterns("devops/commit", &patterns));
        assert!(!matches_only_patterns("docs/readme", &patterns));
    }

    #[test]
    fn test_matches_only_patterns_double_wildcard() {
        let patterns = parse_only_patterns("**/review").unwrap();
        assert!(matches_only_patterns("qa/review", &patterns));
        assert!(matches_only_patterns("code/review", &patterns));
        assert!(!matches_only_patterns("qa/test", &patterns));
    }
}
