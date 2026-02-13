#!/bin/bash
# Sublarr Backend DEV Server (Linux/Mac)

echo "🚀 Starting Sublarr Backend DEV Server..."

export FLASK_APP=server.py
export FLASK_ENV=development
export FLASK_DEBUG=1

# Set defaults if not set
export SUBLARR_PORT=${SUBLARR_PORT:-5765}
export SUBLARR_DB_PATH=${SUBLARR_DB_PATH:-./dev.db}
export SUBLARR_MEDIA_PATH=${SUBLARR_MEDIA_PATH:-./test-media}

echo "📁 Working Directory: $(pwd)"
echo "🔧 Port: $SUBLARR_PORT"
echo "💾 DB Path: $SUBLARR_DB_PATH"
echo "📂 Media Path: $SUBLARR_MEDIA_PATH"
echo ""

cd backend

echo "🔥 Flask Development Server starting..."
python -m flask run --host=0.0.0.0 --port=$SUBLARR_PORT --reload
