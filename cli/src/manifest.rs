//! Manifest module for tracking installed primitives
//!
//! The manifest allows smart sync - only updating managed files while
//! preserving locally created files.

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs;
use std::path::Path;

/// Name of the manifest file
pub const MANIFEST_FILENAME: &str = ".agentic-manifest.yaml";

/// Manifest tracking installed primitives
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct AgenticManifest {
    /// Schema version for future compatibility
    pub version: String,

    /// When this manifest was created/updated
    pub updated_at: DateTime<Utc>,

    /// Source repository or identifier
    #[serde(skip_serializing_if = "Option::is_none")]
    pub source: Option<String>,

    /// Provider this manifest is for
    pub provider: String,

    /// Primitives tracked by this manifest
    #[serde(default)]
    pub primitives: Vec<ManifestPrimitive>,
}

/// A single primitive entry in the manifest
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ManifestPrimitive {
    /// Primitive ID (e.g., "qa/review")
    pub id: String,

    /// Primitive kind (command, meta-prompt, agent, skill)
    pub kind: String,

    /// Version number
    pub version: u32,

    /// Content hash for change detection
    pub hash: String,

    /// Files installed for this primitive (relative paths)
    pub files: Vec<String>,
}

impl AgenticManifest {
    /// Create a new empty manifest
    pub fn new(provider: &str) -> Self {
        Self {
            version: "1.0".to_string(),
            updated_at: Utc::now(),
            source: None,
            provider: provider.to_string(),
            primitives: Vec::new(),
        }
    }

    /// Load manifest from a directory
    pub fn load(dir: &Path) -> Result<Option<Self>, ManifestError> {
        let manifest_path = dir.join(MANIFEST_FILENAME);

        if !manifest_path.exists() {
            return Ok(None);
        }

        let content = fs::read_to_string(&manifest_path).map_err(|e| ManifestError::IoError {
            path: manifest_path.clone(),
            source: e,
        })?;

        let manifest: Self =
            serde_yaml::from_str(&content).map_err(|e| ManifestError::ParseError {
                path: manifest_path,
                source: e,
            })?;

        Ok(Some(manifest))
    }

    /// Save manifest to a directory
    pub fn save(&self, dir: &Path) -> Result<(), ManifestError> {
        let manifest_path = dir.join(MANIFEST_FILENAME);

        let content =
            serde_yaml::to_string(self).map_err(|e| ManifestError::SerializeError { source: e })?;

        fs::write(&manifest_path, content).map_err(|e| ManifestError::IoError {
            path: manifest_path,
            source: e,
        })?;

        Ok(())
    }

    /// Add or update a primitive in the manifest
    pub fn upsert_primitive(&mut self, primitive: ManifestPrimitive) {
        if let Some(existing) = self.primitives.iter_mut().find(|p| p.id == primitive.id) {
            *existing = primitive;
        } else {
            self.primitives.push(primitive);
        }
        self.updated_at = Utc::now();
    }

    /// Get all files managed by this manifest
    pub fn managed_files(&self) -> Vec<String> {
        self.primitives
            .iter()
            .flat_map(|p| p.files.iter().cloned())
            .collect()
    }

    /// Check if a file is managed by this manifest
    pub fn is_managed(&self, file_path: &str) -> bool {
        self.primitives
            .iter()
            .any(|p| p.files.iter().any(|f| f == file_path))
    }

    /// Get primitive by ID
    pub fn get_primitive(&self, id: &str) -> Option<&ManifestPrimitive> {
        self.primitives.iter().find(|p| p.id == id)
    }
}

/// Result of comparing two manifests
#[derive(Debug, Default)]
pub struct ManifestDiff {
    /// Primitives that are new (not in target)
    pub added: Vec<ManifestPrimitive>,

    /// Primitives that changed (hash or version different)
    pub updated: Vec<(ManifestPrimitive, ManifestPrimitive)>, // (old, new)

    /// Primitives that were removed (in target but not in source)
    pub removed: Vec<ManifestPrimitive>,

    /// Primitives that are unchanged
    pub unchanged: Vec<ManifestPrimitive>,
}

impl ManifestDiff {
    /// Compare source manifest to target manifest
    ///
    /// - `source`: The new manifest (from build)
    /// - `target`: The existing manifest (in install location)
    pub fn compare(source: &AgenticManifest, target: Option<&AgenticManifest>) -> Self {
        let mut diff = ManifestDiff::default();

        // Build lookup map for target primitives
        let target_map: HashMap<&str, &ManifestPrimitive> = target
            .map(|t| t.primitives.iter().map(|p| (p.id.as_str(), p)).collect())
            .unwrap_or_default();

        // Check each source primitive
        for src_prim in &source.primitives {
            match target_map.get(src_prim.id.as_str()) {
                None => {
                    // New primitive
                    diff.added.push(src_prim.clone());
                }
                Some(tgt_prim) => {
                    if src_prim.hash != tgt_prim.hash || src_prim.version != tgt_prim.version {
                        // Updated primitive
                        diff.updated.push(((*tgt_prim).clone(), src_prim.clone()));
                    } else {
                        // Unchanged
                        diff.unchanged.push(src_prim.clone());
                    }
                }
            }
        }

        // Check for removed primitives (in target but not in source)
        if let Some(target) = target {
            let source_ids: std::collections::HashSet<&str> =
                source.primitives.iter().map(|p| p.id.as_str()).collect();

            for tgt_prim in &target.primitives {
                if !source_ids.contains(tgt_prim.id.as_str()) {
                    diff.removed.push(tgt_prim.clone());
                }
            }
        }

        diff
    }

    /// Check if there are any changes
    pub fn has_changes(&self) -> bool {
        !self.added.is_empty() || !self.updated.is_empty() || !self.removed.is_empty()
    }

    /// Get all files that need to be installed
    pub fn files_to_install(&self) -> Vec<String> {
        let mut files = Vec::new();

        for prim in &self.added {
            files.extend(prim.files.iter().cloned());
        }

        for (_, new_prim) in &self.updated {
            files.extend(new_prim.files.iter().cloned());
        }

        files
    }

    /// Get all files that should be removed
    pub fn files_to_remove(&self) -> Vec<String> {
        self.removed
            .iter()
            .flat_map(|p| p.files.iter().cloned())
            .collect()
    }
}

/// Errors that can occur during manifest operations
#[derive(Debug)]
pub enum ManifestError {
    IoError {
        path: std::path::PathBuf,
        source: std::io::Error,
    },
    ParseError {
        path: std::path::PathBuf,
        source: serde_yaml::Error,
    },
    SerializeError {
        source: serde_yaml::Error,
    },
}

impl std::fmt::Display for ManifestError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ManifestError::IoError { path, source } => {
                write!(f, "Failed to read/write {}: {}", path.display(), source)
            }
            ManifestError::ParseError { path, source } => {
                write!(f, "Failed to parse {}: {}", path.display(), source)
            }
            ManifestError::SerializeError { source } => {
                write!(f, "Failed to serialize manifest: {source}")
            }
        }
    }
}

impl std::error::Error for ManifestError {}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    fn create_test_primitive(id: &str, version: u32, hash: &str) -> ManifestPrimitive {
        ManifestPrimitive {
            id: id.to_string(),
            kind: "command".to_string(),
            version,
            hash: hash.to_string(),
            files: vec![format!("commands/{}.md", id.replace('/', "-"))],
        }
    }

    #[test]
    fn test_manifest_new() {
        let manifest = AgenticManifest::new("claude");

        assert_eq!(manifest.version, "1.0");
        assert_eq!(manifest.provider, "claude");
        assert!(manifest.primitives.is_empty());
    }

    #[test]
    fn test_manifest_save_and_load() {
        let temp_dir = TempDir::new().unwrap();

        let mut manifest = AgenticManifest::new("claude");
        manifest.upsert_primitive(create_test_primitive("qa/review", 1, "hash123"));

        // Save
        manifest.save(temp_dir.path()).unwrap();

        // Load
        let loaded = AgenticManifest::load(temp_dir.path()).unwrap();
        assert!(loaded.is_some());

        let loaded = loaded.unwrap();
        assert_eq!(loaded.provider, "claude");
        assert_eq!(loaded.primitives.len(), 1);
        assert_eq!(loaded.primitives[0].id, "qa/review");
    }

    #[test]
    fn test_manifest_load_not_exists() {
        let temp_dir = TempDir::new().unwrap();

        let loaded = AgenticManifest::load(temp_dir.path()).unwrap();
        assert!(loaded.is_none());
    }

    #[test]
    fn test_manifest_upsert_new() {
        let mut manifest = AgenticManifest::new("claude");

        manifest.upsert_primitive(create_test_primitive("qa/review", 1, "hash123"));

        assert_eq!(manifest.primitives.len(), 1);
        assert_eq!(manifest.primitives[0].version, 1);
    }

    #[test]
    fn test_manifest_upsert_update() {
        let mut manifest = AgenticManifest::new("claude");

        manifest.upsert_primitive(create_test_primitive("qa/review", 1, "hash123"));
        manifest.upsert_primitive(create_test_primitive("qa/review", 2, "hash456"));

        assert_eq!(manifest.primitives.len(), 1);
        assert_eq!(manifest.primitives[0].version, 2);
        assert_eq!(manifest.primitives[0].hash, "hash456");
    }

    #[test]
    fn test_manifest_managed_files() {
        let mut manifest = AgenticManifest::new("claude");

        manifest.upsert_primitive(ManifestPrimitive {
            id: "qa/review".to_string(),
            kind: "command".to_string(),
            version: 1,
            hash: "hash123".to_string(),
            files: vec!["commands/review.md".to_string()],
        });

        manifest.upsert_primitive(ManifestPrimitive {
            id: "qa/pre-commit".to_string(),
            kind: "command".to_string(),
            version: 1,
            hash: "hash456".to_string(),
            files: vec!["commands/pre-commit.md".to_string()],
        });

        let managed = manifest.managed_files();
        assert_eq!(managed.len(), 2);
        assert!(managed.contains(&"commands/review.md".to_string()));
        assert!(managed.contains(&"commands/pre-commit.md".to_string()));
    }

    #[test]
    fn test_manifest_is_managed() {
        let mut manifest = AgenticManifest::new("claude");

        manifest.upsert_primitive(ManifestPrimitive {
            id: "qa/review".to_string(),
            kind: "command".to_string(),
            version: 1,
            hash: "hash123".to_string(),
            files: vec!["commands/review.md".to_string()],
        });

        assert!(manifest.is_managed("commands/review.md"));
        assert!(!manifest.is_managed("commands/doc-sync.md"));
        assert!(!manifest.is_managed("commands/prime.md"));
    }

    #[test]
    fn test_diff_no_target() {
        let source = {
            let mut m = AgenticManifest::new("claude");
            m.upsert_primitive(create_test_primitive("qa/review", 1, "hash123"));
            m.upsert_primitive(create_test_primitive("qa/pre-commit", 1, "hash456"));
            m
        };

        let diff = ManifestDiff::compare(&source, None);

        assert_eq!(diff.added.len(), 2);
        assert!(diff.updated.is_empty());
        assert!(diff.removed.is_empty());
        assert!(diff.unchanged.is_empty());
    }

    #[test]
    fn test_diff_no_changes() {
        let source = {
            let mut m = AgenticManifest::new("claude");
            m.upsert_primitive(create_test_primitive("qa/review", 1, "hash123"));
            m
        };

        let target = source.clone();

        let diff = ManifestDiff::compare(&source, Some(&target));

        assert!(diff.added.is_empty());
        assert!(diff.updated.is_empty());
        assert!(diff.removed.is_empty());
        assert_eq!(diff.unchanged.len(), 1);
        assert!(!diff.has_changes());
    }

    #[test]
    fn test_diff_new_primitive() {
        let source = {
            let mut m = AgenticManifest::new("claude");
            m.upsert_primitive(create_test_primitive("qa/review", 1, "hash123"));
            m.upsert_primitive(create_test_primitive("qa/new-command", 1, "hash789"));
            m
        };

        let target = {
            let mut m = AgenticManifest::new("claude");
            m.upsert_primitive(create_test_primitive("qa/review", 1, "hash123"));
            m
        };

        let diff = ManifestDiff::compare(&source, Some(&target));

        assert_eq!(diff.added.len(), 1);
        assert_eq!(diff.added[0].id, "qa/new-command");
        assert!(diff.updated.is_empty());
        assert!(diff.removed.is_empty());
        assert_eq!(diff.unchanged.len(), 1);
        assert!(diff.has_changes());
    }

    #[test]
    fn test_diff_updated_primitive() {
        let source = {
            let mut m = AgenticManifest::new("claude");
            m.upsert_primitive(create_test_primitive("qa/review", 2, "newhash"));
            m
        };

        let target = {
            let mut m = AgenticManifest::new("claude");
            m.upsert_primitive(create_test_primitive("qa/review", 1, "oldhash"));
            m
        };

        let diff = ManifestDiff::compare(&source, Some(&target));

        assert!(diff.added.is_empty());
        assert_eq!(diff.updated.len(), 1);
        assert_eq!(diff.updated[0].0.version, 1); // old
        assert_eq!(diff.updated[0].1.version, 2); // new
        assert!(diff.removed.is_empty());
        assert!(diff.has_changes());
    }

    #[test]
    fn test_diff_removed_primitive() {
        let source = {
            let mut m = AgenticManifest::new("claude");
            m.upsert_primitive(create_test_primitive("qa/review", 1, "hash123"));
            m
        };

        let target = {
            let mut m = AgenticManifest::new("claude");
            m.upsert_primitive(create_test_primitive("qa/review", 1, "hash123"));
            m.upsert_primitive(create_test_primitive("qa/old-command", 1, "hash456"));
            m
        };

        let diff = ManifestDiff::compare(&source, Some(&target));

        assert!(diff.added.is_empty());
        assert!(diff.updated.is_empty());
        assert_eq!(diff.removed.len(), 1);
        assert_eq!(diff.removed[0].id, "qa/old-command");
        assert!(diff.has_changes());
    }

    #[test]
    fn test_diff_complex_scenario() {
        // Source has: review (v2), new-cmd (v1)
        // Target has: review (v1), old-cmd (v1)
        // Expected: review updated, new-cmd added, old-cmd removed

        let source = {
            let mut m = AgenticManifest::new("claude");
            m.upsert_primitive(create_test_primitive("qa/review", 2, "newhash"));
            m.upsert_primitive(create_test_primitive("qa/new-cmd", 1, "hash789"));
            m
        };

        let target = {
            let mut m = AgenticManifest::new("claude");
            m.upsert_primitive(create_test_primitive("qa/review", 1, "oldhash"));
            m.upsert_primitive(create_test_primitive("qa/old-cmd", 1, "hash456"));
            m
        };

        let diff = ManifestDiff::compare(&source, Some(&target));

        assert_eq!(diff.added.len(), 1);
        assert_eq!(diff.added[0].id, "qa/new-cmd");

        assert_eq!(diff.updated.len(), 1);
        assert_eq!(diff.updated[0].1.id, "qa/review");

        assert_eq!(diff.removed.len(), 1);
        assert_eq!(diff.removed[0].id, "qa/old-cmd");

        assert!(diff.has_changes());
    }

    #[test]
    fn test_diff_files_to_install() {
        let source = {
            let mut m = AgenticManifest::new("claude");
            m.upsert_primitive(ManifestPrimitive {
                id: "qa/new-cmd".to_string(),
                kind: "command".to_string(),
                version: 1,
                hash: "hash123".to_string(),
                files: vec!["commands/new-cmd.md".to_string()],
            });
            m.upsert_primitive(ManifestPrimitive {
                id: "qa/updated".to_string(),
                kind: "command".to_string(),
                version: 2,
                hash: "newhash".to_string(),
                files: vec!["commands/updated.md".to_string()],
            });
            m
        };

        let target = {
            let mut m = AgenticManifest::new("claude");
            m.upsert_primitive(ManifestPrimitive {
                id: "qa/updated".to_string(),
                kind: "command".to_string(),
                version: 1,
                hash: "oldhash".to_string(),
                files: vec!["commands/updated.md".to_string()],
            });
            m
        };

        let diff = ManifestDiff::compare(&source, Some(&target));
        let files_to_install = diff.files_to_install();

        assert_eq!(files_to_install.len(), 2);
        assert!(files_to_install.contains(&"commands/new-cmd.md".to_string()));
        assert!(files_to_install.contains(&"commands/updated.md".to_string()));
    }

    #[test]
    fn test_diff_files_to_remove() {
        let source = AgenticManifest::new("claude");

        let target = {
            let mut m = AgenticManifest::new("claude");
            m.upsert_primitive(ManifestPrimitive {
                id: "qa/old-cmd".to_string(),
                kind: "command".to_string(),
                version: 1,
                hash: "hash123".to_string(),
                files: vec![
                    "commands/old-cmd.md".to_string(),
                    "commands/old-cmd-helper.md".to_string(),
                ],
            });
            m
        };

        let diff = ManifestDiff::compare(&source, Some(&target));
        let files_to_remove = diff.files_to_remove();

        assert_eq!(files_to_remove.len(), 2);
        assert!(files_to_remove.contains(&"commands/old-cmd.md".to_string()));
        assert!(files_to_remove.contains(&"commands/old-cmd-helper.md".to_string()));
    }

    #[test]
    fn test_local_files_not_touched() {
        // This test verifies that local files (not in manifest) are not affected

        let source = {
            let mut m = AgenticManifest::new("claude");
            m.upsert_primitive(ManifestPrimitive {
                id: "qa/review".to_string(),
                kind: "command".to_string(),
                version: 1,
                hash: "hash123".to_string(),
                files: vec!["commands/review.md".to_string()],
            });
            m
        };

        let target = source.clone();

        // Local files that should NOT be in the diff
        let local_files = vec!["commands/doc-sync.md", "commands/prime.md"];

        let diff = ManifestDiff::compare(&source, Some(&target));

        // No changes since source == target
        assert!(!diff.has_changes());

        // Verify local files are not managed
        assert!(!source.is_managed("commands/doc-sync.md"));
        assert!(!source.is_managed("commands/prime.md"));

        // Files to install should not include local files
        let files_to_install = diff.files_to_install();
        for local_file in &local_files {
            assert!(
                !files_to_install.contains(&local_file.to_string()),
                "Local file {local_file} should not be in files to install"
            );
        }
    }
}
