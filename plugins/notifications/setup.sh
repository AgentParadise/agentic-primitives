#!/usr/bin/env bash
# setup.sh — first-run setup for the notifications plugin
set -euo pipefail

echo "🔔 Claude Code Notifications — Setup"
echo ""

# --- ntfy topic generation ---
echo "Generate a secure ntfy topic name?"
echo "(This gives you push notifications on any device via ntfy.sh)"
echo ""
read -rp "Enter a prefix (e.g., claude, myname): " PREFIX

# Detect shell RC file
if [[ "${SHELL:-}" == */zsh ]]; then
  SHELL_RC="${HOME}/.zshrc"
else
  SHELL_RC="${HOME}/.bashrc"
fi

if [[ -z "$PREFIX" ]]; then
  echo "Skipping ntfy setup."
else
  # Generate secure random hex (with fallbacks)
  if command -v openssl &>/dev/null; then
    RANDOM_HEX="$(openssl rand -hex 32)"
  elif command -v python3 &>/dev/null; then
    RANDOM_HEX="$(python3 -c 'import os; print(os.urandom(32).hex())')"
  elif [[ -r /dev/urandom ]]; then
    RANDOM_HEX="$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  else
    echo "Error: Cannot generate secure random. Install openssl or python3." >&2
    exit 1
  fi
  TOPIC="${PREFIX}_${RANDOM_HEX}"
  echo ""
  echo "✅ Your ntfy topic: ${TOPIC}"
  echo ""
  if grep -q 'NTFY_TOPIC' "$SHELL_RC" 2>/dev/null; then
    echo "⚠️  NTFY_TOPIC already exists in $SHELL_RC — skipping write"
  else
    printf '\n# Claude Code Notifications\nexport NTFY_TOPIC="%s"\n' "$TOPIC" >> "$SHELL_RC"
    echo "Written NTFY_TOPIC to $SHELL_RC"
  fi
  echo ""
  echo "Subscribe on your phone:"
  echo "  1. Install ntfy app (iOS/Android)"
  echo "  2. Subscribe to topic: ${TOPIC}"
  echo "  3. Or open: https://ntfy.sh/${TOPIC}"
fi

echo ""
echo "---"
echo ""

# --- macOS sound theme ---
if command -v osascript &>/dev/null; then
  echo "✅ macOS detected — native notifications enabled"
  echo ""
  echo "Pick a notification theme:"
  echo "  1. default  (Ping / Basso / Glass)"
  echo "  2. ocean    (Submarine / Sonar / Blow)"
  echo "  3. minimal  (Tink / Pop / Purr)"
  echo "  4. alert    (Hero / Sosumi / Fanfare)"
  echo "  5. custom   (set each individually)"
  echo ""
  read -rp "Choice [1]: " THEME_CHOICE
  THEME_CHOICE="${THEME_CHOICE:-1}"

  case "$THEME_CHOICE" in
    1) THEME="default" ;;
    2) THEME="ocean" ;;
    3) THEME="minimal" ;;
    4) THEME="alert" ;;
    5)
      echo ""
      echo "Available macOS sounds: Basso, Blow, Bottle, Frog, Funk, Glass, Hero,"
      echo "  Morse, Ping, Pop, Purr, Sosumi, Submarine, Tink, Sonar, Fanfare"
      echo ""
      read -rp "Sound for idle [Ping]: " CUSTOM_IDLE
      read -rp "Sound for permission [Basso]: " CUSTOM_PERM
      read -rp "Sound for complete [Glass]: " CUSTOM_COMP
      CUSTOM_IDLE="${CUSTOM_IDLE:-Ping}"
      CUSTOM_PERM="${CUSTOM_PERM:-Basso}"
      CUSTOM_COMP="${CUSTOM_COMP:-Glass}"
      # Remove existing sound overrides before writing
      sed -i.bak '/CLAUDE_NOTIFY_SOUND_IDLE\|CLAUDE_NOTIFY_SOUND_PERMISSION\|CLAUDE_NOTIFY_SOUND_COMPLETE\|CLAUDE_NOTIFY_THEME/d' "$SHELL_RC" 2>/dev/null || true
      rm -f "${SHELL_RC}.bak"
      {
        echo "export CLAUDE_NOTIFY_SOUND_IDLE=\"${CUSTOM_IDLE}\""
        echo "export CLAUDE_NOTIFY_SOUND_PERMISSION=\"${CUSTOM_PERM}\""
        echo "export CLAUDE_NOTIFY_SOUND_COMPLETE=\"${CUSTOM_COMP}\""
      } >> "$SHELL_RC"
      echo ""
      echo "✅ Custom sounds written to $SHELL_RC"
      THEME=""
      ;;
    *) THEME="default" ;;
  esac

  if [[ -n "${THEME:-}" ]]; then
    # Remove existing theme/sound overrides before writing
    sed -i.bak '/CLAUDE_NOTIFY_THEME\|CLAUDE_NOTIFY_SOUND_IDLE\|CLAUDE_NOTIFY_SOUND_PERMISSION\|CLAUDE_NOTIFY_SOUND_COMPLETE/d' "$SHELL_RC" 2>/dev/null || true
    rm -f "${SHELL_RC}.bak"
    echo "export CLAUDE_NOTIFY_THEME=\"${THEME}\"" >> "$SHELL_RC"
    echo ""
    echo "✅ Theme '${THEME}' written to $SHELL_RC"
  fi
else
  echo "ℹ️  Not on macOS — native notifications disabled"
  echo "   Use ntfy or pushover for push notifications"
fi

echo ""
echo "Done! Run Claude Code and notifications will fire automatically."
