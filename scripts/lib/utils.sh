#!/usr/bin/env bash
# Utility functions for bootstrap script

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
  echo -e "${GREEN}==>${NC} $1"
}

error() {
  echo -e "${RED}Error:${NC} $1" >&2
  exit 1
}

warn() {
  echo -e "${YELLOW}Warning:${NC} $1"
}

info() {
  echo -e "${BLUE}Info:${NC} $1"
}

# Run command (respect dry-run)
run_cmd() {
  local cmd="$1"
  
  if [ "$VERBOSE" = true ]; then
    log "Running: $cmd"
  fi
  
  if [ "$DRY_RUN" = true ]; then
    info "[DRY RUN] Would run: $cmd"
  else
    eval "$cmd"
  fi
}

# Print banner
print_banner() {
  cat << 'EOF'
    ___                  __  _      
   /   | ____ ____  ____/ /_(_)_____
  / /| |/ __ `/ _ \/ __  / __/ ___/
 / ___ / /_/ /  __/ /_/ / /_/ /__  
/_/  |_\__, /\___/\__,_/\__/_/\___/
      /____/                        
   Primitives Bootstrap

EOF
}

# Print success message
print_success() {
  local stack="$1"
  
  cat << EOF

🎉 ${GREEN}Bootstrap Complete!${NC}

Your $stack project is now set up with agentic-primitives.

${BLUE}Next steps:${NC}
  1. Review primitives: ${GREEN}agentic-p list${NC}
  2. Validate setup: ${GREEN}agentic-p validate${NC}
  3. Build for provider: ${GREEN}agentic-p build --provider claude${NC}
  4. Install: ${GREEN}agentic-p install --project${NC}

${BLUE}Documentation:${NC}
  https://github.com/neural/agentic-primitives

EOF
}

