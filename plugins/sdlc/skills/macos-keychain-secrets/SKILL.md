---
name: macos-keychain-secrets
description: Store and retrieve secrets securely using macOS Keychain. Use when working with API keys, tokens, credentials, or any sensitive values that should not be stored in plain text files, dotfiles, or committed to git. Triggers on requests to store secrets, manage credentials, set up environment variables securely, or avoid hardcoding sensitive values.
---

# macOS Keychain Secrets Management

Securely store and retrieve secrets using the macOS `security` command-line tool.

## Quick Start - Interactive Tools

### Add a secret

```bash
${CLAUDE_PLUGIN_ROOT}/skills/macos-keychain-secrets/scripts/add-secret.sh
```

This will:
1. Prompt for a service name (keychain identifier)
2. Prompt for an environment variable name
3. Securely prompt for the secret value (hidden input)
4. Store it in Keychain and add the export to `~/.zshrc`

### Delete a secret

```bash
${CLAUDE_PLUGIN_ROOT}/skills/macos-keychain-secrets/scripts/delete-secret.sh
```

This will:
1. List all your secrets stored in Keychain
2. Let you select one to delete
3. Remove it from Keychain and optionally from `~/.zshrc`

## Core Commands

### Store a secret

```bash
security add-generic-password -a "$USER" -s "SERVICE_NAME" -w "SECRET_VALUE"
```

- `-a` = account (use `$USER` for consistency)
- `-s` = service name (unique identifier for this secret)
- `-w` = password/secret value

### Retrieve a secret

```bash
security find-generic-password -a "$USER" -s "SERVICE_NAME" -w
```

Returns only the secret value (no metadata).

### Update an existing secret

```bash
security add-generic-password -U -a "$USER" -s "SERVICE_NAME" -w "NEW_VALUE"
```

The `-U` flag updates if exists, creates if not.

### Delete a secret

```bash
security delete-generic-password -a "$USER" -s "SERVICE_NAME"
```

## Shell Integration

Add to `~/.zshrc` or `~/.bashrc`:

```bash
export API_KEY=$(security find-generic-password -a "$USER" -s "my_api_key" -w 2>/dev/null)
```

The `2>/dev/null` suppresses errors if the key doesn't exist.

## Naming Conventions

Use consistent, descriptive service names:

| Secret Type | Service Name Pattern | Example |
|-------------|---------------------|---------|
| API keys | `{service}_api_key` | `openai_api_key` |
| OAuth tokens | `{service}_oauth_token` | `claude_oauth_token` |
| Database credentials | `{service}_db_{field}` | `postgres_db_password` |
| Generic secrets | `{project}_{purpose}` | `myapp_encryption_key` |

## Common Patterns

### Multiple related secrets

```bash
# Store
security add-generic-password -a "$USER" -s "aws_access_key_id" -w "AKIA..."
security add-generic-password -a "$USER" -s "aws_secret_access_key" -w "wJal..."

# Load in shell config
export AWS_ACCESS_KEY_ID=$(security find-generic-password -a "$USER" -s "aws_access_key_id" -w 2>/dev/null)
export AWS_SECRET_ACCESS_KEY=$(security find-generic-password -a "$USER" -s "aws_secret_access_key" -w 2>/dev/null)
```

### Conditional loading with fallback

```bash
# Only set if keychain has the value
if CLAUDE_TOKEN=$(security find-generic-password -a "$USER" -s "claude_oauth_token" -w 2>/dev/null); then
  export CLAUDE_CODE_OAUTH_TOKEN="$CLAUDE_TOKEN"
fi
```

### Helper function for shell config

```bash
# Add to ~/.zshrc
keychain_get() {
  security find-generic-password -a "$USER" -s "$1" -w 2>/dev/null
}

keychain_set() {
  security add-generic-password -U -a "$USER" -s "$1" -w "$2"
}

# Usage
export OPENAI_API_KEY=$(keychain_get "openai_api_key")
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "security: SecKeychainSearchCopyNext" error | Secret doesn't exist; check service name spelling |
| "already exists" error | Use `-U` flag to update |
| Secret not loading in new terminal | Run `source ~/.zshrc` or open new terminal |
| Permission denied | May need to unlock keychain: `security unlock-keychain` |

## Security Notes

- Keychain is encrypted at rest using your login password
- Secrets sync via iCloud Keychain if enabled (disable for sensitive work secrets)
- First access may prompt for keychain password
- Use `security lock-keychain` when stepping away
