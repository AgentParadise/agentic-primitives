#!/usr/bin/env bash
# Stack detection library

detect_stack() {
  local stack="unknown"
  
  # TurboRepo (check first, most specific)
  if [ -f "turbo.json" ]; then
    stack="turborepo"
    
  # NestJS (check before general TypeScript)
  elif [ -f "package.json" ] && grep -q "@nestjs/core" package.json 2>/dev/null; then
    stack="nestjs"
  
  # React (check before general TypeScript)
  elif [ -f "package.json" ] && grep -q '"react"' package.json 2>/dev/null; then
    stack="react"
  
  # TypeScript (general)
  elif [ -f "package.json" ] && grep -q '"typescript"' package.json 2>/dev/null; then
    stack="typescript"
  
  # Python (modern: pyproject.toml)
  elif [ -f "pyproject.toml" ]; then
    stack="python"
  
  # Python (legacy)
  elif [ -f "requirements.txt" ] || [ -f "setup.py" ]; then
    stack="python"
  
  # Rust
  elif [ -f "Cargo.toml" ]; then
    # Exclude if this IS the agentic-primitives repo
    if ! grep -q "agentic-primitives" Cargo.toml 2>/dev/null; then
      stack="rust"
    fi
  fi
  
  echo "$stack"
}

# Detect Python package manager
detect_python_pm() {
  if [ -f "pyproject.toml" ] && grep -q "tool.uv" pyproject.toml 2>/dev/null; then
    echo "uv"
  elif [ -f "pyproject.toml" ] && grep -q "tool.poetry" pyproject.toml 2>/dev/null; then
    echo "poetry"
  elif [ -f "Pipfile" ]; then
    echo "pipenv"
  else
    echo "pip"
  fi
}

# Detect Node package manager
detect_node_pm() {
  if [ -f "bun.lockb" ]; then
    echo "bun"
  elif [ -f "pnpm-lock.yaml" ]; then
    echo "pnpm"
  elif [ -f "yarn.lock" ]; then
    echo "yarn"
  else
    echo "npm"
  fi
}

