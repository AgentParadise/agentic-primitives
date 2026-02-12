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
    @command -v uv >/dev/null 2>&1 || (echo '{{ YELLOW }}Installing uv...{{ NORMAL }}' && curl -LsSf https://astral.sh/uv/install.sh | sh)
    @echo '{{ GREEN }}Syncing Python dependencies...{{ NORMAL }}'
    uv run python scripts/python_qa.py sync
    @echo '{{ GREEN }}✓ Development environment ready!{{ NORMAL }}'

[group('dev')]
[windows]
init:
    Write-Host "Initializing development environment..." -ForegroundColor Green
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { Write-Host "Installing uv..." -ForegroundColor Yellow; irm https://astral.sh/uv/install.ps1 | iex }
    Write-Host "Syncing Python dependencies..." -ForegroundColor Green
    uv run python scripts/python_qa.py sync
    Write-Host "✓ Development environment ready!" -ForegroundColor Green

# Clean build artifacts
[group('dev')]
[unix]
clean:
    @echo '{{ YELLOW }}Cleaning build artifacts...{{ NORMAL }}'
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete 2>/dev/null || true
    @echo '{{ GREEN }}✓ Clean complete{{ NORMAL }}'

[group('dev')]
[windows]
clean:
    Write-Host "Cleaning build artifacts..." -ForegroundColor Yellow
    Get-ChildItem -Recurse -Directory -Filter __pycache__ -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Recurse -Directory -Filter .pytest_cache -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Recurse -Filter *.pyc -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
    Write-Host "✓ Clean complete" -ForegroundColor Green

# ═══════════════════════════════════════════════════════════════════════════════
# PYTHON (Libraries)
# ═══════════════════════════════════════════════════════════════════════════════

# Sync all Python package dependencies (required before testing)
[group('python')]
python-sync:
    @echo '{{ YELLOW }}Syncing Python package dependencies...{{ NORMAL }}'
    uv run python scripts/python_qa.py sync
    @echo '{{ GREEN }}✓ Python dependencies synced{{ NORMAL }}'

# Format Python code
[group('python')]
python-fmt:
    @echo '{{ YELLOW }}Formatting Python code...{{ NORMAL }}'
    uv run python scripts/python_qa.py lint --fix
    @echo '{{ GREEN }}✓ Python formatting complete{{ NORMAL }}'

# Check Python formatting
[group('python')]
python-fmt-check:
    @echo '{{ YELLOW }}Checking Python formatting...{{ NORMAL }}'
    uv run python scripts/python_qa.py lint

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

# ═══════════════════════════════════════════════════════════════════════════════
# COMBINED OPERATIONS
# ═══════════════════════════════════════════════════════════════════════════════

# Format all code
[group('all')]
fmt: python-fmt

# Check all formatting
[group('all')]
fmt-check: python-fmt-check

# Lint all code
[group('all')]
lint: python-lint

# Auto-fix linting issues
[group('all')]
lint-fix: python-lint-fix

# Run all tests
[group('all')]
test: python-test

# ═══════════════════════════════════════════════════════════════════════════════
# QUALITY ASSURANCE
# ═══════════════════════════════════════════════════════════════════════════════

# Run all QA checks (format check, lint, test)
[group('qa')]
qa:
    @echo '{{ GREEN }}════════════════════════════════════════{{ NORMAL }}'
    @echo '{{ GREEN }}Running Full QA Suite{{ NORMAL }}'
    @echo '{{ GREEN }}════════════════════════════════════════{{ NORMAL }}'
    just fmt-check
    @echo ''
    just lint
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
    just test
    @echo '{{ GREEN }}════════════════════════════════════════{{ NORMAL }}'
    @echo '{{ GREEN }}✓ CI pipeline passed!{{ NORMAL }}'
    @echo '{{ GREEN }}════════════════════════════════════════{{ NORMAL }}'

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
# UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

# Show version information
[group('utils')]
[unix]
version:
    @echo '{{ GREEN }}Python version:{{ NORMAL }}'
    uv --version
    python3 --version || python --version
    @echo ''
    @echo '{{ GREEN }}Just version:{{ NORMAL }}'
    just --version

[group('utils')]
[windows]
version:
    Write-Host "Python version:" -ForegroundColor Green
    uv --version
    python --version
    Write-Host ""
    Write-Host "Just version:" -ForegroundColor Green
    just --version

# Show TODO/FIXME comments
[group('utils')]
[unix]
todo:
    @echo '{{ YELLOW }}Scanning for TODO/FIXME comments...{{ NORMAL }}'
    rg -n "TODO|FIXME" --glob '*.py' --glob '*.md' . || echo '{{ GREEN }}No TODOs found!{{ NORMAL }}'

[group('utils')]
[windows]
todo:
    Write-Host "Scanning for TODO/FIXME comments..." -ForegroundColor Yellow
    rg -n "TODO|FIXME" --glob '*.py' --glob '*.md' .

# Count lines of code
[group('utils')]
[unix]
loc:
    @echo '{{ YELLOW }}Lines of code:{{ NORMAL }}'
    @echo 'Python:'
    @find lib plugins -name "*.py" 2>/dev/null | xargs wc -l 2>/dev/null | tail -n 1 || echo '0'

[group('utils')]
[windows]
loc:
    Write-Host "Lines of code:" -ForegroundColor Yellow
    Write-Host "Python:"
    (Get-ChildItem -Recurse lib,plugins -Filter *.py -ErrorAction SilentlyContinue | Get-Content | Measure-Object -Line).Lines

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
# ADVANCED
# ═══════════════════════════════════════════════════════════════════════════════

# Fix all auto-fixable issues
[group('advanced')]
fix-all: fmt lint-fix
    @echo '{{ GREEN }}✓ Auto-fixes applied{{ NORMAL }}'

# Clean and check everything
[group('advanced')]
verify: clean check
    @echo '{{ GREEN }}✓ Full verification complete!{{ NORMAL }}'
