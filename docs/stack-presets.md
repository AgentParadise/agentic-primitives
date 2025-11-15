# Stack Presets

Curated primitive configurations for common technology stacks.

## Available Stacks

### 🐍 Python
- **Best for**: FastAPI, Django, pytest
- **Tools**: uv, pytest, ruff, mypy
- **Primitives**: Python expert agent, refactoring commands, testing skills

### 📘 TypeScript
- **Best for**: Bun, Node.js projects
- **Tools**: Bun, Vitest, TypeScript compiler
- **Primitives**: TypeScript expert, refactoring, advanced types

### ⚛️ React
- **Best for**: React applications
- **Tools**: Vite, Vitest, React Testing Library
- **Primitives**: React expert, component patterns, hooks skills

### 🦅 NestJS
- **Best for**: NestJS APIs
- **Tools**: NestJS CLI, Jest
- **Primitives**: NestJS expert, module generation, E2E testing

### 🏗️ TurboRepo
- **Best for**: Monorepos
- **Tools**: TurboRepo, pnpm
- **Primitives**: Monorepo architect, pipeline configuration

### 🦀 Rust
- **Best for**: Systems programming
- **Tools**: Cargo, clippy, rustfmt
- **Primitives**: Rust expert, ownership patterns, error handling

## Preset Levels

### Minimal
- Core agent only
- Quick start for exploration

### Standard (Recommended)
- Agent + essential commands + tools
- Balanced setup for most projects

### Full
- Everything in standard +
- Skills for advanced patterns
- Safety and observability hooks

## Usage

```bash
# Auto-detect and use standard preset
./scripts/bootstrap.sh

# Specify stack and preset
./scripts/bootstrap.sh --stack python --preset full
```

