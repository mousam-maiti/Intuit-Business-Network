#!/bin/bash
# ============================================================
# QB Network Graph — Classifier Orchestrator
# ============================================================
#
# Usage:
#   ./run.sh                    # Build + batch mode
#   ./run.sh --stream           # Build + stream mode
#   ./run.sh --classify-only    # Build + classify to JSON files
#   ./run.sh --build            # Build only
#   ./run.sh --test             # Run tests
#   ./run.sh --help             # This message
#
# ============================================================

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
DIM='\033[2m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
JAR="$SCRIPT_DIR/target/classifier-orchestrator.jar"

header() {
    echo -e "${CYAN}"
    echo "  ╔══════════════════════════════════════════════════╗"
    echo "  ║   QB Network Graph — Classifier Orchestrator     ║"
    echo "  ╚══════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# ── Check prerequisites ──
check_prereqs() {
    if ! command -v java &>/dev/null; then
        echo -e "${RED}✗ java not found. Install JDK 17+.${NC}"
        exit 1
    fi

    JAVA_VER=$(java -version 2>&1 | head -1 | awk -F'"' '{print $2}' | cut -d. -f1)
    if [ "$JAVA_VER" -lt 17 ] 2>/dev/null; then
        echo -e "${YELLOW}⚠ Java $JAVA_VER detected. JDK 17+ recommended.${NC}"
    fi

    if ! command -v mvn &>/dev/null; then
        echo -e "${RED}✗ mvn not found. Install Maven 3.8+.${NC}"
        exit 1
    fi
}

# ── Build ──
do_build() {
    echo -e "${CYAN}▶ Building...${NC}"
    cd "$SCRIPT_DIR"
    mvn clean package -q -DskipTests 2>&1 | tail -5

    if [ -f "$JAR" ]; then
        SIZE=$(du -h "$JAR" | cut -f1)
        echo -e "  ${GREEN}✓ Built${NC} ${DIM}($SIZE)${NC}"
    else
        echo -e "  ${RED}✗ Build failed${NC}"
        echo -e "  ${DIM}Run: mvn clean package  (for full output)${NC}"
        exit 1
    fi
}

# ── Run ──
do_run() {
    if [ ! -f "$JAR" ]; then
        do_build
    fi

    echo -e "${CYAN}▶ Running...${NC}\n"

    # Pass through all args except --build and --test
    ARGS=()
    for arg in "$@"; do
        case "$arg" in
            --build|--test|--help|-h) ;;
            *) ARGS+=("$arg") ;;
        esac
    done

    cd "$SCRIPT_DIR"
    java -jar "$JAR" "${ARGS[@]}"
}

# ── Test ──
do_test() {
    echo -e "${CYAN}▶ Running tests...${NC}"
    cd "$SCRIPT_DIR"
    mvn test 2>&1
}

# ── Main ──
case "${1:-}" in
    --help|-h)
        header
        echo "  Usage: ./run.sh [options]"
        echo ""
        echo "  Options:"
        echo "    (none)           Build + run in batch mode"
        echo "    --stream         Run in stream mode (tails changelog)"
        echo "    --classify-only  Classify to JSON files (no agent call)"
        echo "    --build          Build only (mvn package)"
        echo "    --test           Run unit tests"
        echo "    --help           This message"
        echo ""
        echo "  Environment:"
        echo "    Edit src/main/resources/app.properties for warehouse path, agent URL, mode, etc."
        echo ""
        ;;
    --build)
        header
        check_prereqs
        do_build
        ;;
    --test)
        header
        check_prereqs
        do_test
        ;;
    *)
        header
        check_prereqs
        do_build
        do_run "$@"
        ;;
esac
