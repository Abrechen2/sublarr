#!/bin/bash
# License compliance check script for Sublarr
# Checks that all dependencies use whitelisted licenses

set -e

echo "📄 Checking License Compliance..."
echo ""

# Backend Python License Check
echo "🐍 Python License Check (liccheck)..."
cd backend

if command -v liccheck &> /dev/null; then
    # Create liccheck.ini if it doesn't exist
    if [ ! -f "liccheck.ini" ]; then
        cat > liccheck.ini << EOF
[Licenses]
# Authorized licenses
authorized_licenses:
    mit
    apache-2.0
    bsd-2-clause
    bsd-3-clause
    isc
    gpl-2.0
    gpl-3.0
    lgpl-2.1
    lgpl-3.0
    mpl-2.0
    python-2.0
    psf
    unlicense
    cc0-1.0

# Authorized packages (exceptions)
authorized_packages:
    # Add exceptions here if needed
    # package-name:reason

[General]
# Python version
python_requires: >=3.11
EOF
    fi
    
    liccheck -r requirements.txt --level=ERROR || {
        echo "❌ License check failed! Review licenses above."
        exit 1
    }
    echo "✅ All Python licenses are compliant"
else
    echo "  ⚠️  liccheck not installed. Install with: pip install liccheck"
fi

cd ..

# Frontend Node.js License Check
echo ""
echo "⚛️  Node.js License Check (license-checker)..."
cd frontend

if command -v license-checker &> /dev/null || npm list -g license-checker &> /dev/null; then
    npx license-checker --json > license-report.json || true
    npx license-checker --onlyAllow "$(cat ../LICENSE_WHITELIST.txt | grep -v '^#' | grep -v '^$' | tr '\n' ';')" || {
        echo "❌ License check failed! Review licenses above."
        exit 1
    }
    echo "✅ All Node.js licenses are compliant"
else
    echo "  ⚠️  license-checker not installed. Install with: npm install -g license-checker"
fi

cd ..

echo ""
echo "✅ License compliance check complete!"
echo "   Reports saved:"
echo "   - frontend/license-report.json"
