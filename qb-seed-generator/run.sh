#!/bin/bash
# ============================================================
# QB Network Graph — Seed Data Manager
# ============================================================

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m' # No Color

# Config
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SEED_DIR="$SCRIPT_DIR/seed"
MYSQL_CONTAINER="qb-mysql"

header() {
    clear
    echo -e "${CYAN}"
    echo "  ╔══════════════════════════════════════════════════╗"
    echo "  ║   QB Network Graph — Seed Data Manager          ║"
    echo "  ╚══════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

status_bar() {
    echo -e "${DIM}──────────────────────────────────────────────────────${NC}"

    # Check seed files
    if [ -d "$SEED_DIR/mysql" ] && [ -f "$SEED_DIR/mysql/companies.json" ]; then
        local vendors=$(python3.9 -c "import json; print(len(json.load(open('$SEED_DIR/assignments/vendor_assignments.json'))))" 2>/dev/null || echo "?")
        local bills=$(python3.9 -c "import json; print(len(json.load(open('$SEED_DIR/mysql/bills.json'))))" 2>/dev/null || echo "?")
        echo -e "  Seed files:  ${GREEN}✓ present${NC}  (${vendors} vendors, ${bills} bills)"
    else
        echo -e "  Seed files:  ${RED}✗ not generated${NC}"
    fi

    # Check MySQL
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${MYSQL_CONTAINER}$"; then
        local row_count=$(docker exec $MYSQL_CONTAINER mysql -u qb_admin -pqb_admin_pass quickbooks -sNe "SELECT COUNT(*) FROM vendors" 2>/dev/null || echo "0")
        if [ "$row_count" != "0" ] && [ -n "$row_count" ]; then
            echo -e "  MySQL:       ${GREEN}✓ running${NC}  (${row_count} vendor rows)"
        else
            echo -e "  MySQL:       ${YELLOW}● running${NC}  (empty — not seeded)"
        fi
    else
        echo -e "  MySQL:       ${RED}✗ not running${NC}"
    fi

    echo -e "${DIM}──────────────────────────────────────────────────────${NC}"
    echo ""
}

menu() {
    echo -e "  ${BOLD}What do you want to do?${NC}"
    echo ""
    echo -e "  ${CYAN}1${NC}  Generate seed files            ${DIM}python -m src.main generate${NC}"
    echo -e "  ${CYAN}2${NC}  Load seed files into MySQL     ${DIM}python -m src.main seed${NC}"
    echo -e "  ${CYAN}3${NC}  Generate + Load (both)         ${DIM}python -m src.main generate seed${NC}"
    echo ""
    echo -e "  ${CYAN}4${NC}  Start MySQL container          ${DIM}docker start${NC}"
    echo -e "  ${CYAN}5${NC}  Stop MySQL container            ${DIM}docker stop${NC}"
    echo -e "  ${CYAN}6${NC}  Reset MySQL (truncate all)     ${DIM}truncate all tables${NC}"
    echo ""
    echo -e "  ${CYAN}7${NC}  Show seed file stats"
    echo -e "  ${CYAN}8${NC}  Show MySQL table counts"
    echo -e "  ${CYAN}9${NC}  Preview name variations"
    echo ""
    echo -e "  ${CYAN}0${NC}  Exit"
    echo ""
}

wait_for_key() {
    echo ""
    echo -e "${DIM}  Press any key to continue...${NC}"
    read -n 1 -s
}

# ── Actions ──

do_generate() {
    echo -e "\n${YELLOW}▶ Generating seed files...${NC}\n"
    cd "$SCRIPT_DIR"
    python3.9 -m src.main generate
    wait_for_key
}

do_seed() {
    if [ ! -f "$SEED_DIR/mysql/companies.json" ]; then
        echo -e "\n${RED}✗ No seed files found. Run Generate first.${NC}"
        wait_for_key
        return
    fi

    if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${MYSQL_CONTAINER}$"; then
        echo -e "\n${RED}✗ MySQL container not running. Start it first.${NC}"
        wait_for_key
        return
    fi

    echo -e "\n${YELLOW}▶ Loading seed files into MySQL...${NC}\n"
    cd "$SCRIPT_DIR"
    python3.9 -m src.main seed
    wait_for_key
}

do_both() {
    echo -e "\n${YELLOW}▶ Generate + Load...${NC}\n"

    if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${MYSQL_CONTAINER}$"; then
        echo -e "${RED}✗ MySQL container not running. Start it first.${NC}"
        wait_for_key
        return
    fi

    cd "$SCRIPT_DIR"
    python3.9 -m src.main generate seed
    wait_for_key
}

do_start_mysql() {
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${MYSQL_CONTAINER}$"; then
        echo -e "\n${GREEN}✓ MySQL is already running.${NC}"
        wait_for_key
        return
    fi

    # Check if container exists but stopped
    if docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q "^${MYSQL_CONTAINER}$"; then
        echo -e "\n${YELLOW}▶ Starting existing MySQL container...${NC}"
        docker start $MYSQL_CONTAINER
    else
        echo -e "\n${YELLOW}▶ Creating new MySQL container...${NC}"
        docker run -d \
            --name $MYSQL_CONTAINER \
            -p 3306:3306 \
            -e MYSQL_ROOT_PASSWORD=rootpass \
            -e MYSQL_DATABASE=quickbooks \
            -e MYSQL_USER=qb_admin \
            -e MYSQL_PASSWORD=qb_admin_pass \
            -v qb_mysql_data:/var/lib/mysql \
            mysql:8.0 \
            --server-id=1 \
            --log-bin=mysql-bin \
            --binlog-format=ROW \
            --binlog-row-image=FULL \
            --expire-logs-days=7

        echo -e "${DIM}  Waiting for MySQL to be ready...${NC}"
        for i in $(seq 1 30); do
            if docker exec $MYSQL_CONTAINER mysqladmin ping -h localhost --silent 2>/dev/null; then
                break
            fi
            sleep 1
            echo -ne "  ${DIM}${i}s...${NC}\r"
        done
    fi

    echo -e "${GREEN}✓ MySQL is running.${NC}"
    wait_for_key
}

do_stop_mysql() {
    if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${MYSQL_CONTAINER}$"; then
        echo -e "\n${YELLOW}▶ Stopping MySQL...${NC}"
        docker stop $MYSQL_CONTAINER
        echo -e "${GREEN}✓ MySQL stopped. Data persists in volume.${NC}"
    else
        echo -e "\n${DIM}MySQL is not running.${NC}"
    fi
    wait_for_key
}

do_reset_mysql() {
    if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${MYSQL_CONTAINER}$"; then
        echo -e "\n${RED}✗ MySQL container not running.${NC}"
        wait_for_key
        return
    fi

    echo -e "\n${RED}⚠  This will TRUNCATE all data in MySQL.${NC}"
    read -p "  Are you sure? (y/N) " confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        echo -e "  ${DIM}Cancelled.${NC}"
        wait_for_key
        return
    fi

    echo -e "\n${YELLOW}▶ Truncating all tables...${NC}"
    docker exec $MYSQL_CONTAINER mysql -u qb_admin -pqb_admin_pass quickbooks -e "
        SET FOREIGN_KEY_CHECKS = 0;
        TRUNCATE TABLE payments;
        TRUNCATE TABLE bill_line_items;
        TRUNCATE TABLE invoice_line_items;
        TRUNCATE TABLE bills;
        TRUNCATE TABLE invoices;
        TRUNCATE TABLE products_services;
        TRUNCATE TABLE vendors;
        TRUNCATE TABLE customers;
        TRUNCATE TABLE companies;
        SET FOREIGN_KEY_CHECKS = 1;
    " 2>/dev/null

    echo -e "${GREEN}✓ All tables truncated.${NC}"
    wait_for_key
}

do_seed_stats() {
    if [ ! -d "$SEED_DIR" ]; then
        echo -e "\n${RED}✗ No seed directory found.${NC}"
        wait_for_key
        return
    fi

    echo -e "\n${BOLD}  Seed File Stats${NC}\n"

    python3.9 << 'PYEOF'
import json, os

base = os.environ.get("SEED_DIR", "seed")

files = {
    "Vendor pool (truth)":   f"{base}/pools/vendor_pool.json",
    "Client pool (truth)":   f"{base}/pools/client_pool.json",
    "Vendor assignments":    f"{base}/assignments/vendor_assignments.json",
    "Customer assignments":  f"{base}/assignments/customer_assignments.json",
    "Companies":             f"{base}/mysql/companies.json",
    "Bills":                 f"{base}/mysql/bills.json",
    "Bill line items":       f"{base}/mysql/bill_line_items.json",
    "Invoices":              f"{base}/mysql/invoices.json",
    "Invoice line items":    f"{base}/mysql/invoice_line_items.json",
    "Payments":              f"{base}/mysql/payments.json",
}

for label, path in files.items():
    if os.path.exists(path):
        data = json.load(open(path))
        size = os.path.getsize(path)
        size_str = f"{size/1024:.0f}KB" if size < 1048576 else f"{size/1048576:.1f}MB"
        print(f"  {label:<25s}  {len(data):>8,} records  ({size_str})")
    else:
        print(f"  {label:<25s}  — missing")
PYEOF

    wait_for_key
}

do_mysql_counts() {
    if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${MYSQL_CONTAINER}$"; then
        echo -e "\n${RED}✗ MySQL container not running.${NC}"
        wait_for_key
        return
    fi

    echo -e "\n${BOLD}  MySQL Table Counts${NC}\n"

    docker exec $MYSQL_CONTAINER mysql -u qb_admin -pqb_admin_pass quickbooks -t -e "
        SELECT 'companies' AS table_name, COUNT(*) AS row_count FROM companies
        UNION ALL SELECT 'vendors', COUNT(*) FROM vendors
        UNION ALL SELECT 'customers', COUNT(*) FROM customers
        UNION ALL SELECT 'bills', COUNT(*) FROM bills
        UNION ALL SELECT 'bill_line_items', COUNT(*) FROM bill_line_items
        UNION ALL SELECT 'invoices', COUNT(*) FROM invoices
        UNION ALL SELECT 'invoice_line_items', COUNT(*) FROM invoice_line_items
        UNION ALL SELECT 'payments', COUNT(*) FROM payments
        UNION ALL SELECT 'products_services', COUNT(*) FROM products_services
        UNION ALL SELECT 'match_decisions', COUNT(*) FROM match_decisions;
    " 2>/dev/null

    wait_for_key
}

do_preview_variations() {
    if [ ! -f "$SEED_DIR/assignments/vendor_assignments.json" ]; then
        echo -e "\n${RED}✗ No seed files found. Run Generate first.${NC}"
        wait_for_key
        return
    fi

    echo -e "\n${BOLD}  Name Variations (entity resolution challenge)${NC}\n"

    SEED_DIR="$SEED_DIR" python3.9 << 'PYEOF'
import json, os
from collections import defaultdict

base = os.environ["SEED_DIR"]
pool = json.load(open(f"{base}/pools/vendor_pool.json"))
assignments = json.load(open(f"{base}/assignments/vendor_assignments.json"))

pool_names = {v["serial_id"]: v["canonical_name"] for v in pool}

# Group display names by serial_id
variants = defaultdict(set)
for rec in assignments:
    variants[rec["pool_serial_id"]].add(rec["display_name"])

# Show entries with most variations
multi = sorted(
    [(sid, names) for sid, names in variants.items() if len(names) > 1],
    key=lambda x: -len(x[1])
)

print(f"  {len(multi)}/{len(variants)} vendors have multiple display names\n")

for sid, names in multi[:15]:
    canonical = pool_names.get(sid, "?")
    print(f"  {sid} canonical: \"{canonical}\"")
    for n in sorted(names):
        marker = "  ✓" if n == canonical else "  ≠"
        print(f"      {marker} \"{n}\"")
    print()
PYEOF

    wait_for_key
}

# ── Main loop ──

while true; do
    header
    status_bar
    menu

    read -p "  Enter choice: " choice

    case $choice in
        1) do_generate ;;
        2) do_seed ;;
        3) do_both ;;
        4) do_start_mysql ;;
        5) do_stop_mysql ;;
        6) do_reset_mysql ;;
        7) do_seed_stats ;;
        8) do_mysql_counts ;;
        9) do_preview_variations ;;
        0) echo -e "\n${DIM}Bye.${NC}"; exit 0 ;;
        *) echo -e "\n${RED}Invalid choice.${NC}"; sleep 1 ;;
    esac
done