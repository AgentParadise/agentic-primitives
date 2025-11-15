#!/usr/bin/env bash
set -euo pipefail

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source utilities
source "$SCRIPT_DIR/lib/detect.sh"
source "$SCRIPT_DIR/lib/utils.sh"

# Defaults
STACK="${STACK:-auto}"
PROVIDER="${PROVIDER:-claude}"
PRESET="${PRESET:-standard}"
INSTALL_HOOKS=false
DRY_RUN=false
VERBOSE=false

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --stack)
      STACK="$2"
      shift 2
      ;;
    --provider)
      PROVIDER="$2"
      shift 2
      ;;
    --preset)
      PRESET="$2"
      shift 2
      ;;
    --hooks)
      INSTALL_HOOKS=true
      shift
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --verbose)
      VERBOSE=true
      shift
      ;;
    --help)
      cat << EOF
Usage: bootstrap.sh [OPTIONS]

Options:
  --stack <name>      Override stack detection (python|typescript|react|nestjs|turbo|rust)
  --provider <name>   Default provider (claude|openai) [default: claude]
  --preset <level>    Primitive set (minimal|standard|full) [default: standard]
  --hooks             Install git hooks for pre-commit validation
  --dry-run           Preview actions without executing
  --verbose           Show detailed output
  --help              Show this help message

Examples:
  # Auto-detect stack, use defaults
  ./bootstrap.sh

  # Specify stack and provider
  ./bootstrap.sh --stack python --provider claude --preset full

  # Dry run to preview
  ./bootstrap.sh --dry-run
EOF
      exit 0
      ;;
    *)
      error "Unknown option: $1"
      ;;
  esac
done

# Export flags for run_cmd
export DRY_RUN VERBOSE

# Step 1: Ensure CLI is installed
ensure_cli() {
  if command -v agentic-p > /dev/null 2>&1; then
    log "✅ agentic-p CLI found"
  else
    log "Installing agentic-p CLI..."
    if [ "$DRY_RUN" = false ]; then
      curl -fsSL https://raw.githubusercontent.com/neural/agentic-primitives/main/scripts/install.sh | sh
    else
      info "[DRY RUN] Would install CLI"
    fi
  fi
}

# Step 2: Detect or use provided stack
detect_or_use_stack() {
  if [ "$STACK" = "auto" ]; then
    STACK=$(detect_stack)
    log "Detected stack: $STACK"
  else
    log "Using provided stack: $STACK"
  fi
  
  if [ "$STACK" = "unknown" ]; then
    error "Could not detect stack. Please specify with --stack <name>"
  fi
}

# Step 3: Initialize repository
init_repo() {
  if [ -f "primitives.config.yaml" ]; then
    log "✅ Repository already initialized"
  else
    log "Initializing agentic-primitives repository..."
    run_cmd "agentic-p init"
  fi
}

# Step 4: Install stack-specific primitives
install_primitives() {
  log "Installing $PRESET primitives for $STACK..."
  
  case "$STACK" in
    python)
      install_python_primitives
      ;;
    typescript)
      install_typescript_primitives
      ;;
    react)
      install_react_primitives
      ;;
    nestjs)
      install_nestjs_primitives
      ;;
    turborepo)
      install_turborepo_primitives
      ;;
    rust)
      install_rust_primitives
      ;;
    *)
      warn "No primitives defined for stack: $STACK"
      ;;
  esac
}

install_python_primitives() {
  case "$PRESET" in
    minimal)
      run_cmd "agentic-p new prompt agent python/python-pro"
      ;;
    standard)
      run_cmd "agentic-p new prompt agent python/python-pro"
      run_cmd "agentic-p new command python/refactor-code"
      run_cmd "agentic-p new command python/write-tests"
      ;;
    full)
      run_cmd "agentic-p new prompt agent python/python-pro"
      run_cmd "agentic-p new command python/refactor-code"
      run_cmd "agentic-p new command python/write-tests"
      run_cmd "agentic-p new skill testing/pytest-patterns"
      run_cmd "agentic-p new hook safety/block-dangerous-commands"
      ;;
  esac
}

install_typescript_primitives() {
  case "$PRESET" in
    minimal)
      run_cmd "agentic-p new prompt agent typescript/typescript-pro"
      ;;
    standard)
      run_cmd "agentic-p new prompt agent typescript/typescript-pro"
      run_cmd "agentic-p new command typescript/refactor-code"
      run_cmd "agentic-p new command typescript/write-tests"
      ;;
    full)
      run_cmd "agentic-p new prompt agent typescript/typescript-pro"
      run_cmd "agentic-p new command typescript/refactor-code"
      run_cmd "agentic-p new command typescript/write-tests"
      run_cmd "agentic-p new skill testing/jest-patterns"
      run_cmd "agentic-p new hook safety/block-dangerous-commands"
      ;;
  esac
}

install_react_primitives() {
  case "$PRESET" in
    minimal)
      run_cmd "agentic-p new prompt agent react/react-pro"
      ;;
    standard)
      run_cmd "agentic-p new prompt agent react/react-pro"
      run_cmd "agentic-p new command react/create-component"
      run_cmd "agentic-p new command react/write-tests"
      ;;
    full)
      run_cmd "agentic-p new prompt agent react/react-pro"
      run_cmd "agentic-p new command react/create-component"
      run_cmd "agentic-p new command react/write-tests"
      run_cmd "agentic-p new skill ui/accessibility-patterns"
      run_cmd "agentic-p new hook safety/block-dangerous-commands"
      ;;
  esac
}

install_nestjs_primitives() {
  case "$PRESET" in
    minimal)
      run_cmd "agentic-p new prompt agent nestjs/nestjs-pro"
      ;;
    standard)
      run_cmd "agentic-p new prompt agent nestjs/nestjs-pro"
      run_cmd "agentic-p new command nestjs/create-module"
      run_cmd "agentic-p new command nestjs/write-tests"
      ;;
    full)
      run_cmd "agentic-p new prompt agent nestjs/nestjs-pro"
      run_cmd "agentic-p new command nestjs/create-module"
      run_cmd "agentic-p new command nestjs/write-tests"
      run_cmd "agentic-p new skill api/rest-patterns"
      run_cmd "agentic-p new hook safety/block-dangerous-commands"
      ;;
  esac
}

install_turborepo_primitives() {
  case "$PRESET" in
    minimal)
      run_cmd "agentic-p new prompt agent turborepo/monorepo-pro"
      ;;
    standard)
      run_cmd "agentic-p new prompt agent turborepo/monorepo-pro"
      run_cmd "agentic-p new command turborepo/create-package"
      run_cmd "agentic-p new command turborepo/sync-dependencies"
      ;;
    full)
      run_cmd "agentic-p new prompt agent turborepo/monorepo-pro"
      run_cmd "agentic-p new command turborepo/create-package"
      run_cmd "agentic-p new command turborepo/sync-dependencies"
      run_cmd "agentic-p new skill monorepo/workspace-patterns"
      run_cmd "agentic-p new hook safety/block-dangerous-commands"
      ;;
  esac
}

install_rust_primitives() {
  case "$PRESET" in
    minimal)
      run_cmd "agentic-p new prompt agent rust/rust-pro"
      ;;
    standard)
      run_cmd "agentic-p new prompt agent rust/rust-pro"
      run_cmd "agentic-p new command rust/refactor-code"
      run_cmd "agentic-p new command rust/write-tests"
      ;;
    full)
      run_cmd "agentic-p new prompt agent rust/rust-pro"
      run_cmd "agentic-p new command rust/refactor-code"
      run_cmd "agentic-p new command rust/write-tests"
      run_cmd "agentic-p new skill testing/cargo-test-patterns"
      run_cmd "agentic-p new hook safety/block-dangerous-commands"
      ;;
  esac
}

# Step 5: Configure .gitignore
configure_gitignore() {
  local gitignore=".gitignore"
  
  if [ ! -f "$gitignore" ]; then
    run_cmd "touch $gitignore"
  fi
  
  if ! grep -q "# Agentic Primitives" "$gitignore" 2>/dev/null; then
    log "Adding agentic-primitives entries to .gitignore..."
    if [ "$DRY_RUN" = false ]; then
      cat >> "$gitignore" << 'EOF'

# Agentic Primitives
.agentic/
primitives/build/
EOF
    else
      info "[DRY RUN] Would add entries to .gitignore"
    fi
  fi
}

# Step 6: Install git hooks (optional)
install_git_hooks() {
  if [ "$INSTALL_HOOKS" = true ]; then
    log "Installing git hooks..."
    if [ -f "Makefile" ] && grep -q "git-hooks-install" Makefile 2>/dev/null; then
      run_cmd "make git-hooks-install"
    else
      warn "No Makefile or git-hooks-install target found"
    fi
  fi
}

# Step 7: Validate setup
validate_setup() {
  log "Validating primitives..."
  run_cmd "agentic-p validate"
}

# Main execution
main() {
  print_banner
  
  ensure_cli
  detect_or_use_stack
  init_repo
  install_primitives
  configure_gitignore
  install_git_hooks
  validate_setup
  
  print_success "$STACK"
}

main

