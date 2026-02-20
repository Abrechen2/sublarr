#!/bin/bash
# Smoke-Tests für Sublarr — prüft Kern-Workflows
# Verwendung: ./scripts/smoke-tests.sh [BASE_URL]
# Default: http://localhost:5765

set -e

BASE_URL="${1:-http://localhost:5765}"
API_URL="${BASE_URL}/api/v1"

echo "🧪 Sublarr Smoke-Tests"
echo "======================"
echo "Base URL: ${BASE_URL}"
echo ""

# Farben für Output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Counter
PASSED=0
FAILED=0

# Helper: Test ausführen
run_test() {
    local name="$1"
    local command="$2"
    
    echo -n "Testing: ${name}... "
    
    if eval "$command" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ PASSED${NC}"
        ((PASSED++))
        return 0
    else
        echo -e "${RED}✗ FAILED${NC}"
        ((FAILED++))
        return 1
    fi
}

# Test 1: API ist erreichbar
run_test "API Health Check" \
    "curl -s -f '${API_URL}/health' | grep -q 'status'"

# Test 2: Detailed Health Check
run_test "Detailed Health Check" \
    "curl -s -f '${API_URL}/health/detailed' | grep -q 'database'"

# Test 3: Provider-System funktioniert
run_test "Provider System" \
    "curl -s -f '${API_URL}/providers' | grep -q 'name'"

# Test 4: Wanted-System funktioniert
run_test "Wanted System" \
    "curl -s -f '${API_URL}/wanted' | grep -q 'items'"

# Test 5: Settings-API funktioniert
run_test "Settings API" \
    "curl -s -f '${API_URL}/settings' | grep -q 'config'"

# Test 6: Frontend-Build (wenn im Projekt-Verzeichnis)
if [ -d "frontend" ] && command -v npm > /dev/null 2>&1; then
    echo -n "Testing: Frontend Build... "
    if cd frontend && npm run build > /dev/null 2>&1; then
        echo -e "${GREEN}✓ PASSED${NC}"
        ((PASSED++))
        cd ..
    else
        echo -e "${RED}✗ FAILED${NC}"
        ((FAILED++))
        cd ..
    fi
else
    echo -e "${YELLOW}⚠ SKIPPED: Frontend-Build (npm nicht verfügbar oder nicht im Projekt-Verzeichnis)${NC}"
fi

# Zusammenfassung
echo ""
echo "======================"
echo "Ergebnis: ${PASSED} bestanden, ${FAILED} fehlgeschlagen"

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ Alle Smoke-Tests bestanden!${NC}"
    exit 0
else
    echo -e "${RED}✗ Einige Smoke-Tests sind fehlgeschlagen${NC}"
    exit 1
fi
