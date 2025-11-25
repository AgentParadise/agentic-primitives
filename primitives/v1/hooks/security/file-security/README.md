# File Security Validator

Specialized security hook for validating file operations - protects sensitive files and system paths.

## Features

- Blocks access to `.env`, credentials, SSH keys, certificates
- Protects system paths (`/etc/`, `/boot/`, `/sys/`, `/proc/`)
- Path traversal detection
- Fast validation (< 50ms)

## Usage

```bash
agentic-p build --primitive primitives/v1/hooks/security/file-security --provider claude --output build/claude
```

## Protected Patterns

- `.env` files
- `.aws/credentials`
- SSH keys (`id_rsa`, `id_ed25519`)
- Certificates (`.pem`, `.key`)
- Files containing: `password`, `secret`, `token`, `api_key`

## System Paths

- `/etc/passwd`, `/etc/shadow`
- `/boot/`, `/sys/`, `/proc/`


