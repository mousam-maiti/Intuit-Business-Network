#!/bin/bash
# ============================================================
# QB Network Graph — Start Services (ports 8080–8087)
# ============================================================

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
DIM='\033[2m'
BOLD='\033[1m'
NC='\033[0m'

ROOT="$(cd "$(dirname "$0")" && pwd)"
PIDS_FILE="$ROOT/.demo-pids"

# ── Helpers ──

ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
warn() { echo -e "  ${YELLOW}⚠${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; exit 1; }
info() { echo -e "  ${DIM}$1${NC}"; }

wait_for_port() {
    local port=$1 label=$2 timeout=${3:-30} elapsed=0
    echo -ne "  Waiting for ${label} on :${port}"
    while [ $elapsed -lt $timeout ]; do
        if lsof -iTCP:$port -sTCP:LISTEN -P -n >/dev/null 2>&1; then
            echo -e " ${GREEN}✓${NC}"
            return 0
        fi
        echo -ne "."
        sleep 2
        elapsed=$((elapsed + 2))
    done
    echo -e " ${RED}timeout${NC}"
    return 1
}

wait_for_health() {
    local url=$1 label=$2 timeout=${3:-30} elapsed=0
    echo -ne "  Waiting for ${label} health"
    while [ $elapsed -lt $timeout ]; do
        if curl -sf "$url" >/dev/null 2>&1; then
            echo -e " ${GREEN}✓${NC}"
            return 0
        fi
        echo -ne "."
        sleep 2
        elapsed=$((elapsed + 2))
    done
    echo -e " ${RED}timeout${NC}"
    return 1
}

# ════════════════════════════════════════════════════════════

echo -e "${CYAN}"
echo "  ╔══════════════════════════════════════════════════╗"
echo "  ║   QB Network Graph — Start Services              ║"
echo "  ╚══════════════════════════════════════════════════╝"
echo -e "${NC}"

> "$PIDS_FILE"

# ── MCP Server (port 8083) — must be up before Entity Agent ──

info "Starting MCP Server on :8083..."
cd "$ROOT/qb-network-graph-mcp-servers"
source .venv/bin/activate 2>/dev/null || true
nohup python server.py > /tmp/qb-mcp-server.log 2>&1 &
echo "$!" >> "$PIDS_FILE"
deactivate 2>/dev/null || true
cd "$ROOT"
wait_for_port 8083 "MCP Server" 30 || fail "MCP Server did not start"

# ── Entity Agent (port 8085) — must be up before Classifier ──

info "Starting Entity Agent on :8085..."
cd "$ROOT/qb-network-graph-entity-agent"
source venv/bin/activate 2>/dev/null || true
nohup python main.py > /tmp/qb-entity-agent.log 2>&1 &
echo "$!" >> "$PIDS_FILE"
deactivate 2>/dev/null || true
cd "$ROOT"
wait_for_health "http://localhost:8085/api/v1/health" "Entity Agent" 30 || fail "Entity Agent did not start"

# ── Backend API (port 8087) ──

info "Starting Backend API on :8087..."
cd "$ROOT/qb-network-graph-be"
.venv/bin/python main.py > /tmp/qb-be.log 2>&1 &
echo "$!" >> "$PIDS_FILE"
cd "$ROOT"
wait_for_health "http://localhost:8087/health" "Backend API" 30 || fail "Backend API did not start"

# ── UI (port 8080) ──

info "Starting UI on :8080..."
cd "$ROOT/qb-network-graph-ui"
nohup npm run dev > /tmp/qb-ui.log 2>&1 &
echo "$!" >> "$PIDS_FILE"
cd "$ROOT"
wait_for_port 8080 "UI" 20 || warn "UI may still be starting"

# ── Conversational Agent (port 8082) ──

info "Starting Conversational Agent on :8082..."
cd "$ROOT/qb-network-graph-conv-agent"
source venv/bin/activate 2>/dev/null || true
nohup python main.py > /tmp/qb-conv-agent.log 2>&1 &
echo "$!" >> "$PIDS_FILE"
deactivate 2>/dev/null || true
cd "$ROOT"
wait_for_port 8082 "Conv Agent" 20 || warn "Conv Agent may still be starting"

# ── Port Map & Status ──

echo ""
echo -e "${BOLD}  Port Map & Status${NC}"
echo -e "${DIM}  ──────────────────────────────────────────────────────────${NC}"
printf "  ${DIM}%-6s  %-28s  %s${NC}\n" "PORT" "SERVICE" "STATUS"
echo -e "${DIM}  ──────────────────────────────────────────────────────────${NC}"

for check in \
    "8080|UI (Vite dev server)|/tmp/qb-ui.log" \
    "8082|Conversational Agent|/tmp/qb-conv-agent.log" \
    "8083|MCP Server|/tmp/qb-mcp-server.log" \
    "8085|Entity Resolution Agent|/tmp/qb-entity-agent.log" \
    "8087|Backend REST API|/tmp/qb-be.log"; do

    port=$(echo "$check" | cut -d'|' -f1)
    label=$(echo "$check" | cut -d'|' -f2)
    log=$(echo "$check" | cut -d'|' -f3)
    if lsof -iTCP:$port -sTCP:LISTEN -P -n >/dev/null 2>&1; then
        printf "  ${GREEN}●${NC} %-6s  %-28s  %s\n" ":$port" "$label" "$log"
    else
        printf "  ${RED}○${NC} %-6s  %-28s  %s\n" ":$port" "$label" "NOT RUNNING"
    fi
done

echo -e "${DIM}  ──────────────────────────────────────────────────────────${NC}"
echo ""
echo -e "${GREEN}${BOLD}  Services started.${NC}"
echo -e "${DIM}  PIDs: cat $PIDS_FILE${NC}"
echo ""
