#!/bin/bash
# ============================================================
# QB Network Graph CDC — Flink Pipeline Runner
# ============================================================

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WAREHOUSE_PATH="${PAIMON_WAREHOUSE_PATH:-/Users/mousammaiti/IntuitQB-StreamHouse}"

# Load FLINK_HOME — try .flink-env first, then environment
if [ -f "$SCRIPT_DIR/.flink-env" ]; then
    source "$SCRIPT_DIR/.flink-env"
fi

if [ -z "$FLINK_HOME" ]; then
    echo -e "${RED}FLINK_HOME not set. Run ./setup.sh first.${NC}"
    exit 1
fi

if [ ! -d "$FLINK_HOME" ]; then
    echo -e "${RED}FLINK_HOME=$FLINK_HOME does not exist. Run ./setup.sh first.${NC}"
    exit 1
fi

header() {
    clear
    echo -e "${CYAN}"
    echo "  ╔══════════════════════════════════════════════════╗"
    echo "  ║   QB Network Graph CDC — Pipeline               ║"
    echo "  ╚══════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

status_bar() {
    echo -e "${DIM}──────────────────────────────────────────────────────${NC}"

    # Flink cluster
    if curl -sf http://localhost:8081/overview >/dev/null 2>&1; then
        local jobs=$(curl -sf http://localhost:8081/jobs/overview 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
running = sum(1 for j in data.get('jobs', []) if j['state'] == 'RUNNING')
print(running)
" 2>/dev/null || echo "?")
        echo -e "  Flink:     ${GREEN}✓ running${NC}  (${jobs} jobs)"
    else
        echo -e "  Flink:     ${RED}✗ not running${NC}"
    fi

    # MySQL
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^qb-mysql$"; then
        echo -e "  MySQL:     ${GREEN}✓ running${NC}  (Docker)"
    else
        echo -e "  MySQL:     ${RED}✗ not running${NC}"
    fi

    # Warehouse
    if [ -d "$WAREHOUSE_PATH/network_graph" ]; then
        local tables=$(ls -d "$WAREHOUSE_PATH"/network_graph/staged_* 2>/dev/null | wc -l | tr -d ' ')
        echo -e "  Warehouse: ${GREEN}✓ ${tables} tables${NC}  ($WAREHOUSE_PATH)"
    else
        echo -e "  Warehouse: ${YELLOW}● empty${NC}  ($WAREHOUSE_PATH)"
    fi

    # Observability
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^qb-otel-collector$"; then
        echo -e "  OTEL:      ${GREEN}✓ scraping :9249 → :8889${NC}"
    else
        echo -e "  OTEL:      ${DIM}○ not running${NC}"
    fi

    echo -e "${DIM}──────────────────────────────────────────────────────${NC}"
    echo ""
}

menu() {
    echo -e "  ${BOLD}Pipeline${NC}"
    echo ""
    echo -e "  ${CYAN}1${NC}  Start Flink cluster"
    echo -e "  ${CYAN}2${NC}  Stop Flink cluster"
    echo -e "  ${CYAN}3${NC}  Open SQL client                ${DIM}(interactive)${NC}"
    echo -e "  ${CYAN}4${NC}  Run full CDC setup             ${DIM}(catalog + sources + 9 jobs)${NC}"
    echo ""
    echo -e "  ${BOLD}Monitor${NC}"
    echo ""
    echo -e "  ${CYAN}5${NC}  Show running Flink jobs"
    echo -e "  ${CYAN}6${NC}  Show Paimon warehouse contents"
    echo -e "  ${CYAN}7${NC}  Verify row counts              ${DIM}(Paimon batch query)${NC}"
    echo -e "  ${CYAN}8${NC}  Open Flink Web UI              ${DIM}http://localhost:8081${NC}"
    echo -e "  ${CYAN}9${NC}  Open Kibana                    ${DIM}http://localhost:5601${NC}"
    echo ""
    echo -e "  ${CYAN}0${NC}  Exit"
    echo ""
}

wait_for_key() {
    echo ""
    echo -e "${DIM}  Press any key to continue...${NC}"
    read -n 1 -s
}

do_start_flink() {
    if curl -sf http://localhost:8081/overview >/dev/null 2>&1; then
        echo -e "\n${GREEN}✓ Flink is already running.${NC}"
        wait_for_key
        return
    fi

    echo -e "\n${YELLOW}▶ Starting Flink cluster...${NC}"
    "$FLINK_HOME/bin/start-cluster.sh"

    for i in $(seq 1 15); do
        if curl -sf http://localhost:8081/overview >/dev/null 2>&1; then
            break
        fi
        sleep 1
    done

    if curl -sf http://localhost:8081/overview >/dev/null 2>&1; then
        local slots=$(curl -sf http://localhost:8081/overview | python3 -c "import sys,json; print(json.load(sys.stdin).get('slots-total',0))" 2>/dev/null)
        echo -e "${GREEN}✓ Flink is running — ${slots} task slots available${NC}"
        echo -e "  Web UI: http://localhost:8081"
    else
        echo -e "${RED}✗ Flink did not start. Check logs:${NC}"
        echo "  $FLINK_HOME/log/"
    fi
    wait_for_key
}

do_stop_flink() {
    echo -e "\n${YELLOW}▶ Stopping Flink cluster...${NC}"
    "$FLINK_HOME/bin/stop-cluster.sh"
    echo -e "${GREEN}✓ Flink stopped.${NC}"
    wait_for_key
}

do_sql_client() {
    echo -e "\n${YELLOW}▶ Opening SQL client...${NC}"
    echo -e "${DIM}  Tip: paste SQL files from sql/ directory one at a time${NC}"
    echo -e "${DIM}  Type 'quit;' or Ctrl+C to exit${NC}"
    echo ""
    "$FLINK_HOME/bin/sql-client.sh"
}

# Submit a single SQL file to Flink SQL client in batch/non-streaming mode
run_sql_file() {
    local file="$1"
    local label="$2"
    echo -e "  ${CYAN}▸ ${label}${NC}"
    "$FLINK_HOME/bin/sql-client.sh" -f "$file" 2>&1 | while IFS= read -r line; do
        if echo "$line" | grep -qi "successfully submitted\|Job ID"; then
            echo -e "    ${GREEN}✓${NC} $line"
        elif echo "$line" | grep -qi "error\|exception\|failed"; then
            echo -e "    ${RED}✗${NC} $line"
        fi
    done
}

# Submit a self-contained job SQL file
submit_job_file() {
    local label="$1"
    local sqlfile="$2"

    echo -ne "  ${CYAN}▸ ${label}${NC} "

    if [ ! -f "$sqlfile" ]; then
        echo -e "${RED}✗ file not found${NC}"
        return
    fi

    local output=$("$FLINK_HOME/bin/sql-client.sh" -f "$sqlfile" 2>&1)
    local job_id=$(echo "$output" | grep -o 'Job ID: [a-f0-9]*' | head -1 | awk '{print $3}')

    if [ -n "$job_id" ]; then
        echo -e "${GREEN}✓${NC} ${DIM}${job_id:0:12}${NC}"
    else
        local err=$(echo "$output" | grep -i "error\|exception\|failed" | head -1)
        if [ -n "$err" ]; then
            echo -e "${RED}✗${NC}"
            echo -e "    ${RED}${err}${NC}"
        else
            echo -e "${GREEN}✓${NC}"
        fi
    fi
}

do_full_cdc() {
    if ! curl -sf http://localhost:8081/overview >/dev/null 2>&1; then
        echo -e "\n${RED}✗ Flink not running. Start it first (option 1).${NC}"
        wait_for_key
        return
    fi

    if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^qb-mysql$"; then
        echo -e "\n${RED}✗ MySQL not running.${NC}"
        wait_for_key
        return
    fi

    # Check available slots
    local slots=$(curl -sf http://localhost:8081/overview | python3 -c "import sys,json; print(json.load(sys.stdin).get('slots-available',0))" 2>/dev/null)
    if [ "$slots" -lt 9 ] 2>/dev/null; then
        echo -e "\n${YELLOW}⚠  Only ${slots} task slots available, need 9 for all CDC jobs.${NC}"
        echo -e "${DIM}  Restart Flink after running setup.sh to get 10 slots.${NC}"
        echo -ne "  Continue anyway? [y/N] "
        read -n 1 confirm
        echo ""
        if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
            wait_for_key
            return
        fi
    fi

    echo -e "\n${YELLOW}▶ Running full CDC pipeline setup...${NC}"
    echo ""

    # Phase 1: Create Paimon catalog + bronze tables (persists on disk)
    echo -e "${BOLD}  Phase 1: Creating Paimon catalog and bronze tables${NC}"

    local ddl_file=$(mktemp /tmp/cdc-ddl-XXXXXX.sql)
    cat "$SCRIPT_DIR/sql/01-create-paimon-catalog.sql" >> "$ddl_file"
    echo "" >> "$ddl_file"
    cat "$SCRIPT_DIR/sql/03-paimon-bronze-tables.sql" >> "$ddl_file"

    local ddl_output=$("$FLINK_HOME/bin/sql-client.sh" -f "$ddl_file" 2>&1)
    local ddl_errors=$(echo "$ddl_output" | grep -ci "\[ERROR\]" || true)
    rm -f "$ddl_file"

    if [ "$ddl_errors" -gt 0 ]; then
        echo -e "  ${RED}✗ DDL errors found:${NC}"
        echo "$ddl_output" | grep -i "ERROR" | head -5 | while read -r line; do
            echo -e "    ${RED}$line${NC}"
        done
        wait_for_key
        return
    fi
    echo -e "  ${GREEN}✓${NC} Paimon catalog + 9 bronze tables ready"

    # Phase 2: Submit each CDC job (each file is self-contained)
    echo ""
    echo -e "${BOLD}  Phase 2: Submitting 9 CDC streaming jobs${NC}"
    echo -e "${DIM}  Each job: catalog + CDC source + INSERT (self-contained)${NC}"
    echo ""

    local JOBS_DIR="$SCRIPT_DIR/sql/jobs"
    if [ ! -d "$JOBS_DIR" ] || [ -z "$(ls -A "$JOBS_DIR" 2>/dev/null)" ]; then
        echo -e "  ${YELLOW}Generating job files...${NC}"
        bash "$SCRIPT_DIR/generate-jobs.sh" >/dev/null 2>&1
    fi

    submit_job_file "companies"          "$JOBS_DIR/01-companies.sql"
    submit_job_file "vendors"            "$JOBS_DIR/02-vendors.sql"
    submit_job_file "customers"          "$JOBS_DIR/03-customers.sql"
    submit_job_file "bills"              "$JOBS_DIR/04-bills.sql"
    submit_job_file "bill_line_items"    "$JOBS_DIR/05-bill-line-items.sql"
    submit_job_file "invoices"           "$JOBS_DIR/06-invoices.sql"
    submit_job_file "invoice_line_items" "$JOBS_DIR/07-invoice-line-items.sql"
    submit_job_file "payments"           "$JOBS_DIR/08-payments.sql"
    submit_job_file "match_decisions"    "$JOBS_DIR/09-match-decisions.sql"

    # Phase 3: Verify
    echo ""
    sleep 3
    if curl -sf http://localhost:8081/jobs/overview >/dev/null 2>&1; then
        local running=$(curl -sf http://localhost:8081/jobs/overview | python3 -c "
import sys, json
data = json.load(sys.stdin)
running = [j for j in data.get('jobs', []) if j['state'] == 'RUNNING']
print(len(running))
" 2>/dev/null || echo "?")
        echo -e "${GREEN}✓ ${running}/9 CDC jobs running.${NC}"
        if [ "$running" = "9" ]; then
            echo -e "  ${GREEN}All jobs healthy!${NC} Data flowing: MySQL binlog → Paimon"
            echo -e "  ${DIM}Initial snapshot takes ~30s, then switches to binlog streaming.${NC}"
        else
            echo -e "  ${YELLOW}Some jobs may still be starting. Check: http://localhost:8081${NC}"
        fi
    fi

    wait_for_key
}

do_show_jobs() {
    if ! curl -sf http://localhost:8081/overview >/dev/null 2>&1; then
        echo -e "\n${RED}✗ Flink not running.${NC}"
        wait_for_key
        return
    fi

    echo -e "\n${BOLD}  Flink Jobs${NC}\n"

    curl -sf http://localhost:8081/jobs/overview 2>/dev/null | python3 -c "
import sys, json
data = json.load(sys.stdin)
jobs = data.get('jobs', [])
if not jobs:
    print('  No jobs.')
else:
    for j in sorted(jobs, key=lambda x: x.get('name', '')):
        state = j['state']
        name = j.get('name', 'unknown')[:60]
        jid = j['jid'][:12]
        if state == 'RUNNING':
            print(f'  \033[0;32m● {state:<12s}\033[0m {name}  ({jid})')
        elif state == 'FAILED':
            print(f'  \033[0;31m✗ {state:<12s}\033[0m {name}  ({jid})')
        elif state in ('CANCELED', 'FINISHED'):
            print(f'  \033[2m○ {state:<12s}\033[0m {name}  ({jid})')
        elif state == 'RESTARTING':
            print(f'  \033[1;33m↻ {state:<12s}\033[0m {name}  ({jid})')
        else:
            print(f'  ◌ {state:<12s} {name}  ({jid})')
" 2>/dev/null || echo "  Could not fetch jobs."

    wait_for_key
}

do_show_warehouse() {
    echo -e "\n${BOLD}  Paimon Warehouse${NC}\n"
    echo -e "  Path: $WAREHOUSE_PATH"
    echo ""

    if [ ! -d "$WAREHOUSE_PATH/network_graph" ]; then
        echo -e "  ${YELLOW}Empty — no tables yet.${NC}"
        wait_for_key
        return
    fi

    for dir in "$WAREHOUSE_PATH"/network_graph/*/; do
        if [ -d "$dir" ]; then
            table=$(basename "$dir")
            files=$(find "$dir" -name "*.orc" -o -name "*.parquet" -o -name "data-*" 2>/dev/null | wc -l | tr -d ' ')
            snapshots=$(find "$dir" -path "*/snapshot/*" -type f 2>/dev/null | wc -l | tr -d ' ')
            size=$(du -sh "$dir" 2>/dev/null | cut -f1)
            echo -e "  ${CYAN}${table}${NC}  (${files} data files, ${snapshots} snapshots, ${size})"
        fi
    done

    wait_for_key
}

do_verify_counts() {
    if ! curl -sf http://localhost:8081/overview >/dev/null 2>&1; then
        echo -e "\n${RED}✗ Flink not running.${NC}"
        wait_for_key
        return
    fi

    echo -e "\n${BOLD}  Verifying Paimon row counts...${NC}\n"
    echo -e "${DIM}  Running batch queries via SQL client (takes a few seconds)${NC}\n"

    "$FLINK_HOME/bin/sql-client.sh" -f "$SCRIPT_DIR/sql/05-verify-sync.sql" 2>&1 | while IFS= read -r line; do
        # Filter out noise, show data
        if echo "$line" | grep -qE "^\+|^|.*staged_|^Flink SQL>.*SELECT"; then
            echo "  $line"
        fi
    done

    wait_for_key
}

do_open_url() {
    local url="$1"
    local name="$2"
    echo -e "\n${YELLOW}▶ Opening ${name}...${NC}"
    if command -v open &>/dev/null; then
        open "$url"
    elif command -v xdg-open &>/dev/null; then
        xdg-open "$url"
    else
        echo "  Open in browser: $url"
    fi
    wait_for_key
}

# ── Main loop ──

while true; do
    header
    status_bar
    menu

    read -p "  Enter choice: " choice

    case $choice in
        1) do_start_flink ;;
        2) do_stop_flink ;;
        3) do_sql_client ;;
        4) do_full_cdc ;;
        5) do_show_jobs ;;
        6) do_show_warehouse ;;
        7) do_verify_counts ;;
        8) do_open_url "http://localhost:8081" "Flink Web UI" ;;
        9) do_open_url "http://localhost:5601" "Kibana" ;;
        0) echo -e "\n${DIM}Bye.${NC}"; exit 0 ;;
        *) echo -e "\n${RED}Invalid choice.${NC}"; sleep 1 ;;
    esac
done
