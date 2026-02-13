#!/bin/bash
# Interactive TUI for deleting secrets from macOS Keychain and .zshrc

set -e

# Colors
BOLD='\033[1m'
DIM='\033[2m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

ZSHRC="${HOME}/.zshrc"

echo ""
echo -e "${BOLD}🗑️  macOS Keychain Secret Remover${NC}"
echo -e "${DIM}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Find all generic passwords for this user
echo -e "${BLUE}Your secrets in Keychain:${NC}"
echo ""

# Get list of service names from keychain
SECRETS=$(security dump-keychain 2>/dev/null | grep -A4 "class: \"genp\"" | grep "svce" | sed 's/.*="//;s/"$//' | sort -u)

if [[ -z "$SECRETS" ]]; then
  echo -e "${YELLOW}No secrets found in Keychain.${NC}"
  exit 0
fi

# Display numbered list
i=1
declare -a SECRET_ARRAY
while IFS= read -r secret; do
  SECRET_ARRAY+=("$secret")
  echo -e "  ${BOLD}$i)${NC} $secret"
  ((i++))
done <<< "$SECRETS"

echo ""
echo -e "${DIM}Enter the number of the secret to delete (or 'q' to quit):${NC}"
read -p "> " CHOICE

if [[ "$CHOICE" == "q" || "$CHOICE" == "Q" ]]; then
  echo -e "${YELLOW}Cancelled.${NC}"
  exit 0
fi

# Validate choice
if ! [[ "$CHOICE" =~ ^[0-9]+$ ]] || (( CHOICE < 1 || CHOICE > ${#SECRET_ARRAY[@]} )); then
  echo -e "${RED}Invalid selection.${NC}"
  exit 1
fi

SELECTED_SECRET="${SECRET_ARRAY[$((CHOICE-1))]}"

echo ""
echo -e "${YELLOW}You selected: ${BOLD}${SELECTED_SECRET}${NC}"
echo -e "${RED}This will permanently delete this secret from Keychain.${NC}"
read -p "Are you sure? [y/N] " CONFIRM

if [[ ! "$CONFIRM" =~ ^[Yy] ]]; then
  echo -e "${YELLOW}Cancelled.${NC}"
  exit 0
fi

echo ""

# Delete from Keychain
echo -e "${DIM}Deleting from Keychain...${NC}"
if security delete-generic-password -a "$USER" -s "$SELECTED_SECRET" 2>/dev/null; then
  echo -e "${GREEN}✓${NC} Deleted from Keychain"
else
  echo -e "${RED}✗${NC} Failed to delete from Keychain (may not exist)"
fi

# Check if in .zshrc and offer to remove
if grep -qF "$SELECTED_SECRET" "$ZSHRC" 2>/dev/null; then
  echo ""
  echo -e "${YELLOW}Found entry in ~/.zshrc${NC}"
  read -p "Remove from .zshrc too? [Y/n] " REMOVE_ZSHRC
  
  if [[ ! "$REMOVE_ZSHRC" =~ ^[Nn] ]]; then
    # Create backup
    cp "$ZSHRC" "${ZSHRC}.bak"
    
    # Remove lines containing the secret name (the comment and export line)
    grep -v "$SELECTED_SECRET" "$ZSHRC" > "${ZSHRC}.tmp" && mv "${ZSHRC}.tmp" "$ZSHRC"
    
    echo -e "${GREEN}✓${NC} Removed from ~/.zshrc (backup at ~/.zshrc.bak)"
  fi
fi

echo ""
echo -e "${GREEN}Done!${NC} Secret has been removed."
echo -e "${DIM}Run 'source ~/.zshrc' to reload your shell config.${NC}"
