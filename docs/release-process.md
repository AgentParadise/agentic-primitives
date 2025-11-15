# Release Process

## Preparing a Release

1. **Update version in Cargo.toml**
   ```bash
   # Edit cli/Cargo.toml
   version = "X.Y.Z"
   ```

2. **Update CHANGELOG.md**
   - Add section for new version
   - List all changes (feat, fix, docs, etc.)
   - Follow Keep a Changelog format

3. **Commit changes**
   ```bash
   git add cli/Cargo.toml CHANGELOG.md
   git commit -m "chore(release): prepare vX.Y.Z release"
   git push origin main
   ```

4. **Create and push tag**
   ```bash
   git tag -a vX.Y.Z -m "Release vX.Y.Z"
   git push origin vX.Y.Z
   ```

5. **Wait for CI**
   - Release workflow builds binaries
   - GitHub Release is created automatically
   - Verify all binaries are attached

## Versioning Strategy

Follow [Semantic Versioning](https://semver.org/):
- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes

## Pre-Releases

For testing release workflow:
- Use `-alpha`, `-beta`, `-rc.N` suffixes
- Example: `v1.1.0-rc.1`
- Marked as pre-release automatically

## Binary Verification

Users can verify downloads:
```bash
# Download binary and checksum
curl -LO https://github.com/neural/agentic-primitives/releases/download/v1.0.0/agentic-p-linux-x64
curl -LO https://github.com/neural/agentic-primitives/releases/download/v1.0.0/agentic-p-linux-x64.sha256

# Verify
shasum -a 256 -c agentic-p-linux-x64.sha256
```

