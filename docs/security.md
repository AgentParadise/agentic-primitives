# Security

## Automated Security Checks

We run weekly security audits every Monday at 9:00 AM UTC via GitHub Actions.

### What We Check

1. **Known Vulnerabilities** (`cargo audit`)
   - Checks all dependencies against RustSec Advisory Database
   - Creates GitHub issue if vulnerabilities found

2. **Outdated Dependencies** (`cargo-outdated`)
   - Identifies dependencies with newer versions available
   - Focuses on root dependencies only

3. **Software Bill of Materials** (SBOM)
   - Generated in SPDX and CycloneDX formats
   - Available as workflow artifacts

## Manual Security Review

Run security checks locally:

```bash
# Install tools
cargo install cargo-audit cargo-outdated cargo-sbom

# Check for vulnerabilities
cd cli && cargo audit

# Check for outdated dependencies
cd cli && cargo outdated

# Generate SBOM
cd cli && cargo sbom --output-format spdx
```

## Reporting Security Issues

Please report security vulnerabilities via GitHub Security Advisories:
https://github.com/neural/agentic-primitives/security/advisories

Do not open public issues for security concerns.

## Security Policy

- We aim to patch high-severity vulnerabilities within 7 days
- Medium-severity vulnerabilities within 30 days  
- Low-severity vulnerabilities in next minor release
- We follow responsible disclosure practices

