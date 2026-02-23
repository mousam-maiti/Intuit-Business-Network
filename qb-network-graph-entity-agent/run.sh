#!/usr/bin/env bash
# ============================================================
# QB Network Graph — Entity Resolution Agent v3
# Interactive run script with menu options
# ============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="venv"
PID_FILE=".agent.pid"
LOG_FILE="agent.log"

# ── Colors ──────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()  { echo -e "${GREEN}✓${NC} $1"; }
warn()  { echo -e "${YELLOW}⚠${NC} $1"; }
err()   { echo -e "${RED}✗${NC} $1"; }
header(){ echo -e "\n${CYAN}${BOLD}$1${NC}"; }

# ── Helpers ─────────────────────────────────────────────────
ensure_venv() {
    if [ ! -d "$VENV_DIR" ]; then
        warn "Virtual environment not found. Creating..."
        python3 -m venv "$VENV_DIR"
        source "$VENV_DIR/bin/activate"
        pip install --upgrade pip -q
        pip install -r requirements.txt -q
        info "Virtual environment created and dependencies installed."
    else
        source "$VENV_DIR/bin/activate"
    fi
}

ensure_env() {
    if [ ! -f ".env" ]; then
        warn ".env not found. Copying from .env.example..."
        cp .env.example .env
        warn "Please edit .env with your API keys and credentials."
    fi
}

is_running() {
    [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

agent_pid() {
    [ -f "$PID_FILE" ] && cat "$PID_FILE" || echo ""
}

# ── Actions ─────────────────────────────────────────────────
do_setup() {
    header "Setup"
    ensure_env
    ensure_venv
    info "Setup complete. Edit .env with your API keys."
}

do_install() {
    header "Install Dependencies"
    ensure_venv
    pip install -r requirements.txt
    info "Dependencies installed."
}

do_start() {
    header "Start Agent"
    ensure_venv
    ensure_env
    if is_running; then
        warn "Agent already running (PID $(agent_pid))"
        return
    fi
    nohup python3 main.py > "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    sleep 2
    if is_running; then
        info "Agent started (PID $(agent_pid)) — http://localhost:${AGENT_PORT:-8080}"
        info "Logs: tail -f $LOG_FILE"
    else
        err "Agent failed to start. Check $LOG_FILE"
        cat "$LOG_FILE" | tail -20
    fi
}

do_start_fg() {
    header "Start Agent (foreground)"
    ensure_venv
    ensure_env
    if is_running; then
        warn "Agent already running (PID $(agent_pid)). Stop it first."
        return
    fi
    python3 main.py
}

do_stop() {
    header "Stop Agent"
    if is_running; then
        kill "$(agent_pid)"
        rm -f "$PID_FILE"
        info "Agent stopped."
    else
        warn "Agent is not running."
        rm -f "$PID_FILE"
    fi
}

do_restart() {
    do_stop
    sleep 1
    do_start
}

do_logs() {
    header "Agent Logs"
    if [ -f "$LOG_FILE" ]; then
        tail -f "$LOG_FILE"
    else
        warn "No log file found. Start the agent first."
    fi
}

do_test() {
    header "Run Tests"
    ensure_venv
    python3 -m pytest tests/ -v --tb=short
}

do_health() {
    header "Health Check"
    curl -s http://localhost:${AGENT_PORT:-8080}/health 2>/dev/null | python3 -m json.tool || err "Agent not responding"
}

do_stats() {
    header "Agent Stats"
    curl -s http://localhost:${AGENT_PORT:-8080}/stats 2>/dev/null | python3 -m json.tool || err "Agent not responding"
}

do_golden_records() {
    header "Golden Records (MySQL)"
    source .env 2>/dev/null
    docker exec qb-mysql mysql -u "${MYSQL_USER:-qb_admin}" -p"${MYSQL_PASSWORD:-qb_admin_pass}" \
        "${MYSQL_DATABASE:-quickbooks}" -e \
        "SELECT golden_record_id, canonical_name, state, naics_code, confidence, status, source_count FROM golden_records ORDER BY updated_at DESC LIMIT 20" \
        2>/dev/null || warn "Cannot connect to MySQL. Is Docker running?"
}

do_audit() {
    header "Resolution Audit (last 20)"
    source .env 2>/dev/null
    docker exec qb-mysql mysql -u "${MYSQL_USER:-qb_admin}" -p"${MYSQL_PASSWORD:-qb_admin_pass}" \
        "${MYSQL_DATABASE:-quickbooks}" -e \
        "SELECT audit_id, decision, trigger_type, target_golden_id, confidence, total_duration_ms, created_at FROM resolution_audit ORDER BY created_at DESC LIMIT 20" \
        2>/dev/null || warn "Cannot connect to MySQL. Is Docker running?"
}

do_pending() {
    header "Pending Reviews"
    source .env 2>/dev/null
    docker exec qb-mysql mysql -u "${MYSQL_USER:-qb_admin}" -p"${MYSQL_PASSWORD:-qb_admin_pass}" \
        "${MYSQL_DATABASE:-quickbooks}" -e \
        "SELECT match_id, orphan_golden_id, candidate_golden_id, confidence, status FROM pending_resolution WHERE status='PENDING' ORDER BY created_at DESC LIMIT 20" \
        2>/dev/null || warn "Cannot connect to MySQL. Is Docker running?"
}

do_check_stores() {
    header "Store Health Check"

    # MySQL
    echo -n "  MySQL:  "
    docker exec qb-mysql mysqladmin ping -h localhost --silent 2>/dev/null \
        && info "connected" || err "not reachable"

    # Milvus
    echo -n "  Milvus: "
    curl -sf http://localhost:9091/healthz 2>/dev/null \
        && info "connected" || err "not reachable"

    # GraphDB
    echo -n "  GraphDB: "
    curl -sf http://localhost:7200/rest/repositories 2>/dev/null \
        && info "connected" || warn "not running (optional)"
}

do_test_resolve() {
    header "Send Test Resolve Request"
    curl -s -X POST http://localhost:${AGENT_PORT:-8080}/resolve \
        -H "Content-Type: application/json" \
        -d '{
            "event_id": "test-manual-001",
            "record_id": "v-test-1",
            "record_type": "vendor",
            "company_id": 1,
            "chain_depth": 0,
            "classified_persona": {
                "identity": {
                    "normalized_name": "BOBS PLUMBING",
                    "name_first_token": "BOBS",
                    "name_tokens": ["BOBS", "PLUMBING"],
                    "legal_suffix": "LLC",
                    "ein_clean": "743218976",
                    "phone_digits": "5125550101",
                    "email": "bob@bobsplumbing.com",
                    "email_domain": "bobsplumbing.com"
                },
                "industry": {
                    "naics_code": "423720",
                    "naics_sector": "42",
                    "naics_subsector": "423",
                    "original_category": "Plumbing Supply"
                },
                "location": {
                    "state": "TX",
                    "city_norm": "AUSTIN",
                    "zip3": "787",
                    "zip5": "78745"
                },
                "commodity": {
                    "top_keywords": ["pvc pipe", "copper fitting", "water heater"],
                    "service_categories": ["Materials"]
                },
                "behavioral": {
                    "volume_bracket": "MEDIUM",
                    "avg_transaction": 1787.23,
                    "transaction_count": 47
                },
                "sparsity": {
                    "identity": 5,
                    "industry": 4,
                    "location": 4,
                    "commodity": 3,
                    "behavioral": 4
                }
            }
        }' 2>/dev/null | python3 -m json.tool || err "Agent not responding"
}

do_milvus_count() {
    header "Milvus Entity Count"
    ensure_venv
    python3 -c "
from pymilvus import connections, Collection, utility
try:
    connections.connect(host='localhost', port='19530')
    if utility.has_collection('golden_records'):
        col = Collection('golden_records')
        col.load()
        print(f'  golden_records collection: {col.num_entities} entities')
    else:
        print('  golden_records collection: not yet created')
    connections.disconnect('default')
except Exception as e:
    print(f'  Cannot connect to Milvus: {e}')
" 2>/dev/null
}

# ── CLI shortcut handling ───────────────────────────────────
case "${1:-}" in
    --setup)     do_setup;     exit 0 ;;
    --install)   do_install;   exit 0 ;;
    --start)     do_start;     exit 0 ;;
    --start-fg)  do_start_fg;  exit 0 ;;
    --stop)      do_stop;      exit 0 ;;
    --restart)   do_restart;   exit 0 ;;
    --test)      do_test;      exit 0 ;;
    --health)    do_health;    exit 0 ;;
    --stats)     do_stats;     exit 0 ;;
    --logs)      do_logs;      exit 0 ;;
    --stores)    do_check_stores; exit 0 ;;
    --help|-h)
        echo "Usage: $0 [--setup|--install|--start|--start-fg|--stop|--restart|--test|--health|--stats|--logs|--stores]"
        exit 0 ;;
esac

# ── Interactive Menu ────────────────────────────────────────
show_menu() {
    echo ""
    echo -e "${BOLD}╔══════════════════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}║  QB Network Graph — Entity Resolution Agent v3      ║${NC}"
    echo -e "${BOLD}╚══════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${CYAN}Setup${NC}"
    echo "  s  Setup (venv + deps + .env)        i  Install/update deps"
    echo ""
    echo -e "  ${CYAN}Agent${NC}"
    echo "  1  Start agent (background)          2  Start agent (foreground)"
    echo "  3  Stop agent                        4  Restart agent"
    echo "  l  View agent logs (tail -f)"
    echo ""
    echo -e "  ${CYAN}Test${NC}"
    echo "  t  Run test suite (42 tests)         r  Send test resolve request"
    echo ""
    echo -e "  ${CYAN}Monitor${NC}"
    echo "  h  Health check                      a  Agent stats"
    echo "  g  Show golden records (MySQL)        u  Show audit log"
    echo "  p  Show pending reviews               m  Milvus entity count"
    echo ""
    echo -e "  ${CYAN}Infrastructure${NC}"
    echo "  c  Check all stores (MySQL/Milvus/GraphDB)"
    echo ""
    echo "  q  Quit"
    echo ""
    if is_running; then
        echo -e "  ${GREEN}● Agent running (PID $(agent_pid))${NC}"
    else
        echo -e "  ${RED}○ Agent not running${NC}"
    fi
    echo ""
}

while true; do
    show_menu
    read -rp "  Choose: " choice
    case "$choice" in
        s)  do_setup ;;
        i)  do_install ;;
        1)  do_start ;;
        2)  do_start_fg ;;
        3)  do_stop ;;
        4)  do_restart ;;
        l)  do_logs ;;
        t)  do_test ;;
        r)  do_test_resolve ;;
        h)  do_health ;;
        a)  do_stats ;;
        g)  do_golden_records ;;
        u)  do_audit ;;
        p)  do_pending ;;
        m)  do_milvus_count ;;
        c)  do_check_stores ;;
        q)  echo ""; info "Bye."; exit 0 ;;
        *)  warn "Invalid choice: $choice" ;;
    esac
done
