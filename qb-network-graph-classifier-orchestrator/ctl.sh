#!/bin/bash
# ============================================================
# QB Network Graph — Classifier Orchestrator   [Control Panel]
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
JAR="$SCRIPT_DIR/target/classifier-orchestrator.jar"
PID_FILE="$SCRIPT_DIR/.classifier.pid"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/classifier.log"

# ── Colors ──────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# ── Helpers ─────────────────────────────────────────────────

header() {
    clear
    echo -e "${CYAN}"
    echo "  ╔══════════════════════════════════════════════════╗"
    echo "  ║   QB Network Graph — Classifier Orchestrator    ║"
    echo "  ╠══════════════════════════════════════════════════╣"
    echo "  ║              Control Panel                       ║"
    echo "  ╚══════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

is_running() {
    if [ -f "$PID_FILE" ]; then
        local pid
        pid=$(cat "$PID_FILE" 2>/dev/null)
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
        # Stale PID file
        rm -f "$PID_FILE"
    fi
    return 1
}

get_pid() {
    cat "$PID_FILE" 2>/dev/null
}

status_line() {
    if is_running; then
        local pid
        pid=$(get_pid)
        local uptime
        uptime=$(ps -o etime= -p "$pid" 2>/dev/null | xargs)
        echo -e "  Status: ${GREEN}RUNNING${NC}  ${DIM}(PID $pid, uptime $uptime)${NC}"
    else
        echo -e "  Status: ${DIM}STOPPED${NC}"
    fi
    echo ""
}

check_prereqs() {
    if ! command -v java &>/dev/null; then
        echo -e "  ${RED}java not found. Install JDK 17+.${NC}"
        return 1
    fi
    if ! command -v mvn &>/dev/null; then
        echo -e "  ${RED}mvn not found. Install Maven 3.8+.${NC}"
        return 1
    fi
    return 0
}

ensure_jar() {
    if [ ! -f "$JAR" ]; then
        echo -e "  ${YELLOW}JAR not found — building first...${NC}"
        do_build
    fi
}

# ── Actions ─────────────────────────────────────────────────

do_build() {
    echo -e "  ${CYAN}Building...${NC}"
    cd "$SCRIPT_DIR"
    mvn clean package -q -DskipTests 2>&1 | tail -5

    if [ -f "$JAR" ]; then
        local size
        size=$(du -h "$JAR" | cut -f1)
        echo -e "  ${GREEN}Build successful${NC} ${DIM}($size)${NC}"
    else
        echo -e "  ${RED}Build failed.${NC} Run ${DIM}mvn clean package${NC} for details."
        return 1
    fi
}

do_test() {
    echo -e "  ${CYAN}Running tests...${NC}\n"
    cd "$SCRIPT_DIR"
    mvn test 2>&1
}

start_process() {
    local mode="$1"
    local extra_flags="$2"

    if is_running; then
        echo -e "  ${YELLOW}Already running${NC} (PID $(get_pid)). Stop it first."
        return 1
    fi

    ensure_jar || return 1
    mkdir -p "$LOG_DIR"

    local args=""
    [ "$mode" = "stream" ] && args="--stream"
    [ "$mode" = "batch" ]  && args="--batch"
    [ -n "$extra_flags" ]  && args="$args $extra_flags"

    echo -e "  ${CYAN}Starting in ${BOLD}${mode}${NC}${CYAN} mode...${NC}"
    [ -n "$extra_flags" ] && echo -e "  ${DIM}Flags: $extra_flags${NC}"
    echo -e "  ${DIM}Log:   $LOG_FILE${NC}"

    cd "$SCRIPT_DIR"
    nohup java -jar "$JAR" $args > /dev/null 2>&1 &
    local pid=$!
    echo "$pid" > "$PID_FILE"

    sleep 1
    if kill -0 "$pid" 2>/dev/null; then
        echo -e "  ${GREEN}Started${NC} (PID $pid)"
    else
        rm -f "$PID_FILE"
        echo -e "  ${RED}Failed to start.${NC} Check log: $LOG_FILE"
        return 1
    fi
}

stop_process() {
    if ! is_running; then
        echo -e "  ${DIM}Not running.${NC}"
        return 0
    fi

    local pid
    pid=$(get_pid)
    echo -e "  ${CYAN}Stopping${NC} (PID $pid)..."

    kill "$pid" 2>/dev/null

    # Wait up to 10 seconds for graceful shutdown
    local waited=0
    while kill -0 "$pid" 2>/dev/null && [ $waited -lt 10 ]; do
        sleep 1
        waited=$((waited + 1))
    done

    if kill -0 "$pid" 2>/dev/null; then
        echo -e "  ${YELLOW}Forcing stop...${NC}"
        kill -9 "$pid" 2>/dev/null
        sleep 1
    fi

    rm -f "$PID_FILE"
    echo -e "  ${GREEN}Stopped.${NC}"
}

run_foreground() {
    local mode="$1"
    local extra_flags="$2"

    if is_running; then
        echo -e "  ${YELLOW}Background process running${NC} (PID $(get_pid)). Stop it first."
        return 1
    fi

    ensure_jar || return 1

    local args=""
    [ "$mode" = "stream" ] && args="--stream"
    [ "$mode" = "batch" ]  && args="--batch"
    [ -n "$extra_flags" ]  && args="$args $extra_flags"

    echo -e "  ${CYAN}Running in ${BOLD}${mode}${NC}${CYAN} mode (foreground)...${NC}"
    [ -n "$extra_flags" ] && echo -e "  ${DIM}Flags: $extra_flags${NC}"
    echo -e "  ${DIM}Press Ctrl+C to stop.${NC}\n"

    cd "$SCRIPT_DIR"
    java -jar "$JAR" $args
}

tail_log() {
    if [ ! -f "$LOG_FILE" ]; then
        echo -e "  ${DIM}No log file yet.${NC}"
        return 0
    fi
    echo -e "  ${DIM}Tailing $LOG_FILE  (Ctrl+C to stop)${NC}\n"
    tail -f "$LOG_FILE"
}

show_dead_letters() {
    local dl_dir="$SCRIPT_DIR/dead-letter"
    local count
    count=$(ls -1 "$dl_dir"/*.json 2>/dev/null | wc -l | xargs)

    if [ "$count" -eq 0 ] 2>/dev/null; then
        echo -e "  ${GREEN}No dead-letter files.${NC}"
        return 0
    fi

    echo -e "  ${YELLOW}$count dead-letter file(s):${NC}\n"
    for f in "$dl_dir"/*.json; do
        echo -e "  ${DIM}$(basename "$f")${NC}"
        python3 -m json.tool "$f" 2>/dev/null | head -20 | sed 's/^/    /'
        echo ""
    done
}

clear_dead_letters() {
    local dl_dir="$SCRIPT_DIR/dead-letter"
    local count
    count=$(ls -1 "$dl_dir"/*.json 2>/dev/null | wc -l | xargs)

    if [ "$count" -eq 0 ] 2>/dev/null; then
        echo -e "  ${DIM}No dead-letter files to clear.${NC}"
        return 0
    fi

    rm -f "$dl_dir"/*.json
    echo -e "  ${GREEN}Cleared $count dead-letter file(s).${NC}"
}

# ── Menu ────────────────────────────────────────────────────

show_menu() {
    echo -e "  ${BOLD}Start / Stop${NC}"
    echo -e "    1)  Start stream mode           ${DIM}(background)${NC}"
    echo -e "    2)  Start stream mode + reset    ${DIM}(background, reprocess all)${NC}"
    echo -e "    3)  Start batch mode             ${DIM}(background)${NC}"
    echo -e "    4)  Stop"
    echo ""
    echo -e "  ${BOLD}Run (foreground)${NC}"
    echo -e "    5)  Run stream                   ${DIM}(Ctrl+C to stop)${NC}"
    echo -e "    6)  Run stream + reset"
    echo -e "    7)  Run batch"
    echo -e "    8)  Run batch dry-run"
    echo -e "    9)  Run classify-only            ${DIM}(JSON output, no agent)${NC}"
    echo ""
    echo -e "  ${BOLD}Tools${NC}"
    echo -e "    b)  Build"
    echo -e "    t)  Run tests"
    echo -e "    l)  Tail log"
    echo -e "    d)  Show dead-letter files"
    echo -e "    c)  Clear dead-letter files"
    echo ""
    echo -e "    q)  Quit"
    echo ""
}

# ── Main ────────────────────────────────────────────────────

# Non-interactive mode: pass arguments directly
if [ $# -gt 0 ]; then
    case "$1" in
        start)
            mode="${2:-stream}"
            flags=""
            [ "$3" = "--reset" ] && flags="--reset"
            start_process "$mode" "$flags"
            ;;
        stop)
            stop_process
            ;;
        status)
            status_line
            ;;
        restart)
            stop_process
            mode="${2:-stream}"
            flags=""
            [ "$3" = "--reset" ] && flags="--reset"
            sleep 1
            start_process "$mode" "$flags"
            ;;
        log)
            tail_log
            ;;
        *)
            echo "Usage: $0 {start [batch|stream] [--reset] | stop | status | restart [batch|stream] [--reset] | log}"
            ;;
    esac
    exit 0
fi

# Interactive menu loop
check_prereqs || exit 1

while true; do
    header
    status_line
    show_menu

    echo -ne "  ${BOLD}Choose [1-9, b/t/l/d/c/q]:${NC} "
    read -r choice

    echo ""

    case "$choice" in
        1) start_process "stream" ""          ;;
        2) start_process "stream" "--reset"   ;;
        3) start_process "batch"  ""          ;;
        4) stop_process                       ;;
        5) run_foreground "stream" ""         ;;
        6) run_foreground "stream" "--reset"  ;;
        7) run_foreground "batch"  ""         ;;
        8) run_foreground "batch"  "--classify-only" ;;
        9) DRY_RUN=true run_foreground "batch" "--classify-only" ;;
        b|B) do_build     ;;
        t|T) do_test      ;;
        l|L) tail_log     ;;
        d|D) show_dead_letters    ;;
        c|C) clear_dead_letters   ;;
        q|Q) echo -e "  ${DIM}Bye.${NC}"; exit 0 ;;
        *)   echo -e "  ${RED}Invalid choice.${NC}" ;;
    esac

    echo ""
    echo -ne "  ${DIM}Press Enter to continue...${NC}"
    read -r
done
