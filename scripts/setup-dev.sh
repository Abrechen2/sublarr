#!/bin/bash
# Development setup script for Sublarr
# Installs all dependencies and sets up development environment

set -e

echo "🚀 Setting up Sublarr development environment..."
echo ""

# Backend Setup
echo "🐍 Backend Setup..."
cd backend

echo "  - Installing Python dependencies..."
python -m pip install --upgrade pip
pip install -r requirements.txt

echo "  - ✅ Backend dependencies installed"
cd ..

# Frontend Setup
echo ""
echo "⚛️  Frontend Setup..."
cd frontend

echo "  - Installing Node.js dependencies..."
npm install

echo "  - ✅ Frontend dependencies installed"
cd ..

# Pre-commit Hooks
echo ""
echo "🔧 Pre-commit Hooks Setup..."
if command -v pre-commit &> /dev/null; then
    echo "  - Installing pre-commit hooks..."
    pre-commit install
    echo "  - ✅ Pre-commit hooks installed"
else
    echo "  - ⚠️  pre-commit not found. Install with: pip install pre-commit"
fi

# Optional: Dependency Pinning
echo ""
read -p "  Generate pinned requirements.txt from requirements.in? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    cd backend
    if command -v pip-compile &> /dev/null; then
        echo "  - Generating requirements.txt from requirements.in..."
        pip-compile requirements.in --output-file requirements.txt --upgrade
        echo "  - ✅ requirements.txt generated"
    else
        echo "  - ⚠️  pip-compile not found. Install with: pip install pip-tools"
    fi
    cd ..
fi

# Optional: Run tests
echo ""
read -p "  Run tests to verify setup? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "🧪 Running tests..."
    
    # Backend tests
    echo "  - Backend tests..."
    cd backend
    pytest tests/ -v --tb=short || echo "  - ⚠️  Some backend tests failed"
    cd ..
    
    # Frontend tests
    echo "  - Frontend tests..."
    cd frontend
    npm test -- --run || echo "  - ⚠️  Some frontend tests failed"
    cd ..
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "📝 Next steps:"
echo "   1. Configure your .env file (copy .env.example)"
echo "   2. Start development: npm run dev (from project root)"
echo "   3. Or start separately:"
echo "      - Backend: cd backend && python -m flask run --host=0.0.0.0 --port=5765"
echo "      - Frontend: cd frontend && npm run dev"
