# Installation

## Quick Install

### Linux / macOS

```bash
curl -fsSL https://raw.githubusercontent.com/neural/agentic-primitives/main/scripts/install.sh | sh
```

### Windows (Git Bash or WSL)

```bash
curl -fsSL https://raw.githubusercontent.com/neural/agentic-primitives/main/scripts/install.sh | sh
```

## Install Specific Version

```bash
curl -fsSL https://raw.githubusercontent.com/neural/agentic-primitives/main/scripts/install.sh | sh -s v1.0.0
```

## Custom Install Location

```bash
# Install to /opt/bin
curl -fsSL https://raw.githubusercontent.com/neural/agentic-primitives/main/scripts/install.sh | INSTALL_DIR=/opt/bin sh

# Install to custom user directory
curl -fsSL https://raw.githubusercontent.com/neural/agentic-primitives/main/scripts/install.sh | INSTALL_DIR=$HOME/bin sh
```

## Manual Installation

1. Download binary for your platform from [Releases](https://github.com/neural/agentic-primitives/releases)
2. Verify checksum:

```bash
shasum -a 256 -c agentic-p-linux-x64.sha256
```

3. Make executable and move to PATH:

```bash
chmod +x agentic-p-linux-x64
sudo mv agentic-p-linux-x64 /usr/local/bin/agentic-p
```

## Verify Installation

```bash
agentic-p --version
agentic-p --help
```

## Troubleshooting

### "command not found: agentic-p"

The install directory is not in your PATH. Add it manually:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Or restart your shell to load the updated PATH from your rc file.

### Permission denied

If installing to a system directory like `/usr/local/bin`, you may need sudo:

```bash
curl -fsSL https://raw.githubusercontent.com/neural/agentic-primitives/main/scripts/install.sh | sudo sh
```

Or install to a user directory (default):

```bash
# Installs to ~/.local/bin (no sudo needed)
curl -fsSL https://raw.githubusercontent.com/neural/agentic-primitives/main/scripts/install.sh | sh
```

### macOS: "cannot be opened because the developer cannot be verified"

Allow the binary in System Preferences → Security & Privacy, or:

```bash
xattr -d com.apple.quarantine ~/.local/bin/agentic-p
```

### Checksum verification failed

The download may be corrupted. Try again:

```bash
rm -rf /tmp/agentic-p*
curl -fsSL https://raw.githubusercontent.com/neural/agentic-primitives/main/scripts/install.sh | sh
```

## Supported Platforms

The installation script automatically detects your platform and downloads the appropriate binary:

- **Linux**: x64, ARM64
- **macOS**: Intel (x64), Apple Silicon (ARM64)
- **Windows**: x64 (via Git Bash or WSL)

## Requirements

- `curl` or `wget` for downloading
- `shasum` or `sha256sum` for checksum verification
- Bash-compatible shell

## Environment Variables

The installation script supports the following environment variables:

- `INSTALL_DIR`: Custom installation directory (default: `$HOME/.local/bin`)

Example:

```bash
INSTALL_DIR=/usr/local/bin curl -fsSL https://raw.githubusercontent.com/neural/agentic-primitives/main/scripts/install.sh | sudo sh
```

## Uninstallation

To uninstall, simply remove the binary:

```bash
rm ~/.local/bin/agentic-p
```

If you want to remove the PATH configuration, edit your shell rc file (e.g., `~/.bashrc`, `~/.zshrc`) and remove the line:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

---

## Installing Primitives

After the CLI is installed, you can build and install primitives to your project or globally.

### Build & Install All Primitives

```bash
# Build all primitives for Claude
agentic-p build --provider claude

# Install to current project
agentic-p install --provider claude

# Install globally (~/.claude/)
agentic-p install --provider claude --global
```

### Selective Installation (--only)

Use the `--only` flag to install only the primitives you need:

```bash
# Install only QA-related primitives
agentic-p build --provider claude --only "qa/*"
agentic-p install --provider claude --only "qa/*"

# Install specific primitives (comma-separated patterns)
agentic-p build --provider claude --only "qa/review,devops/commit,hooks/*"
agentic-p install --provider claude --only "qa/review,devops/commit,hooks/*"
```

### Pattern Syntax

The `--only` flag accepts comma-separated glob patterns:

| Pattern | Description | Example Matches |
|---------|-------------|-----------------|
| `qa/*` | All primitives in `qa/` category | `qa/review`, `qa/pre-commit-qa` |
| `qa/review` | Exact match | `qa/review` only |
| `devops/*` | All devops primitives | `devops/commit`, `devops/push` |
| `*/commit` | Any primitive ending in `commit` | `devops/commit`, `workflow/commit` |
| `hooks/*` | All hooks | All hook primitives |

### Dry Run

Preview what would be installed without making changes:

```bash
agentic-p install --provider claude --only "qa/*" --dry-run --verbose
```

