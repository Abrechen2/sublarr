#!/bin/bash
# Sublarr Frontend DEV Server (Linux/Mac)

echo "🚀 Starting Sublarr Frontend DEV Server..."

cd frontend

echo "📁 Working Directory: $(pwd)"
echo "🌐 Vite Dev Server starting on http://localhost:5173"
echo ""

npm run dev
