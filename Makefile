.PHONY: help
.DEFAULT_GOAL := help

# Colors for output
GREEN  := \033[0;32m
YELLOW := \033[0;33m
RED    := \033[0;31m
NC     := \033[0m # No Color

##@ Help

help: ## Display this help message
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Development

init: ## Initialize development environment
	@echo "$(GREEN)Initializing development environment...$(NC)"
	@command -v rustc >/dev/null 2>&1 || (echo "$(RED)Rust not found. Install from https://rustup.rs$(NC)" && exit 1)
	@command -v uv >/dev/null 2>&1 || (echo "$(YELLOW)Installing uv...$(NC)" && curl -LsSf https://astral.sh/uv/install.sh | sh)
	@echo "$(GREEN)Installing Rust dependencies...$(NC)"
	@cd cli && cargo fetch
	@echo "$(GREEN)Setting up Python environment...$(NC)"
	@cd hooks && uv venv && uv pip install -e ".[dev]"
	@echo "$(GREEN)✓ Development environment ready!$(NC)"

clean: ## Clean build artifacts
	@echo "$(YELLOW)Cleaning build artifacts...$(NC)"
	@cd cli && cargo clean
	@find . -type d -name target -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete
	@rm -rf build/ dist/ *.egg-info
	@echo "$(GREEN)✓ Clean complete$(NC)"

##@ Rust (CLI)

rust-fmt: ## Format Rust code
	@echo "$(YELLOW)Formatting Rust code...$(NC)"
	@cd cli && cargo fmt --all
	@echo "$(GREEN)✓ Rust formatting complete$(NC)"

rust-fmt-check: ## Check Rust code formatting
	@echo "$(YELLOW)Checking Rust code formatting...$(NC)"
	@cd cli && cargo fmt --all -- --check

rust-lint: ## Lint Rust code with clippy
	@echo "$(YELLOW)Linting Rust code...$(NC)"
	@cd cli && cargo clippy --all-targets --all-features -- -D warnings
	@echo "$(GREEN)✓ Rust linting complete$(NC)"

rust-test: ## Run Rust tests
	@echo "$(YELLOW)Running Rust tests...$(NC)"
	@cd cli && cargo test --all-features
	@echo "$(GREEN)✓ Rust tests passed$(NC)"

rust-test-coverage: ## Run Rust tests with coverage
	@echo "$(YELLOW)Running Rust tests with coverage...$(NC)"
	@cd cli && cargo tarpaulin --out Html --output-dir coverage
	@echo "$(GREEN)✓ Coverage report: cli/coverage/index.html$(NC)"

rust-build: ## Build Rust CLI (debug)
	@echo "$(YELLOW)Building Rust CLI (debug)...$(NC)"
	@cd cli && cargo build
	@echo "$(GREEN)✓ Build complete: cli/target/debug/agentic-primitives$(NC)"

rust-build-release: ## Build Rust CLI (release)
	@echo "$(YELLOW)Building Rust CLI (release)...$(NC)"
	@cd cli && cargo build --release
	@echo "$(GREEN)✓ Release build complete: cli/target/release/agentic-primitives$(NC)"

rust-check: ## Check Rust code compiles
	@echo "$(YELLOW)Checking Rust code...$(NC)"
	@cd cli && cargo check --all-features

rust-doc: ## Generate Rust documentation
	@echo "$(YELLOW)Generating Rust documentation...$(NC)"
	@cd cli && cargo doc --no-deps --open

##@ Python (Hooks)

python-fmt: ## Format Python code with black and ruff
	@echo "$(YELLOW)Formatting Python code...$(NC)"
	@cd hooks && uv run black .
	@cd hooks && uv run ruff format .
	@echo "$(GREEN)✓ Python formatting complete$(NC)"

python-fmt-check: ## Check Python code formatting
	@echo "$(YELLOW)Checking Python code formatting...$(NC)"
	@cd hooks && uv run black --check .
	@cd hooks && uv run ruff format --check .

python-lint: ## Lint Python code with ruff
	@echo "$(YELLOW)Linting Python code...$(NC)"
	@cd hooks && uv run ruff check .
	@echo "$(GREEN)✓ Python linting complete$(NC)"

python-lint-fix: ## Lint and auto-fix Python code
	@echo "$(YELLOW)Linting and fixing Python code...$(NC)"
	@cd hooks && uv run ruff check --fix .
	@echo "$(GREEN)✓ Python lint fixes applied$(NC)"

python-typecheck: ## Type check Python code with mypy
	@echo "$(YELLOW)Type checking Python code...$(NC)"
	@cd hooks && uv run mypy .
	@echo "$(GREEN)✓ Python type checking complete$(NC)"

python-test: ## Run Python tests
	@echo "$(YELLOW)Running Python tests...$(NC)"
	@cd hooks && uv run pytest -v
	@echo "$(GREEN)✓ Python tests passed$(NC)"

python-test-coverage: ## Run Python tests with coverage
	@echo "$(YELLOW)Running Python tests with coverage...$(NC)"
	@cd hooks && uv run pytest --cov=. --cov-report=html --cov-report=term
	@echo "$(GREEN)✓ Coverage report: hooks/htmlcov/index.html$(NC)"

##@ Combined Operations

fmt: rust-fmt python-fmt ## Format all code (Rust + Python)

fmt-check: rust-fmt-check python-fmt-check ## Check all code formatting

lint: rust-lint python-lint ## Lint all code (Rust + Python)

lint-fix: python-lint-fix ## Auto-fix linting issues where possible

test: rust-test python-test ## Run all tests (Rust + Python)

test-coverage: rust-test-coverage python-test-coverage ## Generate coverage reports

build: rust-build ## Build all components

build-release: rust-build-release ## Build release versions

typecheck: python-typecheck ## Run all type checks

##@ Quality Assurance

qa: ## Run all QA checks (format check, lint, typecheck, test)
	@echo "$(GREEN)========================================$(NC)"
	@echo "$(GREEN)Running Full QA Suite$(NC)"
	@echo "$(GREEN)========================================$(NC)"
	@$(MAKE) fmt-check
	@echo ""
	@$(MAKE) lint
	@echo ""
	@$(MAKE) typecheck
	@echo ""
	@$(MAKE) test
	@echo ""
	@echo "$(GREEN)========================================$(NC)"
	@echo "$(GREEN)✓ All QA checks passed!$(NC)"
	@echo "$(GREEN)========================================$(NC)"

qa-fix: ## Run QA checks with auto-fixes
	@echo "$(GREEN)Running QA with auto-fixes...$(NC)"
	@$(MAKE) fmt
	@$(MAKE) lint-fix
	@$(MAKE) test

check: qa ## Alias for 'qa' target

check-fix: qa-fix ## Alias for 'qa-fix' target

ci: ## CI pipeline (format check, lint, test, build)
	@echo "$(GREEN)========================================$(NC)"
	@echo "$(GREEN)Running CI Pipeline$(NC)"
	@echo "$(GREEN)========================================$(NC)"
	@$(MAKE) fmt-check
	@$(MAKE) lint
	@$(MAKE) typecheck
	@$(MAKE) test
	@$(MAKE) build-release
	@echo "$(GREEN)========================================$(NC)"
	@echo "$(GREEN)✓ CI pipeline passed!$(NC)"
	@echo "$(GREEN)========================================$(NC)"

##@ Validation

validate: ## Run agentic-primitives validate on repository
	@echo "$(YELLOW)Validating primitives repository...$(NC)"
	@cd cli && cargo run -- validate
	@echo "$(GREEN)✓ Validation passed$(NC)"

validate-hashes: ## Validate all version hashes
	@echo "$(YELLOW)Validating version hashes...$(NC)"
	@cd cli && cargo run -- validate --check-hashes
	@echo "$(GREEN)✓ Hash validation passed$(NC)"

##@ Installation

install: build-release ## Install CLI to system
	@echo "$(YELLOW)Installing agentic-primitives CLI...$(NC)"
	@cd cli && cargo install --path .
	@echo "$(GREEN)✓ Installed to $(shell cargo install --list | grep agentic-primitives)$(NC)"

uninstall: ## Uninstall CLI from system
	@echo "$(YELLOW)Uninstalling agentic-primitives CLI...$(NC)"
	@cargo uninstall agentic-primitives || true
	@echo "$(GREEN)✓ Uninstalled$(NC)"

##@ Documentation

docs: ## Generate all documentation
	@echo "$(YELLOW)Generating documentation...$(NC)"
	@$(MAKE) rust-doc
	@echo "$(GREEN)✓ Documentation generated$(NC)"

docs-serve: ## Serve documentation locally
	@echo "$(YELLOW)Serving documentation...$(NC)"
	@cd cli && cargo doc --no-deps && python3 -m http.server --directory target/doc 8080

##@ Utilities

watch-rust: ## Watch Rust code and run tests on change
	@echo "$(YELLOW)Watching Rust code...$(NC)"
	@cd cli && cargo watch -x test

watch-python: ## Watch Python code and run tests on change
	@echo "$(YELLOW)Watching Python code...$(NC)"
	@cd hooks && uv run ptw

bench: ## Run benchmarks
	@echo "$(YELLOW)Running benchmarks...$(NC)"
	@cd cli && cargo bench

version: ## Show version information
	@echo "$(GREEN)Rust version:$(NC)"
	@rustc --version
	@cargo --version
	@echo ""
	@echo "$(GREEN)Python version:$(NC)"
	@uv --version
	@python3 --version

deps-check: ## Check for outdated dependencies
	@echo "$(YELLOW)Checking Rust dependencies...$(NC)"
	@cd cli && cargo outdated || echo "Install cargo-outdated: cargo install cargo-outdated"
	@echo ""
	@echo "$(YELLOW)Checking Python dependencies...$(NC)"
	@cd hooks && uv pip list --outdated

deps-update: ## Update dependencies
	@echo "$(YELLOW)Updating Rust dependencies...$(NC)"
	@cd cli && cargo update
	@echo "$(YELLOW)Updating Python dependencies...$(NC)"
	@cd hooks && uv pip install --upgrade -e ".[dev]"
	@echo "$(GREEN)✓ Dependencies updated$(NC)"

##@ Git Hooks

git-hooks-install: ## Install git pre-commit hooks
	@echo "$(YELLOW)Installing git hooks...$(NC)"
	@echo '#!/bin/sh\nmake qa' > .git/hooks/pre-commit
	@chmod +x .git/hooks/pre-commit
	@echo "$(GREEN)✓ Pre-commit hook installed (runs 'make qa')$(NC)"

git-hooks-uninstall: ## Uninstall git pre-commit hooks
	@echo "$(YELLOW)Uninstalling git hooks...$(NC)"
	@rm -f .git/hooks/pre-commit
	@echo "$(GREEN)✓ Pre-commit hook uninstalled$(NC)"

##@ Project Management

todo: ## Show TODO/FIXME comments in code
	@echo "$(YELLOW)Scanning for TODO/FIXME comments...$(NC)"
	@rg -n "TODO|FIXME" --glob '*.rs' --glob '*.py' --glob '*.md' . || echo "$(GREEN)No TODOs found!$(NC)"

loc: ## Count lines of code
	@echo "$(YELLOW)Lines of code:$(NC)"
	@echo "Rust:"
	@find cli/src -name "*.rs" | xargs wc -l | tail -n 1
	@echo "Python:"
	@find hooks -name "*.py" | xargs wc -l | tail -n 1 || echo "0 (no Python files yet)"
	@echo "Total:"
	@find . -name "*.rs" -o -name "*.py" | xargs wc -l | tail -n 1

##@ Advanced

profile: ## Profile Rust code
	@echo "$(YELLOW)Profiling Rust code...$(NC)"
	@cd cli && cargo build --release
	@cd cli && cargo flamegraph || echo "Install flamegraph: cargo install flamegraph"

audit: ## Security audit
	@echo "$(YELLOW)Running security audit...$(NC)"
	@cd cli && cargo audit || echo "Install cargo-audit: cargo install cargo-audit"

fix-all: ## Fix all auto-fixable issues
	@echo "$(GREEN)Auto-fixing all issues...$(NC)"
	@$(MAKE) fmt
	@$(MAKE) lint-fix
	@echo "$(GREEN)✓ Auto-fixes applied$(NC)"

verify: clean check build ## Clean, check, and build everything
	@echo "$(GREEN)✓ Full verification complete!$(NC)"

