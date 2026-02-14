#!/bin/bash
# Code metrics collection script for Sublarr
# Collects complexity, duplication, and maintainability metrics

set -e

echo "📊 Collecting Code Metrics..."
echo ""

# Backend metrics
echo "🐍 Backend Metrics (Python)..."
cd backend

# Cyclomatic Complexity with radon
if command -v radon &> /dev/null; then
    echo "  - Cyclomatic Complexity:"
    radon cc . --min B --json > metrics_complexity.json 2>/dev/null || echo "    radon not installed, skipping"
    
    echo "  - Maintainability Index:"
    radon mi . --min B --json > metrics_maintainability.json 2>/dev/null || echo "    radon not installed, skipping"
else
    echo "    radon not installed. Install with: pip install radon"
fi

cd ..

# Frontend metrics
echo ""
echo "⚛️  Frontend Metrics (TypeScript)..."
cd frontend

# Check for jscpd (copy-paste detector)
if command -v jscpd &> /dev/null; then
    echo "  - Code Duplication:"
    jscpd --min-lines 5 --min-tokens 50 --format json --output ./metrics_duplication.json src/ 2>/dev/null || echo "    jscpd scan completed"
else
    echo "    jscpd not installed. Install with: npm install -g jscpd"
fi

cd ..

echo ""
echo "✅ Metrics collection complete!"
echo "   Results saved in backend/metrics_*.json and frontend/metrics_*.json"
