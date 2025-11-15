#!/usr/bin/env bash
set -euo pipefail

echo "Validating stack preset files..."

for file in scripts/stacks/*.yaml; do
  echo "Checking $file..."
  
  # Basic YAML syntax check (if python is available)
  if command -v python3 > /dev/null; then
    python3 -c "import yaml; yaml.safe_load(open('$file'))"
    echo "✅ $file is valid YAML"
  else
    echo "⚠️  Python not available, skipping validation"
  fi
done

echo ""
echo "All stack files validated!"

