---
description: Audit and harden repository security — supply chain, CI/CD scanners, secrets, credentials
argument-hint: "[audit|fix|both] - default: both"
model: opus
allowed-tools: Read, Grep, Glob, Bash, Edit, Write
---

# Security Hardening

Audit a codebase for security vulnerabilities and implement fixes. Two modes:

- **audit** — read-only scan, produces a prioritized findings report
- **fix** — implements the fixes (confirm with user before each change)
- **both** (default) — audit first, then fix

MODE: $1 || "both"

---

## Threat Model

This skill covers five attack surface areas. Each has a concrete historical incident:

### 1. Supply Chain — Tag Repointing (XZ-utils, 2024)

A GitHub Actions workflow step runs inside CI with access to repository secrets and write
permissions. If a third-party Action is pinned to a mutable version tag (`@v4`), a
compromised maintainer can silently move that tag to an attacker-controlled commit — every
repo using the tag now executes malicious code on the next push with no diff in that repo.

The XZ-utils backdoor (CVE-2024-3094) demonstrated exactly this social engineering + supply
chain path: a patient attacker gained maintainer trust over years, then inserted a backdoor.

**Defense:** Every `uses:` line pins to an **immutable commit SHA** with the version as an
inline comment for human readability. Any update requires an explicit SHA change — producing
a reviewable diff.

```yaml
# SAFE — SHA cannot be repointed; update is a visible diff
- uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4

# UNSAFE — tag can be silently moved to a malicious commit overnight
- uses: actions/checkout@v4
```

To update: `gh api repos/actions/checkout/git/ref/tags/v4 --jq '.object.sha'`
(If the tag is annotated, dereference: `gh api repos/<owner>/<repo>/git/tags/<sha> --jq '.object.sha'`)

### 2. Supply Chain — Postinstall Hook Injection (event-stream 2018, ua-parser-js 2021)

`npm install` and `pnpm install` execute `preinstall`/`postinstall` scripts from every
package in the dependency tree by default — including transitive dependencies you never
explicitly chose. An attacker who compromises or publishes a malicious version of any
package in your tree can run arbitrary code in CI (with access to secrets) during install.

The event-stream incident: a trusted npm package was transferred to a malicious actor who
added a dependency that exfiltrated cryptocurrency wallet credentials via postinstall.

**Two defenses — choose based on the project:**

```yaml
# OPTION A: Blanket block — safe for pure JS build tools that don't need native binaries
- run: npm ci --ignore-scripts
  # ^ Blocks ALL postinstall/preinstall hooks. Works for most dashboard/docs builds.
  #   Vite 7.x sources esbuild via optional platform packages, not postinstall,
  #   so this is safe for Vite projects.

# OPTION B: Allowlist (preferred for pnpm projects with native deps like esbuild/sharp)
# In package.json:
# "pnpm": { "onlyBuiltDependencies": ["esbuild", "sharp", "@img/sharp-linux-x64"] }
# Then: pnpm install (no flag needed — allowlist enforces it)
#
# Why prefer allowlist over --ignore-scripts when native deps exist:
# --ignore-scripts breaks packages that legitimately need a build step (native addons,
# platform-specific binaries). The allowlist is explicit, code-reviewed, and auditable —
# you can see exactly which packages are allowed to run install scripts and why.
```

### 3. Dependency Vulnerabilities — Known CVEs (Log4Shell 2021, requests CVE-2023-32681)

Dependencies drift out of date and accumulate published CVEs. Without automated scanning,
teams only discover vulnerabilities reactively — after exploitation or incident disclosure.

**Defense:** Automated SCA (Software Composition Analysis) on every push and PR:

- **OSV Scanner** — checks all lock files against the OSV database (covers PyPI, npm,
  crates.io, Go, Maven). Single tool, multiple ecosystems.
- **dependency-review-action** — GitHub-native, blocks PRs that introduce newly vulnerable
  packages. Requires GitHub Advanced Security (free for public repos).
- **Dependabot** — automated PRs for outdated/vulnerable dependencies.

### 4. Excessive CI Permissions (blast radius amplification)

By default, GitHub Actions runs with `write-all` permissions — a compromised or buggy step
can push to branches, create releases, modify packages, or read/write Actions secrets.
Least-privilege defaults contain the blast radius of any single compromised step.

**Defense:** Top-level `permissions: contents: read` in every workflow. Jobs that need
write access declare it explicitly at the job level, creating a clear audit trail.

```yaml
# At top of workflow file — least-privilege default
permissions:
  contents: read

jobs:
  release:
    # Only this job needs write — visible, reviewable, scoped
    permissions:
      contents: write
      packages: write
```

### 5. Credential Exposure (Codecov breach 2021, dozens of accidental git commits)

Secrets committed to git are permanently exposed — even if deleted in a follow-up commit,
they exist in git history, forks, CI logs, and any clone made during the exposure window.

**Defenses (layered):**
- `.gitignore` patterns for key/cert extensions (passive safety net)
- Pre-commit secret scanning — `gitleaks` or `detect-secrets` blocks the commit before
  it ever reaches git history (active gate)
- GitHub secret scanning — catches exposed secrets in pushes even without pre-commit hook
- CODEOWNERS restricting who can modify high-risk paths

### 6. Static Application Security Testing — Code Vulnerabilities

SQL injection, XSS, insecure deserialization, path traversal, hardcoded credentials in
source code — these require SAST tooling to catch systematically.

**Defense:**

- **CodeQL** — GitHub-native, free for public repos. Covers Python, JavaScript/TypeScript,
  Java, Go, C/C++, C#, Ruby, Swift. Runs as a workflow job.
- **Semgrep** — OSS rules engine with security-focused rulesets. Faster than CodeQL,
  easier to add custom rules.
- **Bandit** — Python-specific SAST. Fast, no config needed.
- **ESLint `plugin:security`** — JavaScript/TypeScript security rules.

### 7. Container Vulnerabilities — Image CVEs

Docker images accumulate OS-level CVEs in base image packages over time. OSV Scanner
covers app-layer dependencies (Python, npm, etc.) in lock files. For OS-layer CVEs,
use **Docker Scout**.

**Why Docker Scout over alternatives:** You already trust Docker for the container runtime —
Scout extends that existing trust rather than introducing a new third-party security
dependency. Trivy (aquasecurity) is commonly cited but aquasecurity has had multiple
security incidents; a compromised scanner is a supply chain risk that undermines the
whole point. Scout is maintained by the same team that ships the runtime, keeping the
trust chain short.

### 8. Version Pinning — Lock File Discipline

`npm install` (not `ci`) or `pip install` (not from lock file) resolve "latest compatible"
versions, meaning a build on Tuesday may install a different dep than Monday's build —
silently picking up a newly published malicious or broken version.

**Defenses:**
- Always commit lock files (`uv.lock`, `package-lock.json`, `pnpm-lock.yaml`, `Cargo.lock`)
- Use `npm ci` (not `npm install`) — enforces exact lock file versions, fails on mismatch
- Use `pnpm install --frozen-lockfile` in CI
- Use `uv sync --frozen` in CI — fails if `uv.lock` is out of sync with `pyproject.toml`
- Pin Python version explicitly: `python-version: "3.12"` not `"3.x"` in CI

```yaml
# SAFE — exact versions from lock file, fails if lock file is stale
- run: npm ci --ignore-scripts

# UNSAFE — resolves fresh, may pick up new malicious version
- run: npm install
```

### 9. Transitive Dependency Poisoning (litellm 2026, Shai-Halud 2025)

An attacker gains access to a package maintainer's credentials — via phishing, token theft,
or account takeover — and publishes a malicious version of a package. The payload doesn't
need to be in a package you directly depend on. It can be buried anywhere in the transitive
dependency tree: if package A depends on B which depends on C, and C is poisoned, everyone
who installs A is compromised.

The attack vectors evolve faster than defenses:
- **Python `.pth` files** (litellm 1.82.8, 2026): A `.pth` file in `site-packages` executes
  arbitrary Python on interpreter startup — before your code even imports anything. This
  bypasses `--ignore-scripts` because it's not an install hook, it's a Python runtime feature.
  The litellm attack base64-encoded instructions to exfiltrate SSH keys, cloud credentials,
  Kubernetes configs, shell history, and crypto wallets to a remote server.
- **`__init__.py` injection**: Malicious code added to a package's `__init__.py` runs on
  first import. No install hooks needed.
- **npm postinstall** (event-stream 2018, ua-parser-js 2021): Covered in threat model #2,
  but the credential theft pattern is identical.
- **Shai-Halud** (2025): Supply chain attack targeting AI/ML ecosystem packages with
  credential exfiltration payloads.

The contagion is the real danger: litellm has 97M downloads/month, but the blast radius
extends to every project that depends on litellm (e.g., `pip install dspy` also pulled in
the poisoned version). One compromised package deep in a dependency tree can affect thousands
of downstream projects.

**Defenses (layered):**
- **Hash verification**: Pin not just versions but content hashes. Even if an attacker
  publishes a new artifact for the same version, the hash won't match.
- **Native ecosystem audits**: `pip-audit` and `pnpm audit` check for known-compromised
  versions beyond what OSV Scanner covers.
- **Dependency minimization**: The only dependency that can't be poisoned is one you don't
  have. Fewer dependencies = smaller attack surface. See threat model #10.
- **Vendoring critical deps**: For small, critical packages, copy the source into your repo.
  You now control the code and review changes via normal PR review.
- **Lock file discipline**: Covered in threat model #8 — ensures reproducible installs.

### 10. Dependency Sprawl — Attack Surface Proportional to Dependency Count

Every dependency is a trust relationship. Every *transitive* dependency is a trust
relationship you didn't explicitly agree to. A project with 500 npm packages has 500
potential supply chain entry points — and you've probably reviewed zero of the transitive
ones.

The goal is to **minimize dependencies toward zero**. This isn't about reinventing wheels —
it's about recognizing that each dependency carries ongoing risk that compounds over time:
- Maintainer accounts can be compromised
- Projects can be transferred to malicious actors
- Abandoned packages accumulate unpatched CVEs
- Deep dependency trees create blast radius you can't predict

**Strategies:**
- **Prefer stdlib**: Python's standard library and Node's built-in modules cover more than
  most developers realize. `urllib`, `json`, `pathlib`, `subprocess`, `http.server`, etc.
- **Yoink simple functionality**: When a dependency provides a small, well-understood function,
  use an LLM to rewrite it locally. A 50-line utility you own is safer than a package with
  200 transitive dependencies.
- **Regular dependency audits**: `uv tree --depth 3` and `pnpm why <package>` to understand
  what you're actually pulling in and whether each dependency earns its place.
- **Remove unused deps**: Dependencies accumulate. Periodically run `deptry` (Python) or
  `depcheck` (Node) to find packages that are imported nowhere.
- **Consolidate overlapping deps**: If two packages serve similar purposes (e.g., `recharts`
  and `@nivo/*` for charts), pick one and remove the other.
- **Question heavy transitive trees**: A package with 3 direct deps that pulls in 150
  transitive deps is a red flag. Look for lighter alternatives or vendor the functionality.

---

## Audit Workflow

### Step 1: Discover Project Structure

```bash
echo "=== Workflows ==="
ls .github/workflows/ 2>/dev/null || echo "No GitHub Actions workflows"

echo ""
echo "=== Lock files (must ALL be committed) ==="
find . -maxdepth 5 \( \
  -name "package-lock.json" -o \
  -name "pnpm-lock.yaml" -o \
  -name "yarn.lock" -o \
  -name "uv.lock" -o \
  -name "Cargo.lock" \
\) -not -path "*/node_modules/*" -not -path "*/.git/*"

echo ""
echo "=== Container files ==="
find . -maxdepth 5 -name "Dockerfile*" -o -name "docker-compose*.yml" \
  | grep -v ".git" | head -20
```

### Step 2: GitHub Actions SHA Pinning

```bash
echo "=== Actions with MUTABLE tags (MUST FIX) ==="
# Matches @v1, @v2.3, @main, @master, @latest, @stable
grep -rn "uses:.*@\(v[0-9]\|main\b\|master\b\|latest\b\|stable\b\)" \
  .github/workflows/ 2>/dev/null || echo "None found ✅"

echo ""
echo "=== Actions with SHA pins (safe) ==="
grep -rn "uses:.*@[0-9a-f]\{40\}" .github/workflows/ 2>/dev/null | wc -l
echo " SHA-pinned action lines"
```

### Step 3: Workflow Permissions

```bash
echo "=== Workflows missing top-level permissions (risky) ==="
for f in .github/workflows/*.yml .github/workflows/*.yaml; do
  [ -f "$f" ] || continue
  if ! grep -q "^permissions:" "$f"; then
    echo "  ❌ MISSING: $f"
  else
    echo "  ✅ $f"
  fi
done
```

### Step 4: Install Hygiene (Postinstall Hook Blocking)

```bash
echo "=== npm/pnpm install commands in CI ==="
grep -rn "npm install\b\|npm ci\b\|pnpm install\b\|yarn install\b" \
  .github/workflows/ 2>/dev/null

echo ""
echo "=== Missing script blocking (flag for review) ==="
grep -rn "npm ci\b\|npm install\b\|pnpm install\b" .github/workflows/ 2>/dev/null \
  | grep -v "ignore-scripts\|frozen-lockfile" \
  || echo "All installs have script/version blocking ✅"

echo ""
echo "=== pnpm onlyBuiltDependencies (allowlist approach) ==="
grep -rn "onlyBuiltDependencies" . --include="package.json" \
  --exclude-dir=node_modules 2>/dev/null || echo "Not configured"
```

### Step 5: Lock File Discipline

```bash
echo "=== Lock files tracked by git (must be committed) ==="
git ls-files | grep -E "uv\.lock|package-lock\.json|pnpm-lock\.yaml|yarn\.lock|Cargo\.lock"

echo ""
echo "=== Lock files in .gitignore (BAD — should be committed) ==="
grep -E "uv\.lock|package-lock|pnpm-lock|yarn\.lock|Cargo\.lock" .gitignore 2>/dev/null \
  || echo "None ignored ✅"

echo ""
echo "=== CI using npm install instead of npm ci ==="
grep -rn "npm install\b" .github/workflows/ 2>/dev/null \
  | grep -v "#" || echo "None found ✅"
```

### Step 6: Vulnerability / SCA Scanning

```bash
echo "=== OSV Scanner ==="
grep -rn "osv-scanner" .github/workflows/ 2>/dev/null || echo "❌ NOT CONFIGURED"

echo ""
echo "=== Dependency Review Action ==="
grep -rn "dependency-review-action" .github/workflows/ 2>/dev/null || echo "❌ NOT CONFIGURED"

echo ""
echo "=== Dependabot ==="
cat .github/dependabot.yml 2>/dev/null || echo "❌ NOT CONFIGURED"
```

### Step 6.5: Native Ecosystem Audits

OSV Scanner checks lock files against a vulnerability database, but native ecosystem tools
(`pip-audit`, `pnpm audit`) cover additional advisories specific to each package registry.
Run both for defense in depth.

```bash
echo "=== pip-audit (Python) ==="
if command -v pip-audit &>/dev/null; then
  # Export locked deps with hashes, then audit against PyPI advisory DB.
  # --disable-pip: use the PyPI JSON API directly (faster, no pip subprocess).
  # --require-hashes: verify package integrity — catches tampered artifacts.
  uv export --format requirements-txt --no-hashes --quiet \
    | pip-audit --disable-pip -r /dev/stdin 2>&1 \
    || echo "⚠️ pip-audit found issues (see above)"
else
  echo "❌ pip-audit not installed. Install: uv tool install pip-audit"
fi

echo ""
echo "=== pnpm audit (Node.js) ==="
# --prod: only audit production dependencies (devDependencies aren't deployed).
# Run per-app because each has its own lock file and dependency tree.
for dir in apps/syn-dashboard-ui apps/syn-pulse-ui apps/syn-docs; do
  if [ -f "$dir/pnpm-lock.yaml" ] || [ -f "$dir/package-lock.json" ]; then
    echo "--- $dir ---"
    (cd "$dir" && pnpm audit --prod 2>&1) || echo "⚠️ audit issues in $dir"
  fi
done
```

### Step 6.6: Dependency Tree Review

Understand what you're actually pulling in. Heavy transitive trees are supply chain risk —
each package is a trust relationship. The goal is to identify reduction targets.

```bash
echo "=== Python dependency tree (direct deps + first 2 levels) ==="
uv tree --depth 2 2>/dev/null || echo "Run from project root with uv.lock present"

echo ""
echo "=== Python: total package count ==="
grep -c '^\[\[package\]\]' uv.lock 2>/dev/null || echo "No uv.lock found"

echo ""
echo "=== Node.js: total package count per app ==="
for dir in apps/syn-dashboard-ui apps/syn-pulse-ui apps/syn-docs; do
  if [ -f "$dir/pnpm-lock.yaml" ]; then
    count=$(grep -c 'resolution:' "$dir/pnpm-lock.yaml" 2>/dev/null || echo "?")
    echo "  $dir: ~$count packages"
  elif [ -f "$dir/package-lock.json" ]; then
    count=$(grep -c '"resolved":' "$dir/package-lock.json" 2>/dev/null || echo "?")
    echo "  $dir: ~$count packages"
  fi
done

echo ""
echo "=== Heaviest transitive dependency chains (investigate these) ==="
echo "Use 'pnpm why <package>' to trace why a package is in your tree."
echo "Use 'uv tree --invert <package>' to trace Python reverse dependencies."
```

### Step 7: SAST — Static Security Analysis

```bash
echo "=== CodeQL ==="
grep -rn "codeql\|github/codeql-action" .github/workflows/ 2>/dev/null \
  || echo "❌ NOT CONFIGURED"

echo ""
echo "=== Semgrep ==="
grep -rn "semgrep" .github/workflows/ 2>/dev/null || echo "Not configured"

echo ""
echo "=== Bandit (Python SAST) ==="
grep -rn "bandit" .github/workflows/ pyproject.toml 2>/dev/null || echo "Not configured"

echo ""
echo "=== ESLint security plugin (JS/TS) ==="
grep -rn "plugin:security\|eslint-plugin-security" . \
  --include=".eslintrc*" --include="package.json" \
  --exclude-dir=node_modules 2>/dev/null || echo "Not configured"
```

### Step 8: Container Scanning

```bash
echo "=== Dockerfile count ==="
find . -name "Dockerfile*" -not -path "*/.git/*" | wc -l

echo ""
echo "=== Docker Scout (container scanning) ==="
grep -rn "docker-scout\|docker/scout-action" .github/workflows/ 2>/dev/null \
  || echo "Not configured"
```

### Step 9: Secret Scanning

```bash
echo "=== Pre-commit config ==="
cat .pre-commit-config.yaml 2>/dev/null || echo "No .pre-commit-config.yaml"

echo ""
echo "=== gitleaks in CI ==="
grep -rn "gitleaks\|zricethezav/gitleaks" .github/workflows/ 2>/dev/null \
  || echo "Not configured in CI"

echo ""
echo "=== GitHub secret scanning ==="
# Cannot check programmatically — requires repo Settings > Security > Secret scanning
echo "Check: Settings > Security > Secret scanning > Enable"

echo ""
echo "=== Potential hardcoded secrets (heuristic) ==="
grep -rn \
  -e "api_key\s*=\s*['\"][^'\"]\{10,\}" \
  -e "secret\s*=\s*['\"][^'\"]\{10,\}" \
  -e "password\s*=\s*['\"][^'\"]\{8,\}" \
  -e "token\s*=\s*['\"][^'\"]\{10,\}" \
  --include="*.py" --include="*.ts" --include="*.js" --include="*.yml" --include="*.yaml" \
  --exclude-dir=".git" --exclude-dir="node_modules" --exclude-dir=".venv" \
  . 2>/dev/null \
  | grep -v "example\|placeholder\|your_\|<\|env\.\|os\.\|process\.env\|getenv\|secret_key\s*=" \
  || echo "No obvious hardcoded secrets ✅"

echo ""
echo "=== .env files accidentally tracked ==="
git ls-files | grep -E "^\.env$|^\.env\." | grep -v ".example" \
  || echo "None tracked ✅"
```

### Step 10: .gitignore Credential Patterns

```bash
echo "=== Credential patterns in .gitignore ==="
for pattern in "*.pem" "*.key" "*.p12" "id_rsa" "id_ed25519" "*.cer" "*.crt" ".env"; do
  if grep -q "$pattern" .gitignore 2>/dev/null; then
    echo "  ✅ $pattern"
  else
    echo "  ❌ MISSING: $pattern"
  fi
done
```

### Step 11: CODEOWNERS

```bash
echo "=== CODEOWNERS protection of high-risk paths ==="
for path in ".github/" "docker/" "infra/" ".gitmodules"; do
  if grep -q "$path" .github/CODEOWNERS 2>/dev/null; then
    echo "  ✅ $path"
  else
    echo "  ❌ NOT PROTECTED: $path"
  fi
done
```

---

## Fix Recipes

Only apply when MODE is "fix" or "both". Walk through each finding with the user.

### Fix: Pin an Action to SHA

```bash
# Resolve SHA for a tag:
gh api repos/actions/checkout/git/ref/tags/v4 --jq '.object.sha'
# If the result is a tag object (annotated), dereference one more time:
gh api repos/actions/checkout/git/tags/<sha-from-above> --jq '.object.sha'
```

Replace in workflow:
```yaml
# Before
- uses: actions/checkout@v4

# After — SHA pinned, version visible in comment
- uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4
```

### Fix: Add Workflow Permissions

Add before `jobs:` in each workflow:
```yaml
# Least-privilege default — limits blast radius if a step is compromised.
# Jobs needing write access declare it explicitly at the job level.
permissions:
  contents: read
```

### Fix: Add --ignore-scripts

```yaml
# npm — blocks postinstall hooks (event-stream/ua-parser-js attack vector)
- run: npm ci --ignore-scripts

# pnpm — blanket approach
- run: pnpm install --ignore-scripts

# pnpm — allowlist approach (preferred when native deps like esbuild need build steps)
# Add to package.json:
# "pnpm": { "onlyBuiltDependencies": ["esbuild", "sharp"] }
```

### Fix: Switch npm install → npm ci

```yaml
# npm ci enforces exact lock file versions — fails if package-lock.json is stale.
# npm install re-resolves, can silently pick up new (possibly malicious) versions.
- run: npm ci --ignore-scripts
```

### Fix: Add uv --frozen

```yaml
# --frozen fails if uv.lock is out of sync with pyproject.toml.
# Ensures CI always installs exactly what's in the lock file.
- run: uv sync --all-extras --frozen
```

### Fix: SHA-Pin a GitHub Action (Worked Example)

Mutable tags (`@v4`) can be silently moved to a malicious commit — the diff in *your* repo
is invisible. SHA-pinning makes every update an explicit, reviewable change.

```bash
# Step 1: Resolve the commit SHA for the tag you want to pin.
# This queries GitHub's git refs API — no clone needed.
gh api repos/actions/checkout/git/ref/tags/v4 --jq '.object.sha'
# → e.g. 11bd71901bbe5b1630ceea73d27597364c9af683

# Step 2: If the tag is annotated (most are), the above returns a tag object SHA,
# not a commit SHA. Dereference it to get the actual commit:
gh api repos/actions/checkout/git/tags/11bd71901bbe5b1630ceea73d27597364c9af683 \
  --jq '.object.sha'
# → the real commit SHA

# Step 3: Replace in your workflow file:
```

```yaml
# BEFORE — mutable tag. A compromised maintainer can silently repoint this
# to a malicious commit. Your CI runs attacker code with access to secrets.
- uses: actions/checkout@v4

# AFTER — immutable SHA. The version comment is for humans; CI uses the SHA.
# To update: repeat steps 1-2 above, get new SHA, update this line.
# The diff in your PR is the proof that the update was intentional.
- uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4
```

### Fix: Add pip-audit to CI

```yaml
  # pip-audit: checks Python dependencies against the PyPI advisory database.
  # Complements OSV Scanner — pip-audit catches PyPI-specific advisories that
  # OSV may not yet index, and verifies package hashes for tamper detection.
  pip-audit:
    name: Python Dependency Audit
    runs-on: ubuntu-latest
    permissions:
      contents: read  # Least-privilege — only needs to read the repo
    steps:
      - uses: actions/checkout@<SHA> # vX

      # Install uv first — we need it to export the locked dependency list.
      - uses: astral-sh/setup-uv@<SHA> # vX
        with:
          version: "latest"

      # pip-audit is a standalone tool, not a project dependency.
      # uv tool install puts it in an isolated environment — it can't
      # be poisoned by the project's own dependency tree.
      - name: Install pip-audit
        run: uv tool install pip-audit

      # Export locked deps from uv.lock → requirements.txt format.
      # --no-hashes here because pip-audit fetches its own hashes to verify.
      # --frozen ensures we export exactly what's locked, not a fresh resolve.
      - name: Audit Python dependencies
        run: |
          uv export --format requirements-txt --no-hashes --frozen --quiet \
            | pip-audit --disable-pip -r /dev/stdin
        # --disable-pip: queries PyPI JSON API directly instead of shelling
        #   out to pip. Faster and avoids pip's own dependency resolution.
        continue-on-error: true  # TODO(#N): remove after first clean baseline
```

### Fix: Add pnpm audit to CI

```yaml
  # pnpm audit: checks Node.js dependencies against the npm advisory database.
  # Runs per-app because each frontend app has its own lock file and dependency
  # tree — a vulnerability in syn-docs doesn't necessarily affect syn-dashboard-ui.
  npm-audit:
    name: Node.js Dependency Audit
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@<SHA> # vX

      - uses: pnpm/action-setup@<SHA> # vX
        with:
          version: 9

      - uses: actions/setup-node@<SHA> # vX
        with:
          node-version: "22"

      # --prod: only audit production dependencies. devDependencies run in CI
      # and local dev but never in production — their risk profile is different.
      # --audit-level moderate: fail on moderate+ severity (skip low/info noise).
      - name: Audit frontend dependencies
        run: |
          for dir in apps/syn-dashboard-ui apps/syn-pulse-ui apps/syn-docs; do
            echo "=== Auditing $dir ==="
            (cd "$dir" && pnpm audit --prod --audit-level moderate) || true
          done
        continue-on-error: true  # TODO(#N): remove after first clean baseline
```

### Fix: Enable Hash Verification for Python Dependencies

Version pinning alone isn't sufficient — if an attacker compromises PyPI and replaces
the artifact for an already-pinned version, the version number matches but the content
is malicious. Hash verification catches this.

```bash
# Export locked dependencies WITH content hashes:
uv export --format requirements-txt --hashes --frozen > requirements-hashed.txt

# The output includes lines like:
#   pydantic==2.12.5 \
#     --hash=sha256:abc123... \
#     --hash=sha256:def456...
# Each hash is the SHA-256 of the wheel/sdist. If PyPI serves a different
# artifact (tampered or replaced), the hash won't match and install fails.

# Install with hash verification:
uv pip install --require-hashes -r requirements-hashed.txt
# --require-hashes: EVERY package must have a hash. If any package is missing
# a hash entry, the install fails — no silent fallback to unhashed installs.
```

For Dockerfiles:
```dockerfile
# Generate hashed requirements at build time from the committed lock file.
# This ensures the Docker build installs exactly what was reviewed and locked,
# with cryptographic proof that no artifact was tampered with in transit.
RUN uv export --format requirements-txt --hashes --frozen > /tmp/requirements.txt \
    && uv pip install --require-hashes -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt
```

### Fix: Add OSV Scanner

```yaml
  osv-scan:
    name: OSV Vulnerability Scan
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@<SHA> # vX
      # OSV checks all lock files against the OSV database (PyPI, npm, crates.io, Go, Maven).
      # continue-on-error during rollout — remove after first clean baseline. See TODO(#N).
      - uses: google/osv-scanner-action/osv-scanner-action@<SHA> # vX
        continue-on-error: true  # TODO(#N): flip to false after clean baseline
        with:
          scan-args: |-
            --lockfile=uv.lock
            --lockfile=package-lock.json
```

### Fix: Add CodeQL SAST

```yaml
  codeql:
    name: CodeQL SAST
    runs-on: ubuntu-latest
    permissions:
      contents: read
      security-events: write  # Required to upload SARIF results
    strategy:
      matrix:
        language: [python, javascript-typescript]
    steps:
      - uses: actions/checkout@<SHA> # vX
      # CodeQL: GitHub-native SAST, free for public repos.
      # Finds SQL injection, XSS, path traversal, insecure deserialization, etc.
      - uses: github/codeql-action/init@<SHA> # vX
        with:
          languages: ${{ matrix.language }}
          queries: security-extended
      - uses: github/codeql-action/autobuild@<SHA> # vX
      - uses: github/codeql-action/analyze@<SHA> # vX
```


### Fix: Add Docker Scout Container Scanning

```yaml
  docker-scout:
    name: Docker Scout
    runs-on: ubuntu-latest
    permissions:
      contents: read
      security-events: write
    steps:
      - uses: actions/checkout@<SHA> # vX
      - name: Build image
        run: docker build -t scan-target:${{ github.sha }} .
      # Docker Scout: maintained by Docker — same trust chain as the runtime itself.
      # Preferred over third-party scanners (e.g. Trivy) precisely because it doesn't
      # add a new security-critical dependency outside the Docker ecosystem.
      - uses: docker/scout-action@<SHA> # vX
        with:
          command: cves
          image: scan-target:${{ github.sha }}
          sarif-file: scout-results.sarif
          only-severities: critical,high
      - uses: github/codeql-action/upload-sarif@<SHA> # vX
        with:
          sarif_file: scout-results.sarif
```

### Fix: Add gitleaks Secret Scanning

```yaml
  secret-scan:
    name: Secret Scan
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@<SHA> # vX
        with:
          fetch-depth: 0  # Full history — scan all commits, not just HEAD
      # gitleaks: scans git history for secrets (API keys, tokens, private keys).
      # Catches accidental commits that slipped past pre-commit hooks.
      - uses: gitleaks/gitleaks-action@<SHA> # vX
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

### Fix: Add Pre-commit Secret Gate (gitleaks)

`.pre-commit-config.yaml`:
```yaml
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.x.x  # Pin to SHA in practice
    hooks:
      - id: gitleaks
        # Scans staged files for secrets before commit reaches git history.
        # Much cheaper than incident response after accidental push.
```

### Fix: Harden .gitignore

```gitignore
# Private keys and certificates — passive safety net against accidental commits
*.pem
*.key
*.p12
*.pfx
*.cer
*.crt
id_rsa
id_rsa.pub
id_ed25519
id_ed25519.pub
*.keystore

# Environment files (use .env.example for documentation)
.env
.env.local
.env.*.local
```

### Fix: Add CODEOWNERS

`.github/CODEOWNERS`:
```
# CI/CD workflows — arbitrary code execution risk. Any change here can exfiltrate
# secrets or backdoor the pipeline. Require maintainer review.
.github/                     @<team>

# Container and infrastructure config — supply chain risk
docker/                      @<team>
infra/                       @<team>

# Shared credentials config and typed env constants — blast radius: all services
packages/syn-shared/         @<team>

# Submodule pin changes must be intentional — a silently advanced submodule
# is a supply chain attack vector analogous to tag repointing
.gitmodules                  @<team>
```

---

## Audit Report Template

```markdown
# Security Audit — <repo>

**Date:** <date>
**Auditor:** <name or "automated">

---

## Summary

| Control | Status | Priority |
|---------|--------|----------|
| Actions SHA-pinned | ✅/❌ | P0 |
| Workflow least-privilege permissions | ✅/❌ | P0 |
| npm/pnpm --ignore-scripts | ✅/❌ | P1 |
| npm ci (not npm install) | ✅/❌ | P1 |
| uv sync --frozen | ✅/❌ | P1 |
| OSV Scanner configured | ✅/❌ | P1 |
| dependency-review-action | ✅/❌ | P1 |
| CodeQL SAST | ✅/❌ | P1 |
| pip-audit (Python advisory DB) | ✅/❌ | P1 |
| pnpm audit (npm advisory DB) | ✅/❌ | P1 |
| Hash verification (uv --hashes) | ✅/❌ | P1 |
| Dependency tree reviewed | ✅/❌ | P1 |
| Container scanning (Docker Scout) | ✅/❌ | P2 |
| Secret scanning (gitleaks) | ✅/❌ | P1 |
| Pre-commit secret gate | ✅/❌ | P2 |
| .gitignore credential patterns | ✅/❌ | P2 |
| CODEOWNERS for high-risk paths | ✅/❌ | P2 |
| SECURITY.md present | ✅/❌ | P2 |
| Dependabot configured | ✅/❌ | P2 |

---

## Critical Findings (P0 — Fix before next push)

### [Finding title]
- **Location:** `path/to/file:line`
- **Issue:** <description>
- **Fix:** <exact change>

---

## High Findings (P1 — Fix this sprint)
...

## Medium Findings (P2 — Backlog)
...

---

## Applied Fixes
- [ ] SHA-pin all Actions
- [ ] Add permissions: contents: read to all workflows
- [ ] Add --ignore-scripts to CI installs
- [ ] Switch npm install → npm ci
- [ ] Add uv sync --frozen
- [ ] Add OSV Scanner
- [ ] Add CodeQL
- [ ] Add Docker Scout (if containers present)
- [ ] Add pip-audit to CI
- [ ] Add pnpm audit to CI
- [ ] Enable hash verification in Dockerfiles
- [ ] Review dependency tree — identify reduction targets
- [ ] Add gitleaks
- [ ] Harden .gitignore
- [ ] Add/update CODEOWNERS
- [ ] Create SECURITY.md

---

## Remaining (Post-launch or Planned)
- [ ] Dependabot for Actions + npm
- [ ] OSV Scanner flip to blocking (after clean baseline)
- [ ] Pre-commit hook with gitleaks
- [ ] Sigstore/cosign artifact signing
- [ ] OpenSSF Scorecard integration
- [ ] SBOM generation (syft/cyclonedx)
```

---

## Reference: Attack Taxonomy

| Attack | Vector | Year | Defense |
|--------|--------|------|---------|
| XZ-utils backdoor | GitHub Actions mutable tag | 2024 | SHA pin Actions |
| event-stream | npm postinstall hook | 2018 | --ignore-scripts |
| ua-parser-js | npm postinstall hook | 2021 | --ignore-scripts |
| Log4Shell | Vulnerable dependency | 2021 | OSV Scanner + Dependabot |
| Codecov breach | CI script injection | 2021 | CODEOWNERS + permissions |
| SolarWinds | Build pipeline compromise | 2020 | Sigstore, SLSA |
| tj-actions/changed-files | Tag repointing | 2025 | SHA pin Actions |
| litellm 1.82.8 | PyPI .pth file injection | 2026 | pip-audit, hash verification, dep minimization |
| Shai-Halud | AI/ML package credential theft | 2025 | pip-audit, hash verification, dep minimization |

## Reference: Tools

| Tool | Category | Cost | Docs |
|------|----------|------|------|
| OSV Scanner | SCA | Free | https://google.github.io/osv-scanner |
| CodeQL | SAST | Free (public) | https://codeql.github.com |
| Semgrep | SAST | Free (OSS) | https://semgrep.dev |
| Docker Scout | Container | Free tier | https://docs.docker.com/scout |
| gitleaks | Secrets | Free | https://gitleaks.io |
| Dependabot | SCA | Free | GitHub native |
| OpenSSF Scorecard | Posture | Free | https://securityscorecards.dev |
| SLSA | Build provenance | Free | https://slsa.dev |
| pip-audit | Python SCA | Free | https://github.com/pypa/pip-audit |
| pnpm audit | Node SCA | Free | Built into pnpm |
| deptry | Python unused deps | Free | https://github.com/fpgmaas/deptry |
| depcheck | Node unused deps | Free | https://github.com/nicedoc/depcheck |
