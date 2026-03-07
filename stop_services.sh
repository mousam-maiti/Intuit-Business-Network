#!/bin/bash
# ============================================================
# QB Network Graph — Stop Services (ports 8080–8087)
# ============================================================

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
DIM='\033[2m'
BOLD='\033[1m'
NC='\033[0m'

ROOT="$(cd "$(dirname "$0")" && pwd)"
PIDS_FILE="$ROOT/.demo-pids"

ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
info() { echo -e "  ${DIM}$1${NC}"; }

echo -e "${BOLD}"
echo "  Stopping QB Network Graph services..."
echo -e "${NC}"

# ── Kill tracked PIDs ──

if [ -f "$PIDS_FILE" ]; then
    while read -r pid; do
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            info "Killed PID $pid"
        fi
    done < "$PIDS_FILE"
    > "$PIDS_FILE"
fi

# ── Kill anything still on service ports ──

for port in 8080 8082 8083 8085 8087; do
    pids=$(lsof -iTCP:$port -sTCP:LISTEN -t 2>/dev/null)
    if [ -n "$pids" ]; then
        kill $pids 2>/dev/null || true
        info "Killed process on :$port"
    fi
done

# ── Port Map & Status ──

echo ""
echo -e "${BOLD}  Port Map & Status${NC}"
echo -e "${DIM}  ──────────────────────────────────────────────────────────${NC}"
printf "  ${DIM}%-6s  %-28s  %s${NC}\n" "PORT" "SERVICE" "STATUS"
echo -e "${DIM}  ──────────────────────────────────────────────────────────${NC}"

all_stopped=true
for check in \
    "8080|UI (Vite dev server)" \
    "8082|Conversational Agent" \
    "8083|MCP Server" \
    "8085|Entity Resolution Agent" \
    "8087|Backend REST API"; do

    port=$(echo "$check" | cut -d'|' -f1)
    label=$(echo "$check" | cut -d'|' -f2)
    if lsof -iTCP:$port -sTCP:LISTEN -P -n >/dev/null 2>&1; then
        printf "  ${RED}●${NC} %-6s  %-28s  %s\n" ":$port" "$label" "STILL RUNNING"
        all_stopped=false
    else
        printf "  ${GREEN}○${NC} %-6s  %-28s  %s\n" ":$port" "$label" "stopped"
    fi
done

echo -e "${DIM}  ──────────────────────────────────────────────────────────${NC}"
echo ""
if [ "$all_stopped" = true ]; then
    echo -e "${GREEN}${BOLD}  All services stopped.${NC}"
else
    echo -e "${YELLOW}${BOLD}  Some services may still be shutting down.${NC}"
fi
echo ""
