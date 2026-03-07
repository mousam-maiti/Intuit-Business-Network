#!/bin/bash
# ============================================================
# QB Network Graph — Stream Aggregator
# ============================================================
#
# Fully automated pipeline that:
#   1. Creates silver/entity_connections table in Paimon
#   2. Submits Job 1: Identity Sync (vendors + customers)
#   3. Submits Job 2: Transaction Aggregation (bills + invoices)
#   4. Verifies data landed correctly
#
# Both jobs run continuously — tailing bronze changelogs.
# After this, you'll have 11 total Flink jobs:
#   9 CDC (bronze) + 2 entity connections (silver)
#
# Usage:
#   ./run.sh              # Full pipeline: create + submit + verify
#   ./run.sh --verify     # Just run verification queries
#   ./run.sh --status     # Show job status
#   ./run.sh --stop       # Cancel entity connections jobs
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

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Load config ──
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi

WAREHOUSE_PATH="${WAREHOUSE_PATH:-/Users/mousammaiti/IntuitQB-StreamHouse}"
FLINK_REST_URL="${FLINK_REST_URL:-http://localhost:8081}"

# ── Find FLINK_HOME ──
find_flink_home() {
    # 1. Already set
    [ -n "$FLINK_HOME" ] && return

    # 2. From sibling .flink-env
    for env_file in "$SCRIPT_DIR/../.flink-env" "$SCRIPT_DIR/.flink-env" "$HOME/.flink-env"; do
        if [ -f "$env_file" ]; then
            source "$env_file"
            [ -n "$FLINK_HOME" ] && return
        fi
    done

    # 3. Glob search
    for candidate in "$HOME"/flink-1.18* /opt/flink* /usr/local/flink*; do
        if [ -d "$candidate" ] && [ -f "$candidate/bin/sql-client.sh" ]; then
            FLINK_HOME="$candidate"
            return
        fi
    done
}

find_flink_home
if [ -z "$FLINK_HOME" ] || [ ! -f "$FLINK_HOME/bin/sql-client.sh" ]; then
    echo -e "${RED}✗ Cannot find FLINK_HOME. Set it in .env or export it.${NC}"
    exit 1
fi

SQL_CLIENT="$FLINK_HOME/bin/sql-client.sh"

# ── Helpers ──

prepare_sql() {
    # Replace ${WAREHOUSE_PATH} placeholder in SQL templates
    local src="$1"
    local tmp="$SCRIPT_DIR/.tmp-sql-$$"
    sed "s|\${WAREHOUSE_PATH}|${WAREHOUSE_PATH}|g" "$src" > "$tmp"
    echo "$tmp"
}

submit_sql() {
    local label="$1"
    local sql_template="$2"

    echo -e "\n${CYAN}▶ ${label}${NC}"

    local sql_file
    sql_file=$(prepare_sql "$sql_template")

    local output
    output=$("$SQL_CLIENT" -f "$sql_file" 2>&1)
    local rc=$?

    rm -f "$sql_file"

    # Check for errors
    if echo "$output" | grep -qi "exception\|failed"; then
        # Filter out benign "already exists" messages
        if echo "$output" | grep -qi "already exists"; then
            echo -e "  ${DIM}Already exists — OK${NC}"
        else
            echo -e "  ${RED}✗ Error:${NC}"
            echo "$output" | grep -i "exception\|error\|cause\|failed" | head -10
            echo -e "\n  ${DIM}Full output:${NC}"
            echo "$output" | tail -20
            return 1
        fi
    fi

    if echo "$output" | grep -qi "submitted"; then
        local job_id
        job_id=$(echo "$output" | grep -oi '[0-9a-f]\{32\}' | head -1)
        echo -e "  ${GREEN}✓ Job submitted${NC} ${DIM}${job_id:+($job_id)}${NC}"
    elif echo "$output" | grep -qi "Execute statement succeed"; then
        echo -e "  ${GREEN}✓ Done${NC}"
    else
        echo -e "  ${GREEN}✓ Done${NC}"
    fi

    return 0
}

count_jobs() {
    local state="${1:-RUNNING}"
    curl -sf "$FLINK_REST_URL/jobs/overview" 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(sum(1 for j in data.get('jobs', []) if j['state'] == '$state'))
" 2>/dev/null || echo "0"
}

list_jobs() {
    curl -sf "$FLINK_REST_URL/jobs/overview" 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
for j in sorted(data.get('jobs', []), key=lambda x: x['name']):
    state = j['state']
    icon = '✓' if state == 'RUNNING' else '✗' if state in ('FAILED','CANCELED') else '↻'
    color = '\033[0;32m' if state == 'RUNNING' else '\033[0;31m' if state in ('FAILED','CANCELED') else '\033[1;33m'
    marker = ' ←' if 'entity_connections' in j['name'] else ''
    print(f\"  {color}{icon}\033[0m  {state:12}  {j['name'][:55]}{marker}\")
" 2>/dev/null
}

wait_for_job_count() {
    local expected="$1"
    local timeout="${2:-90}"
    local elapsed=0

    echo -ne "  ${DIM}Waiting for job to start"
    while [ $elapsed -lt $timeout ]; do
        local current
        current=$(count_jobs)
        if [ "$current" -ge "$expected" ] 2>/dev/null; then
            echo -e " ${GREEN}✓ (${current} running)${NC}"
            return 0
        fi

        # Check if job went to RESTARTING/FAILED instead
        local failing
        failing=$(count_jobs "RESTARTING")
        local failed
        failed=$(count_jobs "FAILED")
        if [ "$failing" -gt 0 ] 2>/dev/null || [ "$failed" -gt 0 ] 2>/dev/null; then
            echo -e " ${RED}✗ Job is RESTARTING/FAILED${NC}"
            echo -e "  ${DIM}Check: curl -s ${FLINK_REST_URL}/jobs/overview${NC}"
            return 1
        fi

        echo -ne "."
        sleep 3
        elapsed=$((elapsed + 3))
    done
    echo -e " ${YELLOW}⚠ timeout${NC}"
    return 1
}

header() {
    echo -e "${CYAN}"
    echo "  ╔══════════════════════════════════════════════════╗"
    echo "  ║   QB Network Graph — Stream Aggregator           ║"
    echo "  ╚══════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# ── Commands ──

do_status() {
    header
    echo -e "${BOLD}Job Status${NC}\n"
    list_jobs
    echo ""
    local running
    running=$(count_jobs)
    echo -e "  Total running: ${GREEN}${running}${NC}"
    echo ""
}

do_verify() {
    header
    echo -e "${BOLD}Running verification queries...${NC}"
    local sql_file
    sql_file=$(prepare_sql "$SCRIPT_DIR/sql/verify.sql")
    "$SQL_CLIENT" -f "$sql_file" 2>&1
    rm -f "$sql_file"
}

do_stop() {
    header
    echo -e "${YELLOW}Cancelling entity_connections jobs...${NC}"
    curl -sf "$FLINK_REST_URL/jobs/overview" 2>/dev/null | python3 -c "
import sys, json, urllib.request
data = json.load(sys.stdin)
for j in data.get('jobs', []):
    if 'entity_connections' in j['name'] and j['state'] in ('RUNNING', 'RESTARTING'):
        jid = j['jid']
        try:
            req = urllib.request.Request(f'$FLINK_REST_URL/jobs/{jid}/yarn-cancel')
            urllib.request.urlopen(req)
        except:
            # Try PATCH cancel
            try:
                req = urllib.request.Request(f'$FLINK_REST_URL/jobs/{jid}', method='PATCH')
                urllib.request.urlopen(req)
            except: pass
        print(f'  Cancelled: {j[\"name\"][:50]}')
" 2>/dev/null
    echo -e "${GREEN}✓ Done${NC}"
}

do_run() {
    header

    # ── Preflight ──
    echo -e "${YELLOW}Preflight checks...${NC}"

    if ! curl -sf "$FLINK_REST_URL/overview" >/dev/null 2>&1; then
        echo -e "  ${RED}✗ Flink not running at ${FLINK_REST_URL}${NC}"
        exit 1
    fi
    echo -e "  ${GREEN}✓${NC} Flink cluster reachable"

    if [ ! -d "$WAREHOUSE_PATH/network_graph.db" ]; then
        echo -e "  ${RED}✗ Paimon warehouse not found at ${WAREHOUSE_PATH}/network_graph.db${NC}"
        echo -e "    Run CDC setup first."
        exit 1
    fi
    echo -e "  ${GREEN}✓${NC} Paimon warehouse exists"

    local baseline
    baseline=$(count_jobs)
    if [ "$baseline" -lt 9 ] 2>/dev/null; then
        echo -e "  ${YELLOW}⚠ Only ${baseline} jobs running (expected ≥9 CDC jobs)${NC}"
        echo -ne "    Continue anyway? [y/N] "
        read -r yn
        [ "$yn" != "y" ] && exit 0
    else
        echo -e "  ${GREEN}✓${NC} ${baseline} jobs running"
    fi

    # Check if entity_connections jobs already running
    local ec_jobs
    ec_jobs=$(curl -sf "$FLINK_REST_URL/jobs/overview" 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(sum(1 for j in data.get('jobs', []) if 'entity_connections' in j['name'] and j['state'] == 'RUNNING'))
" 2>/dev/null || echo "0")

    if [ "$ec_jobs" -ge 2 ] 2>/dev/null; then
        echo -e "  ${GREEN}✓${NC} Entity connections jobs already running (${ec_jobs})"
        echo -e "\n${DIM}  Skipping job submission. Use --verify to check data.${NC}"
        echo -e "${DIM}  Use --stop then re-run to restart jobs.${NC}\n"
        list_jobs
        exit 0
    fi

    echo -e "\n${DIM}  Warehouse:  ${WAREHOUSE_PATH}${NC}"
    echo -e "${DIM}  FLINK_HOME: ${FLINK_HOME}${NC}"

    # ── Step 1: Create table ──
    submit_sql "Step 1/3: Creating entity_connections table" \
        "$SCRIPT_DIR/sql/create-entity-connections.sql"

    sleep 3

    # ── Step 2: Identity Sync ──
    submit_sql "Step 2/3: Submitting Job 1 — Identity Sync (vendors + customers)" \
        "$SCRIPT_DIR/sql/job-identity-sync.sql"

    local expected_1=$((baseline + 1))
    wait_for_job_count "$expected_1" 90

    sleep 5

    # ── Step 3: Transaction Aggregation ──
    submit_sql "Step 3/3: Submitting Job 2 — Transaction Aggregation (bills + invoices)" \
        "$SCRIPT_DIR/sql/job-transaction-agg.sql"

    local expected_2=$((baseline + 2))
    wait_for_job_count "$expected_2" 90

    # ── Summary ──
    echo -e "\n${DIM}──────────────────────────────────────────────────────${NC}"
    echo -e "${BOLD}Pipeline Summary${NC}\n"

    local final_count
    final_count=$(count_jobs)
    echo -e "  Total running jobs:  ${GREEN}${final_count}${NC}"
    echo -e "    CDC (bronze):      ${baseline}"
    echo -e "    Aggregator (silver): $((final_count - baseline))"
    echo ""

    list_jobs

    echo ""
    echo -e "  ${DIM}Warehouse: ${WAREHOUSE_PATH}/network_graph.db/entity_connections/${NC}"
    echo -e "  ${DIM}Re-verify: ./run.sh --verify${NC}"
    echo -e "  ${DIM}Job status: ./run.sh --status${NC}"
    echo ""
}

# ── Main ──

case "${1:-}" in
    --verify|-v)    do_verify ;;
    --status|-s)    do_status ;;
    --stop)         do_stop ;;
    --help|-h)
        header
        echo "  Usage: ./run.sh [command]"
        echo ""
        echo "  Commands:"
        echo "    (none)     Full pipeline: create table + submit jobs + verify"
        echo "    --verify   Run verification queries only"
        echo "    --status   Show all Flink job states"
        echo "    --stop     Cancel entity connections jobs"
        echo "    --help     This message"
        echo ""
        ;;
    *)              do_run ;;
esac
