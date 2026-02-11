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
    rm -rf build/ dist/ *.egg-info 2>/dev/null || true
    @echo '{{ GREEN }}✓ Clean complete{{ NORMAL }}'

[group('dev')]
[windows]
clean:
    Write-Host "Cleaning build artifacts..." -ForegroundColor Yellow
    Get-ChildItem -Recurse -Directory -Filter __pycache__ -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Recurse -Directory -Filter .pytest_cache -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Recurse -Filter *.pyc -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
    Write-Host "✓ Clean complete" -ForegroundColor Green

# ═══════════════════════════════════════════════════════════════════════════════
# PYTHON (Packages & Services)
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
    cd services/analytics && uv run ruff format --check .

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

# Run all tests with coverage
[group('all')]
test-coverage: python-test-coverage

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
    @echo '{{ GREEN }}════════════════════════════════════════{{ NORMAL }}'
    @echo '{{ GREEN }}✓ CI pipeline passed!{{ NORMAL }}'
    @echo '{{ GREEN }}════════════════════════════════════════{{ NORMAL }}'

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

# ═══════════════════════════════════════════════════════════════════════════════
# UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

# Watch Python code and run tests on change
[group('utils')]
watch-python:
    @echo '{{ YELLOW }}Watching Python code...{{ NORMAL }}'
    cd services/analytics && uv run ptw

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
    rg -n "TODO|FIXME" --glob '*.py' --glob '*.md' . || echo '{{ GREEN }}No TODOs found!{{ NORMAL }}'

[group('project')]
[windows]
todo:
    Write-Host "Scanning for TODO/FIXME comments..." -ForegroundColor Yellow
    rg -n "TODO|FIXME" --glob '*.py' --glob '*.md' .

# Count lines of code
[group('project')]
[unix]
loc:
    @echo '{{ YELLOW }}Lines of code:{{ NORMAL }}'
    @echo 'Python:'
    @find packages services plugins -name "*.py" 2>/dev/null | xargs wc -l 2>/dev/null | tail -n 1 || echo '0'

[group('project')]
[windows]
loc:
    Write-Host "Lines of code:" -ForegroundColor Yellow
    Write-Host "Python:"
    (Get-ChildItem -Recurse packages,services,plugins -Filter *.py -ErrorAction SilentlyContinue | Get-Content | Measure-Object -Line).Lines

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

# Fix all auto-fixable issues
[group('advanced')]
fix-all: fmt lint-fix
    @echo '{{ GREEN }}✓ Auto-fixes applied{{ NORMAL }}'

# Clean, check everything
[group('advanced')]
verify: clean check
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
