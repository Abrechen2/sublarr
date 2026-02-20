#!/bin/bash
# Script to update requirements.txt from requirements.in
# This pins all dependencies to exact versions

set -e

echo "📦 Compiling requirements.txt from requirements.in..."

cd "$(dirname "$0")"

# Check if pip-tools is installed
if ! command -v pip-compile &> /dev/null; then
    echo "❌ pip-tools not found. Installing..."
    pip install pip-tools
fi

# Compile requirements.txt
echo "🔄 Running pip-compile..."
pip-compile requirements.in --output-file requirements.txt --upgrade

echo "✅ requirements.txt updated!"
echo ""
echo "📝 Review the changes and commit if satisfied:"
echo "   git diff requirements.txt"
echo "   git add requirements.txt"
echo "   git commit -m 'chore: update dependencies'"
