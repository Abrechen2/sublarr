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
    pre-commit install || true
fi

echo "✅ Quick setup complete!"
