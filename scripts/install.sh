#!/bin/sh
# Installation script for agentic-primitives CLI
# Supports Linux, macOS, and Windows (Git Bash/WSL)

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
REPO="neural/agentic-primitives"
BINARY_NAME="agentic-p"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/bin}"
GITHUB_API="https://api.github.com/repos/${REPO}"
GITHUB_DOWNLOAD="https://github.com/${REPO}/releases/download"

# Helper functions
info() {
    printf "${BLUE}ℹ${NC} %s\n" "$1"
}

success() {
    printf "${GREEN}✓${NC} %s\n" "$1"
}

warn() {
    printf "${YELLOW}⚠${NC} %s\n" "$1"
}

error() {
    printf "${RED}✗${NC} %s\n" "$1" >&2
    exit 1
}

# Detect platform (OS + architecture)
detect_platform() {
    local os=""
    local arch=""
    
    # Detect OS
    case "$(uname -s)" in
        Linux*)     os="linux" ;;
        Darwin*)    os="macos" ;;
        CYGWIN*|MINGW*|MSYS*) os="windows" ;;
        *)          error "Unsupported operating system: $(uname -s)" ;;
    esac
    
    # Detect architecture
    case "$(uname -m)" in
        x86_64|amd64)   arch="x64" ;;
        aarch64|arm64)  arch="arm64" ;;
        *)              error "Unsupported architecture: $(uname -m)" ;;
    esac
    
    echo "${os}-${arch}"
}

# Check for required tools
check_requirements() {
    # Check for download tool
    if command -v curl >/dev/null 2>&1; then
        DOWNLOAD_CMD="curl -fsSL"
    elif command -v wget >/dev/null 2>&1; then
        DOWNLOAD_CMD="wget -qO-"
    else
        error "curl or wget is required for installation"
    fi
    
    # Check for checksum tool
    if command -v shasum >/dev/null 2>&1; then
        CHECKSUM_CMD="shasum -a 256"
    elif command -v sha256sum >/dev/null 2>&1; then
        CHECKSUM_CMD="sha256sum"
    else
        error "shasum or sha256sum is required for checksum verification"
    fi
}

# Get latest release version from GitHub
get_latest_version() {
    info "Fetching latest version..."
    
    local latest_url="${GITHUB_API}/releases/latest"
    local version=""
    
    if command -v curl >/dev/null 2>&1; then
        version=$(curl -fsSL "$latest_url" | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')
    else
        version=$(wget -qO- "$latest_url" | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')
    fi
    
    if [ -z "$version" ]; then
        error "Failed to fetch latest version"
    fi
    
    echo "$version"
}

# Download binary and checksum
download_binary() {
    local version="$1"
    local platform="$2"
    local tmp_dir=$(mktemp -d)
    
    local binary_name="${BINARY_NAME}-${platform}"
    local download_url="${GITHUB_DOWNLOAD}/${version}/${binary_name}"
    local checksum_url="${download_url}.sha256"
    
    info "Downloading ${BINARY_NAME} ${version} for ${platform}..."
    
    # Download binary
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL -o "${tmp_dir}/${binary_name}" "$download_url" || error "Failed to download binary"
        curl -fsSL -o "${tmp_dir}/${binary_name}.sha256" "$checksum_url" || error "Failed to download checksum"
    else
        wget -qO "${tmp_dir}/${binary_name}" "$download_url" || error "Failed to download binary"
        wget -qO "${tmp_dir}/${binary_name}.sha256" "$checksum_url" || error "Failed to download checksum"
    fi
    
    success "Downloaded binary and checksum"
    
    # Verify checksum
    info "Verifying checksum..."
    (
        cd "$tmp_dir"
        if ! $CHECKSUM_CMD -c "${binary_name}.sha256" >/dev/null 2>&1; then
            error "Checksum verification failed"
        fi
    )
    success "Checksum verified"
    
    echo "$tmp_dir"
}

# Install binary to target directory
install_binary() {
    local tmp_dir="$1"
    local platform="$2"
    
    local binary_name="${BINARY_NAME}-${platform}"
    
    # Create install directory if it doesn't exist
    if [ ! -d "$INSTALL_DIR" ]; then
        info "Creating install directory: ${INSTALL_DIR}"
        mkdir -p "$INSTALL_DIR"
    fi
    
    # Make binary executable
    chmod +x "${tmp_dir}/${binary_name}"
    
    # Move binary to install directory
    info "Installing to ${INSTALL_DIR}/${BINARY_NAME}..."
    mv "${tmp_dir}/${binary_name}" "${INSTALL_DIR}/${BINARY_NAME}"
    
    success "Binary installed to ${INSTALL_DIR}/${BINARY_NAME}"
    
    # Clean up
    rm -rf "$tmp_dir"
}

# Configure PATH if needed
configure_path() {
    # Check if install directory is already in PATH
    case ":$PATH:" in
        *":${INSTALL_DIR}:"*)
            success "Install directory is already in PATH"
            return 0
            ;;
    esac
    
    warn "Install directory is not in PATH"
    
    # Determine shell rc file
    local shell_rc=""
    local shell_name=$(basename "$SHELL")
    
    case "$shell_name" in
        bash)
            if [ -f "$HOME/.bashrc" ]; then
                shell_rc="$HOME/.bashrc"
            elif [ -f "$HOME/.bash_profile" ]; then
                shell_rc="$HOME/.bash_profile"
            fi
            ;;
        zsh)
            shell_rc="$HOME/.zshrc"
            ;;
        fish)
            shell_rc="$HOME/.config/fish/config.fish"
            ;;
    esac
    
    if [ -n "$shell_rc" ]; then
        # Check if PATH export already exists
        if ! grep -q "export PATH=\"${INSTALL_DIR}:\$PATH\"" "$shell_rc" 2>/dev/null; then
            info "Adding ${INSTALL_DIR} to PATH in ${shell_rc}"
            echo "" >> "$shell_rc"
            echo "# Added by agentic-primitives installer" >> "$shell_rc"
            echo "export PATH=\"${INSTALL_DIR}:\$PATH\"" >> "$shell_rc"
            success "PATH configured in ${shell_rc}"
            echo ""
            warn "Please restart your shell or run: source ${shell_rc}"
        fi
    else
        echo ""
        warn "Could not detect shell rc file. Add this to your shell configuration:"
        echo "    export PATH=\"${INSTALL_DIR}:\$PATH\""
    fi
}

# Main installation flow
main() {
    echo ""
    info "agentic-primitives installer"
    echo ""
    
    # Check requirements
    check_requirements
    
    # Detect platform
    local platform=$(detect_platform)
    success "Detected platform: ${platform}"
    
    # Determine version to install
    local version="${1:-}"
    if [ -z "$version" ]; then
        version=$(get_latest_version)
        success "Latest version: ${version}"
    else
        info "Installing version: ${version}"
    fi
    
    # Download binary
    local tmp_dir=$(download_binary "$version" "$platform")
    
    # Install binary
    install_binary "$tmp_dir" "$platform"
    
    # Configure PATH
    configure_path
    
    # Verify installation
    echo ""
    if command -v "$BINARY_NAME" >/dev/null 2>&1; then
        success "Installation complete!"
        echo ""
        info "Verify with: ${BINARY_NAME} --version"
    else
        success "Installation complete!"
        echo ""
        warn "Binary installed but not found in PATH"
        info "Try running: ${INSTALL_DIR}/${BINARY_NAME} --version"
        info "Or restart your shell to update PATH"
    fi
    echo ""
}

# Run main function with all arguments
main "$@"

