# justfile - agentic-primitives task runner
# Cross-platform: Linux, macOS, Windows
#
# Usage: just <recipe>
# List recipes: just --list
# Recipe help: just --show <recipe>

# ═══════════════════════════════════════════════════════════════════════════════
# SETTINGS
# ═══════════════════════════════════════════════════════════════════════════════

set shell := ["bash", "-euc"]
set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

# ═══════════════════════════════════════════════════════════════════════════════
# HELP (default)
# ═══════════════════════════════════════════════════════════════════════════════

# Show available recipes
default:
    @just --list --unsorted

# ═══════════════════════════════════════════════════════════════════════════════
# DEVELOPMENT
# ═══════════════════════════════════════════════════════════════════════════════

# Initialize development environment
[group('dev')]
[unix]
init:
    @echo '{{ GREEN }}Initializing development environment...{{ NORMAL }}'
    @command -v rustc >/dev/null 2>&1 || (echo '{{ RED }}Rust not found. Install from https://rustup.rs{{ NORMAL }}' && exit 1)
    @command -v uv >/dev/null 2>&1 || (echo '{{ YELLOW }}Installing uv...{{ NORMAL }}' && curl -LsSf https://astral.sh/uv/install.sh | sh)
    @echo '{{ GREEN }}Installing Rust dependencies...{{ NORMAL }}'
    cd cli && cargo fetch
    @echo '{{ GREEN }}✓ Development environment ready!{{ NORMAL }}'

[group('dev')]
[windows]
init:
    Write-Host "Initializing development environment..." -ForegroundColor Green
    if (-not (Get-Command rustc -ErrorAction SilentlyContinue)) { Write-Host "Rust not found. Install from https://rustup.rs" -ForegroundColor Red; exit 1 }
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { Write-Host "Installing uv..." -ForegroundColor Yellow; irm https://astral.sh/uv/install.ps1 | iex }
    Write-Host "Installing Rust dependencies..." -ForegroundColor Green
    Set-Location cli; cargo fetch; Set-Location ..
    Write-Host "✓ Development environment ready!" -ForegroundColor Green

# Clean build artifacts
[group('dev')]
[unix]
clean:
    @echo '{{ YELLOW }}Cleaning build artifacts...{{ NORMAL }}'
    cd cli && cargo clean
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete 2>/dev/null || true
    rm -rf build/ dist/ *.egg-info 2>/dev/null || true
    @echo '{{ GREEN }}✓ Clean complete{{ NORMAL }}'

[group('dev')]
[windows]
clean:
    Write-Host "Cleaning build artifacts..." -ForegroundColor Yellow
    Set-Location cli; cargo clean; Set-Location ..
    Get-ChildItem -Recurse -Directory -Filter __pycache__ -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Recurse -Directory -Filter .pytest_cache -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Recurse -Filter *.pyc -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
    Write-Host "✓ Clean complete" -ForegroundColor Green

# ═══════════════════════════════════════════════════════════════════════════════
# RUST (CLI)
# ═══════════════════════════════════════════════════════════════════════════════

# Format Rust code
[group('rust')]
rust-fmt:
    @echo '{{ YELLOW }}Formatting Rust code...{{ NORMAL }}'
    cargo fmt --all --manifest-path cli/Cargo.toml
    @echo '{{ GREEN }}✓ Rust formatting complete{{ NORMAL }}'

# Check Rust formatting
[group('rust')]
rust-fmt-check:
    @echo '{{ YELLOW }}Checking Rust formatting...{{ NORMAL }}'
    cargo fmt --all --manifest-path cli/Cargo.toml -- --check

# Lint Rust code with clippy
[group('rust')]
rust-lint:
    @echo '{{ YELLOW }}Linting Rust code...{{ NORMAL }}'
    cargo clippy --all-targets --all-features --manifest-path cli/Cargo.toml -- -D warnings
    @echo '{{ GREEN }}✓ Rust linting complete{{ NORMAL }}'

# Run Rust tests
[group('rust')]
rust-test:
    @echo '{{ YELLOW }}Running Rust tests...{{ NORMAL }}'
    cargo test --all-features --manifest-path cli/Cargo.toml
    @echo '{{ GREEN }}✓ Rust tests passed{{ NORMAL }}'

# Run Rust tests with coverage
[group('rust')]
rust-test-coverage:
    @echo '{{ YELLOW }}Running Rust tests with coverage...{{ NORMAL }}'
    cargo tarpaulin --out Html --output-dir coverage --manifest-path cli/Cargo.toml
    @echo '{{ GREEN }}✓ Coverage report: cli/coverage/index.html{{ NORMAL }}'

# Build Rust CLI (debug)
[group('rust')]
rust-build:
    @echo '{{ YELLOW }}Building Rust CLI (debug)...{{ NORMAL }}'
    cargo build --manifest-path cli/Cargo.toml
    @echo '{{ GREEN }}✓ Build complete: cli/target/debug/agentic-p{{ NORMAL }}'

# Build Rust CLI (release)
[group('rust')]
rust-build-release:
    @echo '{{ YELLOW }}Building Rust CLI (release)...{{ NORMAL }}'
    cargo build --release --manifest-path cli/Cargo.toml
    @echo '{{ GREEN }}✓ Release build: cli/target/release/agentic-p{{ NORMAL }}'

# Check Rust code compiles
[group('rust')]
rust-check:
    @echo '{{ YELLOW }}Checking Rust code...{{ NORMAL }}'
    cargo check --all-features --manifest-path cli/Cargo.toml

# Generate Rust documentation
[group('rust')]
rust-doc:
    @echo '{{ YELLOW }}Generating Rust documentation...{{ NORMAL }}'
    cargo doc --no-deps --open --manifest-path cli/Cargo.toml

# ═══════════════════════════════════════════════════════════════════════════════
# PYTHON (Services & Libraries)
# ═══════════════════════════════════════════════════════════════════════════════

# Format Python code
# Sync all Python package dependencies (required before testing)
[group('python')]
python-sync:
    @echo '{{ YELLOW }}Syncing Python package dependencies...{{ NORMAL }}'
    uv run python scripts/python_qa.py sync
    @echo '{{ GREEN }}✓ Python dependencies synced{{ NORMAL }}'

[group('python')]
python-fmt:
    @echo '{{ YELLOW }}Formatting Python code...{{ NORMAL }}'
    cd services/analytics && uv run ruff format .
    cd lib/python/agentic_logging && uv run ruff format .
    @echo '{{ GREEN }}✓ Python formatting complete{{ NORMAL }}'

# Check Python formatting
[group('python')]
python-fmt-check:
    @echo '{{ YELLOW }}Checking Python formatting...{{ NORMAL }}'
    cd services/analytics && uv run ruff format --check .
    cd lib/python/agentic_logging && uv run ruff format --check .

# Lint Python code (all packages via cross-platform script)
[group('python')]
python-lint:
    @echo '{{ YELLOW }}Linting Python code...{{ NORMAL }}'
    uv run python scripts/python_qa.py lint
    @echo '{{ GREEN }}✓ Python linting complete{{ NORMAL }}'

# Lint and auto-fix Python code (all packages)
[group('python')]
python-lint-fix:
    @echo '{{ YELLOW }}Linting and fixing Python code...{{ NORMAL }}'
    uv run python scripts/python_qa.py lint --fix
    @echo '{{ GREEN }}✓ Python lint fixes applied{{ NORMAL }}'

# Type check Python code
[group('python')]
python-typecheck:
    @echo '{{ YELLOW }}Type checking Python code...{{ NORMAL }}'
    cd services/analytics && uv run mypy . || true
    @echo '{{ GREEN }}✓ Python type checking complete{{ NORMAL }}'

# Run Python tests (all packages via cross-platform script)
[group('python')]
python-test:
    @echo '{{ YELLOW }}Running Python tests...{{ NORMAL }}'
    uv run python scripts/python_qa.py test
    @echo '{{ GREEN }}✓ Python tests passed{{ NORMAL }}'

# Run Python integration tests (requires Docker)
[group('python')]
python-test-integration:
    @echo '{{ YELLOW }}Running Python integration tests...{{ NORMAL }}'
    uv run python scripts/python_qa.py test --integration
    @echo '{{ GREEN }}✓ Python integration tests passed{{ NORMAL }}'

# Run Python tests with coverage
[group('python')]
python-test-coverage:
    @echo '{{ YELLOW }}Running Python tests with coverage...{{ NORMAL }}'
    cd services/analytics && uv run pytest --cov=. --cov-report=html --cov-report=term
    @echo '{{ GREEN }}✓ Coverage report: services/analytics/htmlcov/index.html{{ NORMAL }}'

# ═══════════════════════════════════════════════════════════════════════════════
# COMBINED OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════════

# Format all code (Rust + Python)
[group('all')]
fmt: rust-fmt python-fmt

# Check all formatting
[group('all')]
fmt-check: rust-fmt-check python-fmt-check

# Lint all code
[group('all')]
lint: rust-lint python-lint

# Auto-fix linting issues
[group('all')]
lint-fix: python-lint-fix

# Run all tests
[group('all')]
test: rust-test python-test

# Run all tests with coverage
[group('all')]
test-coverage: rust-test-coverage python-test-coverage

# Build all components
[group('all')]
build: rust-build

# Build release versions
[group('all')]
build-release: rust-build-release

# Run type checks
[group('all')]
typecheck: python-typecheck

# ═══════════════════════════════════════════════════════════════════════════════
# QUALITY ASSURANCE
# ═══════════════════════════════════════════════════════════════════════════════

# Run all QA checks (format check, lint, typecheck, test)
[group('qa')]
qa:
    @echo '{{ GREEN }}════════════════════════════════════════{{ NORMAL }}'
    @echo '{{ GREEN }}Running Full QA Suite{{ NORMAL }}'
    @echo '{{ GREEN }}════════════════════════════════════════{{ NORMAL }}'
    just fmt-check
    @echo ''
    just lint
    @echo ''
    just typecheck
    @echo ''
    just test
    @echo ''
    @echo '{{ GREEN }}════════════════════════════════════════{{ NORMAL }}'
    @echo '{{ GREEN }}✓ All QA checks passed!{{ NORMAL }}'
    @echo '{{ GREEN }}════════════════════════════════════════{{ NORMAL }}'

# Run QA with auto-fixes
[group('qa')]
qa-fix:
    @echo '{{ GREEN }}Running QA with auto-fixes...{{ NORMAL }}'
    just fmt
    just lint-fix
    just test

# Alias for qa
[group('qa')]
check: qa

# Alias for qa-fix
[group('qa')]
check-fix: qa-fix

# CI pipeline
[group('qa')]
ci:
    @echo '{{ GREEN }}════════════════════════════════════════{{ NORMAL }}'
    @echo '{{ GREEN }}Running CI Pipeline{{ NORMAL }}'
    @echo '{{ GREEN }}════════════════════════════════════════{{ NORMAL }}'
    just fmt-check
    just lint
    just typecheck
    just test
    just build-release
    @echo '{{ GREEN }}════════════════════════════════════════{{ NORMAL }}'
    @echo '{{ GREEN }}✓ CI pipeline passed!{{ NORMAL }}'
    @echo '{{ GREEN }}════════════════════════════════════════{{ NORMAL }}'

# ═══════════════════════════════════════════════════════════════════════════════
# VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════

# Validate primitives repository (v2 only - transitional CLI doesn't support v1)
[group('validation')]
validate:
    @echo '{{ YELLOW }}Validating v2 primitives...{{ NORMAL }}'
    cd cli && cargo run -- validate ../primitives/v2 || echo '{{ YELLOW }}Note: V1 primitives skipped (use cli/v1 for V1 validation){{ NORMAL }}'
    @echo '{{ GREEN }}✓ V2 validation passed{{ NORMAL }}'

# Validate all version hashes
[group('validation')]
validate-hashes:
    @echo '{{ YELLOW }}Validating version hashes...{{ NORMAL }}'
    cd cli && cargo run -- validate ../primitives --check-hashes
    @echo '{{ GREEN }}✓ Hash validation passed{{ NORMAL }}'

# ═══════════════════════════════════════════════════════════════════════════════
# INSTALLATION
# ═══════════════════════════════════════════════════════════════════════════════

# Install CLI to system
[group('install')]
install: build-release
    @echo '{{ YELLOW }}Installing agentic-p CLI...{{ NORMAL }}'
    cd cli && cargo install --path .
    @echo '{{ GREEN }}✓ Installed{{ NORMAL }}'

# Uninstall CLI from system
[group('install')]
uninstall:
    @echo '{{ YELLOW }}Uninstalling agentic-p CLI...{{ NORMAL }}'
    cargo uninstall agentic-p || true
    @echo '{{ GREEN }}✓ Uninstalled{{ NORMAL }}'

# ═══════════════════════════════════════════════════════════════════════════════
# PLUGINS
# ═══════════════════════════════════════════════════════════════════════════════

# List available plugins with versions
[group('plugins')]
[unix]
plugin-list:
    @python3 scripts/install_plugin.py list

[group('plugins')]
[windows]
plugin-list:
    python scripts/install_plugin.py list

# Install a plugin (use --global for global scope)
[group('plugins')]
[unix]
plugin-install name *FLAGS:
    @python3 scripts/install_plugin.py install {{ name }} {{ FLAGS }}

[group('plugins')]
[windows]
plugin-install name *FLAGS:
    python scripts/install_plugin.py install {{ name }} {{ FLAGS }}

# Uninstall a plugin (use --global for global scope)
[group('plugins')]
[unix]
plugin-uninstall name *FLAGS:
    @python3 scripts/install_plugin.py uninstall {{ name }} {{ FLAGS }}

[group('plugins')]
[windows]
plugin-uninstall name *FLAGS:
    python scripts/install_plugin.py uninstall {{ name }} {{ FLAGS }}

# Show plugin commands help
[group('plugins')]
[unix]
plugin-help:
    @echo '{{ GREEN }}Plugin Commands:{{ NORMAL }}'
    @echo ''
    @echo '  just plugin-list                  List available plugins with versions'
    @echo '  just plugin-install <name>        Install plugin to current project'
    @echo '  just plugin-install <name> --global  Install plugin globally'
    @echo '  just plugin-uninstall <name>      Uninstall from current project'
    @echo '  just plugin-uninstall <name> --global  Uninstall globally'
    @echo '  just plugin-validate              Validate all plugin manifests'
    @echo ''
    @echo '{{ YELLOW }}Examples:{{ NORMAL }}'
    @echo '  just plugin-install sdlc --global    Install SDLC security hooks globally'
    @echo '  just plugin-install workspace        Install workspace hooks to project'
    @echo '  just plugin-list                     See all 5 available plugins'

[group('plugins')]
[windows]
plugin-help:
    Write-Host "Plugin Commands:" -ForegroundColor Green
    Write-Host ""
    Write-Host "  just plugin-list                  List available plugins with versions"
    Write-Host "  just plugin-install <name>        Install plugin to current project"
    Write-Host "  just plugin-install <name> --global  Install plugin globally"
    Write-Host "  just plugin-uninstall <name>      Uninstall from current project"
    Write-Host "  just plugin-uninstall <name> --global  Uninstall globally"
    Write-Host "  just plugin-validate              Validate all plugin manifests"
    Write-Host ""
    Write-Host "Examples:" -ForegroundColor Yellow
    Write-Host "  just plugin-install sdlc --global    Install SDLC security hooks globally"
    Write-Host "  just plugin-install workspace        Install workspace hooks to project"
    Write-Host "  just plugin-list                     See all 5 available plugins"

# Validate all plugin manifests and structure
[group('plugins')]
[unix]
plugin-validate:
    @echo '{{ YELLOW }}Validating plugins...{{ NORMAL }}'
    @python3 scripts/validate_plugins.py
    @echo '{{ GREEN }}✓ Plugin validation complete{{ NORMAL }}'

[group('plugins')]
[windows]
plugin-validate:
    Write-Host "Validating plugins..." -ForegroundColor Yellow
    python scripts/validate_plugins.py
    Write-Host "Plugin validation complete" -ForegroundColor Green

# ═══════════════════════════════════════════════════════════════════════════════
# DOCUMENTATION
# ═══════════════════════════════════════════════════════════════════════════════

# Start docs site development server (Fumadocs)
[group('docs')]
[unix]
docs:
    @echo '{{ YELLOW }}Starting docs site (Fumadocs) on http://localhost:4321...{{ NORMAL }}'
    cd docs-site-fuma && [ -d node_modules ] || npm install --silent && npm run dev -- -p 4321

[group('docs')]
[windows]
docs:
    Write-Host "Starting docs site (Fumadocs) on http://localhost:4321..." -ForegroundColor Yellow
    Set-Location docs-site-fuma; if (!(Test-Path node_modules)) { npm install --silent }; npm run dev -- -p 4321

# Build docs site for production
[group('docs')]
[unix]
docs-build:
    @echo '{{ YELLOW }}Building docs site...{{ NORMAL }}'
    cd docs-site-fuma && [ -d node_modules ] || npm install --silent && npm run build
    @echo '{{ GREEN }}✓ Docs site built{{ NORMAL }}'

[group('docs')]
[windows]
docs-build:
    Write-Host "Building docs site..." -ForegroundColor Yellow
    Set-Location docs-site-fuma; if (!(Test-Path node_modules)) { npm install --silent }; npm run build
    Write-Host "✓ Docs site built" -ForegroundColor Green

# Generate Rust API documentation
[group('docs')]
docs-rust: rust-doc
    @echo '{{ GREEN }}✓ Rust documentation generated{{ NORMAL }}'

# Serve Rust documentation locally
[group('docs')]
[unix]
docs-rust-serve:
    @echo '{{ YELLOW }}Serving Rust documentation...{{ NORMAL }}'
    cd cli && cargo doc --no-deps && python3 -m http.server --directory target/doc 8080

[group('docs')]
[windows]
docs-rust-serve:
    Write-Host "Serving Rust documentation..." -ForegroundColor Yellow
    Set-Location cli; cargo doc --no-deps; python -m http.server --directory target/doc 8080

# ═══════════════════════════════════════════════════════════════════════════════
# UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

# Watch Rust code and run tests on change
[group('utils')]
watch-rust:
    @echo '{{ YELLOW }}Watching Rust code...{{ NORMAL }}'
    cd cli && cargo watch -x test

# Watch Python code and run tests on change
[group('utils')]
watch-python:
    @echo '{{ YELLOW }}Watching Python code...{{ NORMAL }}'
    cd services/analytics && uv run ptw

# Run benchmarks
[group('utils')]
bench:
    @echo '{{ YELLOW }}Running benchmarks...{{ NORMAL }}'
    cd cli && cargo bench

# Show version information
[group('utils')]
[unix]
version:
    @echo '{{ GREEN }}Rust version:{{ NORMAL }}'
    rustc --version
    cargo --version
    @echo ''
    @echo '{{ GREEN }}Python version:{{ NORMAL }}'
    uv --version
    python3 --version || python --version
    @echo ''
    @echo '{{ GREEN }}Just version:{{ NORMAL }}'
    just --version

[group('utils')]
[windows]
version:
    Write-Host "Rust version:" -ForegroundColor Green
    rustc --version
    cargo --version
    Write-Host ""
    Write-Host "Python version:" -ForegroundColor Green
    uv --version
    python --version
    Write-Host ""
    Write-Host "Just version:" -ForegroundColor Green
    just --version

# Check for outdated dependencies
[group('utils')]
deps-check:
    @echo '{{ YELLOW }}Checking Rust dependencies...{{ NORMAL }}'
    cd cli && cargo outdated || echo 'Install: cargo install cargo-outdated'

# Update dependencies
[group('utils')]
deps-update:
    @echo '{{ YELLOW }}Updating Rust dependencies...{{ NORMAL }}'
    cd cli && cargo update
    @echo '{{ GREEN }}✓ Dependencies updated{{ NORMAL }}'

# ═══════════════════════════════════════════════════════════════════════════════
# GIT HOOKS
# ═══════════════════════════════════════════════════════════════════════════════

# Install git pre-commit hooks
[group('git')]
[unix]
git-hooks-install:
    @echo '{{ YELLOW }}Installing git hooks...{{ NORMAL }}'
    printf '#!/bin/sh\njust qa\n' > .git/hooks/pre-commit
    chmod +x .git/hooks/pre-commit
    @echo '{{ GREEN }}✓ Pre-commit hook installed (runs just qa){{ NORMAL }}'

[group('git')]
[windows]
git-hooks-install:
    Write-Host "Installing git hooks..." -ForegroundColor Yellow
    Set-Content -Path .git/hooks/pre-commit -Value "#!/bin/sh`njust qa"
    Write-Host "✓ Pre-commit hook installed" -ForegroundColor Green

# Uninstall git hooks
[group('git')]
[unix]
git-hooks-uninstall:
    @echo '{{ YELLOW }}Uninstalling git hooks...{{ NORMAL }}'
    rm -f .git/hooks/pre-commit
    @echo '{{ GREEN }}✓ Pre-commit hook uninstalled{{ NORMAL }}'

[group('git')]
[windows]
git-hooks-uninstall:
    Write-Host "Uninstalling git hooks..." -ForegroundColor Yellow
    Remove-Item .git/hooks/pre-commit -ErrorAction SilentlyContinue
    Write-Host "✓ Pre-commit hook uninstalled" -ForegroundColor Green

# ═══════════════════════════════════════════════════════════════════════════════
# PROJECT MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

# Show TODO/FIXME comments
[group('project')]
[unix]
todo:
    @echo '{{ YELLOW }}Scanning for TODO/FIXME comments...{{ NORMAL }}'
    rg -n "TODO|FIXME" --glob '*.rs' --glob '*.py' --glob '*.md' . || echo '{{ GREEN }}No TODOs found!{{ NORMAL }}'

[group('project')]
[windows]
todo:
    Write-Host "Scanning for TODO/FIXME comments..." -ForegroundColor Yellow
    rg -n "TODO|FIXME" --glob '*.rs' --glob '*.py' --glob '*.md' .

# Count lines of code
[group('project')]
[unix]
loc:
    @echo '{{ YELLOW }}Lines of code:{{ NORMAL }}'
    @echo 'Rust:'
    @find cli/src -name "*.rs" | xargs wc -l | tail -n 1
    @echo 'Python:'
    @find services lib -name "*.py" 2>/dev/null | xargs wc -l 2>/dev/null | tail -n 1 || echo '0'

[group('project')]
[windows]
loc:
    Write-Host "Lines of code:" -ForegroundColor Yellow
    Write-Host "Rust:"
    (Get-ChildItem -Recurse cli/src -Filter *.rs | Get-Content | Measure-Object -Line).Lines
    Write-Host "Python:"
    (Get-ChildItem -Recurse services,lib -Filter *.py -ErrorAction SilentlyContinue | Get-Content | Measure-Object -Line).Lines

# ═══════════════════════════════════════════════════════════════════════════════
# DOCKER / WORKSPACE IMAGES
# ═══════════════════════════════════════════════════════════════════════════════

# Build a workspace provider image (e.g., claude-cli)
[group('docker')]
[unix]
build-provider provider:
    @echo '{{ YELLOW }}Building provider: {{ provider }}{{ NORMAL }}'
    uv run scripts/build-provider.py {{ provider }}
    @echo '{{ GREEN }}✓ Provider image built{{ NORMAL }}'

[group('docker')]
[windows]
build-provider provider:
    Write-Host "Building provider: {{ provider }}" -ForegroundColor Yellow
    uv run scripts/build-provider.py {{ provider }}
    Write-Host "✓ Provider image built" -ForegroundColor Green

# Build Claude CLI workspace image
[group('docker')]
build-workspace-claude-cli: (build-provider "claude-cli")

# Stage provider build context only (no docker build)
[group('docker')]
[unix]
stage-provider provider:
    @echo '{{ YELLOW }}Staging provider: {{ provider }}{{ NORMAL }}'
    uv run scripts/build-provider.py {{ provider }} --stage-only
    @echo '{{ GREEN }}✓ Staged to build/{{ provider }}/{{ NORMAL }}'

# List available workspace providers
[group('docker')]
[unix]
list-providers:
    @echo '{{ YELLOW }}Available workspace providers:{{ NORMAL }}'
    @ls -1 providers/workspaces/ | grep -v README

# ═══════════════════════════════════════════════════════════════════════════════
# ADVANCED
# ═══════════════════════════════════════════════════════════════════════════════

# Security audit
[group('advanced')]
audit:
    @echo '{{ YELLOW }}Running security audit...{{ NORMAL }}'
    cd cli && cargo audit || echo 'Install: cargo install cargo-audit'

# Fix all auto-fixable issues
[group('advanced')]
fix-all: fmt lint-fix
    @echo '{{ GREEN }}✓ Auto-fixes applied{{ NORMAL }}'

# Clean, check, and build everything
[group('advanced')]
verify: clean check build
    @echo '{{ GREEN }}✓ Full verification complete!{{ NORMAL }}'

# ═══════════════════════════════════════════════════════════════════════════════
# EVALUATION / PLAYGROUND
# ═══════════════════════════════════════════════════════════════════════════════

# Run playground eval with a specific scenario and task
[group('eval')]
[unix]
eval scenario task:
    @echo '{{ YELLOW }}Running eval: {{ scenario }}{{ NORMAL }}'
    cd playground && uv run python run.py "{{ task }}" --scenario {{ scenario }} --live

[group('eval')]
[windows]
eval scenario task:
    Write-Host "Running eval: {{ scenario }}" -ForegroundColor Yellow
    Set-Location playground; uv run python run.py "{{ task }}" --scenario {{ scenario }} --live; Set-Location ..

# Run subagent concurrency test
[group('eval')]
[unix]
eval-subagent:
    @echo '{{ YELLOW }}Running subagent concurrency test...{{ NORMAL }}'
    cd playground && uv run python run.py "$$(cat prompts/subagent-test.md)" --scenario subagent-concurrent --live

[group('eval')]
[windows]
eval-subagent:
    Write-Host "Running subagent concurrency test..." -ForegroundColor Yellow
    Set-Location playground; uv run python run.py (Get-Content prompts/subagent-test.md -Raw) --scenario subagent-concurrent --live; Set-Location ..

# Run a quick task with Haiku model
[group('eval')]
[unix]
eval-quick task:
    @echo '{{ YELLOW }}Running quick eval with Haiku...{{ NORMAL }}'
    cd playground && uv run python run.py "{{ task }}" --scenario quick-haiku --live

[group('eval')]
[windows]
eval-quick task:
    Write-Host "Running quick eval with Haiku..." -ForegroundColor Yellow
    Set-Location playground; uv run python run.py "{{ task }}" --scenario quick-haiku --live; Set-Location ..

# List available eval scenarios
[group('eval')]
[unix]
eval-list:
    @echo '{{ YELLOW }}Available eval scenarios:{{ NORMAL }}'
    cd playground && uv run python run.py scenarios

[group('eval')]
[windows]
eval-list:
    Write-Host "Available eval scenarios:" -ForegroundColor Yellow
    Set-Location playground; uv run python run.py scenarios; Set-Location ..

# Run playground tests
[group('eval')]
eval-test:
    @echo '{{ YELLOW }}Running playground tests...{{ NORMAL }}'
    cd playground && uv run pytest tests/ -v
    @echo '{{ GREEN }}✓ Playground tests passed{{ NORMAL }}'
