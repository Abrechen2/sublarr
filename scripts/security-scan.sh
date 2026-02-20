#!/bin/bash
# Security scanning script for Sublarr
# Scans Python, Node.js, and Docker dependencies for vulnerabilities

set -e

echo "🔒 Running Security Scans..."
echo ""

# Backend Python Security
echo "🐍 Python Security Scan (pip-audit)..."
cd backend

if command -v pip-audit &> /dev/null; then
    pip-audit --desc --format json --output pip-audit-report.json || true
    pip-audit --desc || true
else
    echo "  ⚠️  pip-audit not installed. Install with: pip install pip-audit"
fi

cd ..

# Frontend Node.js Security
echo ""
echo "⚛️  Node.js Security Scan (npm audit)..."
cd frontend

if [ -f "package-lock.json" ]; then
    npm audit --json > npm-audit-report.json || true
    npm audit || true
else
    echo "  ⚠️  package-lock.json not found. Run 'npm install' first."
fi

cd ..

# Container Security (Trivy)
echo ""
echo "🐳 Container Security Scan (trivy)..."
if command -v trivy &> /dev/null; then
    trivy fs --security-checks vuln --format json --output trivy-report.json . || true
    trivy fs --security-checks vuln . || true
else
    echo "  ⚠️  trivy not installed. Install from: https://github.com/aquasecurity/trivy"
fi

echo ""
echo "✅ Security scans complete!"
echo "   Reports saved:"
echo "   - backend/pip-audit-report.json"
echo "   - frontend/npm-audit-report.json"
echo "   - trivy-report.json"
