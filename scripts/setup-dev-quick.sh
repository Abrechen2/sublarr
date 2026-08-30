#!/bin/bash
# Quick setup script - non-interactive version
# Use this for CI or when you want to skip prompts

set -e

echo "🚀 Quick setup for Sublarr..."
echo ""

# Backend
cd backend
python -m pip install --upgrade pip
pip install -r requirements.txt
cd ..

# Frontend
cd frontend
npm install
cd ..

# Pre-commit (if available)
if command -v pre-commit &> /dev/null; then
    # pre-commit refuses to install while core.hooksPath is set. It was set here to
    # git's own default, which changes nothing but blocked installation silently for
    # months -- so the repo had a pre-commit config that never ran, and CI caught
    # formatting drift instead. Clear it only when it points at the default.
    if [ "$(git config --get core.hooksPath || true)" = "$(git rev-parse --git-path hooks)" ]; then
        git config --unset-all core.hooksPath
    fi
    pre-commit install
fi

echo "✅ Quick setup complete!"
