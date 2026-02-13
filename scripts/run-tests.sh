#!/bin/bash
# Run all tests (Backend + Frontend)

echo "🧪 Running Sublarr Tests..."
echo ""

# Backend Tests
echo "🐍 Backend Tests (pytest)..."
cd backend
python -m pytest tests/ -v --tb=short
BACKEND_EXIT=$?
cd ..

echo ""

# Frontend Tests
echo "⚛️  Frontend Tests (vitest)..."
cd frontend
npm run test -- --run
FRONTEND_EXIT=$?
cd ..

echo ""

if [ $BACKEND_EXIT -eq 0 ] && [ $FRONTEND_EXIT -eq 0 ]; then
    echo "✅ All tests passed!"
    exit 0
else
    echo "❌ Some tests failed"
    exit 1
fi
