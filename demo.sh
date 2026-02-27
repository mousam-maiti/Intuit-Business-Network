#!/bin/bash
# ============================================================
# QB Network Graph — Full Demo Reset & Launch
# ============================================================
#
# Wipes all data, re-seeds, runs the full pipeline, and starts
# all services so the UI is ready with fresh real data.
#
# Usage:
#   ./demo.sh           # Full reset + pipeline + services
#
# Prerequisites:
#   - Docker: qb-mysql and milvus-standalone running
#   - Flink: installed ($FLINK_HOME set via qb-network-graph-cdc/.flink-env)
#   - Python venvs: qb-seed-generator, qb-network-graph-be, qb-network-graph-mcp-servers,
#                   qb-network-graph-conv-agent
#   - Node: qb-network-graph-ui (npm install done)
#   - Java: classifier-orchestrator JAR built
#
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
WAREHOUSE_PATH="${PAIMON_WAREHOUSE_PATH:-/Users/mousammaiti/IntuitQB-StreamHouse}"
PIDS_FILE="$ROOT/.demo-pids"

# ── Load FLINK_HOME ──
if [ -f "$ROOT/qb-network-graph-cdc/.flink-env" ]; then
    source "$ROOT/qb-network-graph-cdc/.flink-env"
fi

# ── Helpers ──

step() {
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}  Step $1: $2${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

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

mysql_exec() {
    docker exec qb-mysql mysql -u qb_admin -pqb_admin_pass quickbooks -e "$1" 2>/dev/null
}

kill_port() {
    local port=$1
    local pids=$(lsof -iTCP:$port -sTCP:LISTEN -t 2>/dev/null)
    if [ -n "$pids" ]; then
        kill $pids 2>/dev/null || true
        info "Killed process on :$port"
    fi
}

cancel_all_flink_jobs() {
    if ! curl -sf http://localhost:8081/overview >/dev/null 2>&1; then
        return
    fi
    local job_ids=$(curl -sf http://localhost:8081/jobs/overview 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
for j in data.get('jobs', []):
    if j['state'] in ('RUNNING', 'RESTARTING'):
        print(j['jid'])
" 2>/dev/null)
    for jid in $job_ids; do
        curl -sf -X PATCH "http://localhost:8081/jobs/$jid" >/dev/null 2>&1 || true
    done
    if [ -n "$job_ids" ]; then
        ok "Cancelled $(echo "$job_ids" | wc -l | tr -d ' ') Flink job(s)"
        sleep 3
    else
        info "No running Flink jobs"
    fi
}

# ════════════════════════════════════════════════════════════
#  MAIN
# ════════════════════════════════════════════════════════════

echo -e "${CYAN}"
echo "  ╔══════════════════════════════════════════════════╗"
echo "  ║   QB Network Graph — Demo Reset & Launch         ║"
echo "  ╚══════════════════════════════════════════════════╝"
echo -e "${NC}"

# ── Preflight ──
echo -e "${BOLD}Preflight checks...${NC}"

if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^qb-mysql$"; then
    fail "MySQL Docker container (qb-mysql) not running"
fi
ok "MySQL container running"

if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^milvus-standalone$"; then
    warn "Milvus container not running — vector search will use in-memory fallback"
else
    ok "Milvus container running"
fi

if [ -z "$FLINK_HOME" ] || [ ! -f "$FLINK_HOME/bin/sql-client.sh" ]; then
    fail "FLINK_HOME not set or invalid. Run qb-network-graph-cdc/setup.sh first."
fi
ok "FLINK_HOME=$FLINK_HOME"


# ──────────────────────────────────────────────────────────
step 0 "Stop running Flink jobs & services"
# ──────────────────────────────────────────────────────────

cancel_all_flink_jobs

for port in 8080 8081 8082 8083 8085 8087; do
    kill_port $port
done
ok "Services stopped"


# ──────────────────────────────────────────────────────────
step 1 "Clear Paimon warehouse"
# ──────────────────────────────────────────────────────────

if [ -d "$WAREHOUSE_PATH/network_graph.db" ]; then
    rm -rf "$WAREHOUSE_PATH/network_graph.db"
    ok "Deleted $WAREHOUSE_PATH/network_graph.db"
else
    info "Warehouse already clean"
fi

# Clear Flink checkpoints
if [ -d "$WAREHOUSE_PATH/_checkpoints" ]; then
    rm -rf "$WAREHOUSE_PATH/_checkpoints"
    ok "Deleted Flink checkpoints"
fi


# ──────────────────────────────────────────────────────────
step 2 "Clear Milvus collection"
# ──────────────────────────────────────────────────────────

if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^milvus-standalone$"; then
    python3 -c "
from pymilvus import connections, utility
connections.connect(host='localhost', port='19530')
if utility.has_collection('golden_records'):
    utility.drop_collection('golden_records')
    print('  Dropped golden_records collection')
else:
    print('  Collection already clean')
connections.disconnect('default')
" 2>/dev/null || warn "Could not clear Milvus (pymilvus not available — will auto-create on MCP start)"
else
    info "Milvus not running — skipping"
fi


# ──────────────────────────────────────────────────────────
step 3 "Run Liquibase migrations"
# ──────────────────────────────────────────────────────────

cd "$ROOT/qb-network-graph-dev-ops/db"
liquibase update --log-level=WARNING 2>&1 | tail -5
ok "Liquibase up to date"
cd "$ROOT"


# ──────────────────────────────────────────────────────────
step 4 "Run BE schema.sql (IF NOT EXISTS)"
# ──────────────────────────────────────────────────────────

docker exec -i qb-mysql mysql -u qb_admin -pqb_admin_pass quickbooks \
    < "$ROOT/qb-network-graph-be/schema.sql" 2>/dev/null
ok "BE tables ensured"


# ──────────────────────────────────────────────────────────
step 5 "Truncate ALL tables"
# ──────────────────────────────────────────────────────────

mysql_exec "
SET FOREIGN_KEY_CHECKS = 0;

-- QB source tables
TRUNCATE TABLE payments;
TRUNCATE TABLE bill_line_items;
TRUNCATE TABLE invoice_line_items;
TRUNCATE TABLE bills;
TRUNCATE TABLE invoices;
TRUNCATE TABLE products_services;
TRUNCATE TABLE vendors;
TRUNCATE TABLE customers;
TRUNCATE TABLE companies;

-- Network graph tables
TRUNCATE TABLE resolution_audit;
TRUNCATE TABLE pending_resolution;
TRUNCATE TABLE relationships;
TRUNCATE TABLE golden_records;
TRUNCATE TABLE match_decisions;

-- BE tables
TRUNCATE TABLE native_overrides;
TRUNCATE TABLE native_merges;
TRUNCATE TABLE manual_connections;
TRUNCATE TABLE auto_connections;
TRUNCATE TABLE connection_alerts;

SET FOREIGN_KEY_CHECKS = 1;
"
ok "All tables truncated"


# ──────────────────────────────────────────────────────────
step 6 "Seed QB source tables"
# ──────────────────────────────────────────────────────────

cd "$ROOT/qb-seed-generator"
source venv/bin/activate 2>/dev/null || true
python -m src.main seed
deactivate 2>/dev/null || true
cd "$ROOT"
ok "QB source data seeded"


# ──────────────────────────────────────────────────────────
step 7 "Ensure Flink cluster is running"
# ──────────────────────────────────────────────────────────

FLINK_SLOTS=$(curl -sf http://localhost:8081/overview 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('slots-available',0))" 2>/dev/null || echo "")
if [ -n "$FLINK_SLOTS" ] && [ "$FLINK_SLOTS" -gt 0 ] 2>/dev/null; then
    ok "Flink already running ($FLINK_SLOTS slots available)"
else
    info "Starting Flink cluster..."
    "$FLINK_HOME/bin/start-cluster.sh" 2>&1 | tail -3
    # Wait for Flink to respond with valid JSON
    FLINK_WAIT=0
    while [ $FLINK_WAIT -lt 30 ]; do
        FLINK_CHECK=$(curl -sf http://localhost:8081/overview 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('slots-total',0))" 2>/dev/null || echo "")
        if [ -n "$FLINK_CHECK" ] && [ "$FLINK_CHECK" -gt 0 ] 2>/dev/null; then
            break
        fi
        sleep 2
        FLINK_WAIT=$((FLINK_WAIT + 2))
    done
    if [ -n "$FLINK_CHECK" ] && [ "$FLINK_CHECK" -gt 0 ] 2>/dev/null; then
        ok "Flink cluster started ($FLINK_CHECK slots)"
    else
        fail "Flink did not start — check $FLINK_HOME/log/"
    fi
fi


# ──────────────────────────────────────────────────────────
step 8 "Submit CDC jobs (MySQL → Paimon)"
# ──────────────────────────────────────────────────────────

CDC_DIR="$ROOT/qb-network-graph-cdc"

# Phase 1: Create catalog + bronze tables
info "Creating Paimon catalog and bronze tables..."
DDL_FILE=$(mktemp /tmp/cdc-ddl-XXXXXX.sql)
cat "$CDC_DIR/sql/01-create-paimon-catalog.sql" >> "$DDL_FILE"
echo "" >> "$DDL_FILE"
cat "$CDC_DIR/sql/03-paimon-bronze-tables.sql" >> "$DDL_FILE"
"$FLINK_HOME/bin/sql-client.sh" -f "$DDL_FILE" >/dev/null 2>&1
rm -f "$DDL_FILE"
ok "Paimon catalog + bronze tables created"

# Phase 2: Generate job files if needed
JOBS_DIR="$CDC_DIR/sql/jobs"
if [ ! -d "$JOBS_DIR" ] || [ -z "$(ls -A "$JOBS_DIR" 2>/dev/null)" ]; then
    bash "$CDC_DIR/generate-jobs.sh" >/dev/null 2>&1
    ok "Generated CDC job SQL files"
fi

# Phase 3: Submit 9 CDC jobs
info "Submitting 9 CDC streaming jobs..."
for job in "$JOBS_DIR"/*.sql; do
    label=$(basename "$job" .sql)
    output=$("$FLINK_HOME/bin/sql-client.sh" -f "$job" 2>&1)
    if echo "$output" | grep -qi "error\|exception"; then
        if ! echo "$output" | grep -qi "already exists"; then
            warn "Job $label had errors"
        fi
    fi
done
ok "CDC jobs submitted"


# ──────────────────────────────────────────────────────────
step 9 "Wait for CDC snapshot"
# ──────────────────────────────────────────────────────────

info "Waiting for staged_vendors to have data (initial snapshot)..."
TIMEOUT=120
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
    # Check if staged_vendors directory has data files
    DATA_FILES=$(find "$WAREHOUSE_PATH/network_graph.db/staged_vendors/bucket-0" -name "data-*" 2>/dev/null | head -1)
    if [ -n "$DATA_FILES" ]; then
        ok "CDC snapshot complete — Paimon tables populated"
        break
    fi
    sleep 5
    ELAPSED=$((ELAPSED + 5))
    echo -ne "  ${DIM}${ELAPSED}s...${NC}\r"
done
if [ $ELAPSED -ge $TIMEOUT ]; then
    warn "CDC snapshot timeout — continuing anyway"
fi


# ──────────────────────────────────────────────────────────
step 10 "Submit Aggregator jobs (staged_* → entity_connections)"
# ──────────────────────────────────────────────────────────

AGG_DIR="$ROOT/qb-network-graph-stream-aggregator"

prepare_agg_sql() {
    sed "s|\${WAREHOUSE_PATH}|${WAREHOUSE_PATH}|g" "$1"
}

# Create entity_connections table
info "Creating entity_connections table..."
prepare_agg_sql "$AGG_DIR/sql/create-entity-connections.sql" > /tmp/agg-create-$$.sql
"$FLINK_HOME/bin/sql-client.sh" -f /tmp/agg-create-$$.sql >/dev/null 2>&1
rm -f /tmp/agg-create-$$.sql
ok "entity_connections table created"

sleep 3

# Submit Job 1: Identity Sync
info "Submitting Job 1: Identity Sync..."
prepare_agg_sql "$AGG_DIR/sql/job-identity-sync.sql" > /tmp/agg-job1-$$.sql
"$FLINK_HOME/bin/sql-client.sh" -f /tmp/agg-job1-$$.sql >/dev/null 2>&1
rm -f /tmp/agg-job1-$$.sql
ok "Job 1 submitted"

sleep 5

# Submit Job 2: Transaction Aggregation
info "Submitting Job 2: Transaction Aggregation..."
prepare_agg_sql "$AGG_DIR/sql/job-transaction-agg.sql" > /tmp/agg-job2-$$.sql
"$FLINK_HOME/bin/sql-client.sh" -f /tmp/agg-job2-$$.sql >/dev/null 2>&1
rm -f /tmp/agg-job2-$$.sql
ok "Job 2 submitted"


# ──────────────────────────────────────────────────────────
step 11 "Wait for entity_connections data"
# ──────────────────────────────────────────────────────────

info "Waiting for entity_connections to have data..."
TIMEOUT=120
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
    DATA_FILES=$(find "$WAREHOUSE_PATH/network_graph.db/entity_connections/bucket-0" -name "data-*" 2>/dev/null | head -1)
    if [ -n "$DATA_FILES" ]; then
        ok "Aggregation complete — entity_connections populated"
        break
    fi
    sleep 5
    ELAPSED=$((ELAPSED + 5))
    echo -ne "  ${DIM}${ELAPSED}s...${NC}\r"
done
if [ $ELAPSED -ge $TIMEOUT ]; then
    warn "Aggregation timeout — continuing anyway"
fi


# ──────────────────────────────────────────────────────────
step 12 "Keep Flink jobs running"
# ──────────────────────────────────────────────────────────

RUNNING_JOBS=$(curl -sf http://localhost:8081/jobs/overview 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(sum(1 for j in data.get('jobs', []) if j['state'] in ('RUNNING', 'RESTARTING')))
" 2>/dev/null || echo "0")
ok "Flink CDC + Aggregator jobs still running ($RUNNING_JOBS jobs)"


# ──────────────────────────────────────────────────────────
step 13 "Start services"
# ──────────────────────────────────────────────────────────

> "$PIDS_FILE"

# MCP Server (port 8083) — must be up before Entity Agent
info "Starting MCP Server on :8083..."
cd "$ROOT/qb-network-graph-mcp-servers"
source .venv/bin/activate 2>/dev/null || true
nohup python server.py > /tmp/qb-mcp-server.log 2>&1 &
echo "$!" >> "$PIDS_FILE"
deactivate 2>/dev/null || true
cd "$ROOT"
wait_for_port 8083 "MCP Server" 30 || fail "MCP Server did not start"

# Entity Agent (port 8085) — must be up before Classifier
info "Starting Entity Agent on :8085..."
cd "$ROOT/qb-network-graph-entity-agent"
nohup python main.py > /tmp/qb-entity-agent.log 2>&1 &
echo "$!" >> "$PIDS_FILE"
cd "$ROOT"
wait_for_health "http://localhost:8085/health" "Entity Agent" 30 || fail "Entity Agent did not start"

# Backend API (port 8087)
info "Starting Backend API on :8087..."
cd "$ROOT/qb-network-graph-be"
.venv/bin/python main.py > /tmp/qb-be.log 2>&1 &
echo "$!" >> "$PIDS_FILE"
cd "$ROOT"
wait_for_health "http://localhost:8087/health" "Backend API" 30 || fail "Backend API did not start"

# UI (port 8080)
info "Starting UI on :8080..."
cd "$ROOT/qb-network-graph-ui"
nohup npm run dev > /tmp/qb-ui.log 2>&1 &
echo "$!" >> "$PIDS_FILE"
cd "$ROOT"
wait_for_port 8080 "UI" 20 || warn "UI may still be starting"

# Conversational Agent (port 8082)
info "Starting Conversational Agent on :8082..."
cd "$ROOT/qb-network-graph-conv-agent"
source venv/bin/activate 2>/dev/null || true
nohup python main.py > /tmp/qb-conv-agent.log 2>&1 &
echo "$!" >> "$PIDS_FILE"
deactivate 2>/dev/null || true
cd "$ROOT"
wait_for_port 8082 "Conv Agent" 20 || warn "Conv Agent may still be starting"

ok "All services started"


# ──────────────────────────────────────────────────────────
step 14 "Run Classifier Orchestrator (stream mode + reset)"
# ──────────────────────────────────────────────────────────

# Verify MCP + Entity Agent are up before starting
lsof -iTCP:8083 -sTCP:LISTEN -P -n >/dev/null 2>&1 || fail "MCP Server not listening on :8083"
curl -sf http://localhost:8085/health >/dev/null 2>&1 || fail "Entity Agent not healthy"
ok "MCP Server + Entity Agent ready"

ORCH_DIR="$ROOT/qb-network-graph-classifier-orchestrator"
ORCH_JAR="$ORCH_DIR/target/classifier-orchestrator.jar"

if [ ! -f "$ORCH_JAR" ]; then
    fail "Classifier JAR not found at $ORCH_JAR — run: cd $ORCH_DIR && mvn clean package"
fi

info "Starting Classifier Orchestrator in stream mode with --reset..."
info "  Reads: Paimon entity_connections"
info "  Writes: POST /resolve → golden_records, relationships, resolution_audit"
info "  Log: /tmp/qb-classifier.log"

cd "$ORCH_DIR"
nohup java -jar "$ORCH_JAR" --stream --reset > /tmp/qb-classifier.log 2>&1 &
echo "$!" >> "$PIDS_FILE"
cd "$ROOT"
ok "Classifier Orchestrator running in background (PID $(tail -1 "$PIDS_FILE"))"


# ──────────────────────────────────────────────────────────
step 15 "Final health checks"
# ──────────────────────────────────────────────────────────

info "Waiting 15s for initial entity resolution..."
sleep 15

echo ""
echo -e "${BOLD}  Service Status${NC}"
echo -e "${DIM}  ──────────────────────────────────────────────${NC}"

for check in \
    "8080|UI|http://localhost:8080" \
    "8082|Conv Agent|http://localhost:8082" \
    "8083|MCP Server|http://localhost:8083" \
    "8085|Entity Agent|http://localhost:8085/health" \
    "8087|Backend API|http://localhost:8087/health"; do

    port=$(echo "$check" | cut -d'|' -f1)
    label=$(echo "$check" | cut -d'|' -f2)
    if lsof -iTCP:$port -sTCP:LISTEN -P -n >/dev/null 2>&1; then
        echo -e "  ${GREEN}●${NC} :${port}  ${label}"
    else
        echo -e "  ${RED}○${NC} :${port}  ${label}"
    fi
done

echo ""

# Check if golden records exist
GR_COUNT=$(mysql_exec "SELECT COUNT(*) AS cnt FROM golden_records WHERE status = 'ACTIVE';" 2>/dev/null | tail -1 | tr -d '[:space:]')
AUDIT_COUNT=$(mysql_exec "SELECT COUNT(*) AS cnt FROM resolution_audit;" 2>/dev/null | tail -1 | tr -d '[:space:]')
PENDING_COUNT=$(mysql_exec "SELECT COUNT(*) AS cnt FROM pending_resolution WHERE status = 'PENDING';" 2>/dev/null | tail -1 | tr -d '[:space:]')

echo -e "${BOLD}  Data Status${NC}"
echo -e "${DIM}  ──────────────────────────────────────────────${NC}"
echo -e "  Golden records:     ${GR_COUNT:-0}"
echo -e "  Audit trail rows:   ${AUDIT_COUNT:-0}"
echo -e "  Pending reviews:    ${PENDING_COUNT:-0}"

if [ "${GR_COUNT:-0}" = "0" ]; then
    warn "No golden records yet — Classifier Orchestrator is still processing"
    info "Monitor: tail -f /tmp/qb-classifier.log"
    info "Recheck: curl http://localhost:8087/api/v1/entities | python3 -m json.tool | head"
else
    ok "Entity resolution data is live!"
fi

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}${BOLD}  Demo ready!${NC}"
echo -e "${DIM}  UI:   http://localhost:8080${NC}"
echo -e "${DIM}  API:  http://localhost:8087/api/v1/entities${NC}"
echo -e "${DIM}  Logs: /tmp/qb-*.log${NC}"
echo -e "${DIM}  PIDs: cat $PIDS_FILE${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
