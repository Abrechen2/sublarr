#!/bin/bash
# Sublarr Full DEV Stack (Linux/Mac)
# Startet Backend und Frontend parallel

echo "Starting Sublarr Full DEV Stack..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Starte Backend im Hintergrund
echo "Starting Backend..."
bash "$SCRIPT_DIR/dev-backend.sh" &
BACKEND_PID=$!

# Warte kurz
sleep 3

# Starte Frontend im Hintergrund
echo "Starting Frontend..."
bash "$SCRIPT_DIR/dev-frontend.sh" &
FRONTEND_PID=$!

echo ""
echo "Both servers started!"
echo "   Backend:  http://localhost:5765"
echo "   Frontend: http://localhost:5173"
echo ""
echo "Press Ctrl+C to stop all servers..."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM
wait
