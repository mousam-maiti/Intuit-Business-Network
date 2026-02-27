#!/bin/bash
# ============================================================
# QB Network Graph CDC — Flink + Paimon Setup (Native)
# ============================================================
# Installs Flink locally, drops in Paimon + CDC + Hadoop JARs,
# configures for local filesystem warehouse.
#
# MySQL stays in Docker (qb-mysql on localhost:3306)
# Flink runs natively — no permission issues with local FS.
# Prometheus metrics at :9249, scraped by OTEL Collector.
# ============================================================

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
DIM='\033[2m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Config ──
FLINK_VERSION="1.18.1"
FLINK_SCALA="2.12"
PAIMON_VERSION="0.8.2"
CDC_VERSION="3.1.1"
MYSQL_JDBC_VERSION="8.3.0"

INSTALL_DIR="${FLINK_INSTALL_DIR:-$HOME/flink}"
WAREHOUSE_PATH="${PAIMON_WAREHOUSE_PATH:-/Users/mousammaiti/IntuitQB-StreamHouse}"

echo -e "${CYAN}"
echo "  ╔══════════════════════════════════════════════════╗"
echo "  ║   QB Network Graph CDC — Flink + Paimon         ║"
echo "  ╚══════════════════════════════════════════════════╝"
echo -e "${NC}"
echo -e "  Flink:     ${FLINK_VERSION}"
echo -e "  Paimon:    ${PAIMON_VERSION}"
echo -e "  CDC:       ${CDC_VERSION}"
echo -e "  Install:   ${INSTALL_DIR}"
echo -e "  Warehouse: ${WAREHOUSE_PATH}"
echo ""

# ── Step 1: Check Java ──
echo -e "${YELLOW}Step 1: Checking Java...${NC}"
if command -v java &>/dev/null; then
    JAVA_VER=$(java -version 2>&1 | head -1)
    echo -e "  ${GREEN}✓${NC} $JAVA_VER"
else
    echo -e "  ${RED}✗ Java not found. Install Java 11:${NC}"
    echo "    brew install openjdk@11"
    exit 1
fi

# ── Step 2: Download Flink ──
echo -e "\n${YELLOW}Step 2: Installing Flink...${NC}"
FLINK_DIR="$INSTALL_DIR/flink-${FLINK_VERSION}"
FLINK_TARBALL="flink-${FLINK_VERSION}-bin-scala_${FLINK_SCALA}.tgz"
FLINK_URL="https://archive.apache.org/dist/flink/flink-${FLINK_VERSION}/${FLINK_TARBALL}"

if [ -d "$FLINK_DIR" ]; then
    echo -e "  ${DIM}✓ Flink already installed at ${FLINK_DIR}${NC}"
else
    mkdir -p "$INSTALL_DIR"
    if [ ! -f "$INSTALL_DIR/$FLINK_TARBALL" ]; then
        echo -e "  ${CYAN}↓ Downloading Flink ${FLINK_VERSION}...${NC}"
        curl -fSL --progress-bar -o "$INSTALL_DIR/$FLINK_TARBALL" "$FLINK_URL"
    fi
    echo -e "  ${CYAN}↑ Extracting...${NC}"
    tar -xzf "$INSTALL_DIR/$FLINK_TARBALL" -C "$INSTALL_DIR"
    echo -e "  ${GREEN}✓ Flink installed at ${FLINK_DIR}${NC}"
fi

export FLINK_HOME="$FLINK_DIR"

# ── Step 3: Download connector JARs ──
echo -e "\n${YELLOW}Step 3: Downloading connector JARs into Flink lib/...${NC}"

download_jar() {
    local name="$1"
    local url="$2"
    local dest="$FLINK_HOME/lib/$(basename $url)"

    if [ -f "$dest" ]; then
        echo -e "  ${DIM}✓ $name (exists)${NC}"
        return
    fi

    echo -e "  ${CYAN}↓ $name${NC}"
    curl -fSL --progress-bar -o "$dest" "$url"
    echo -e "  ${GREEN}✓ $name${NC}"
}

# Paimon Flink connector
download_jar "Paimon Flink 1.18" \
    "https://repo1.maven.org/maven2/org/apache/paimon/paimon-flink-1.18/${PAIMON_VERSION}/paimon-flink-1.18-${PAIMON_VERSION}.jar"

# Flink CDC MySQL connector
download_jar "Flink CDC MySQL ${CDC_VERSION}" \
    "https://repo1.maven.org/maven2/org/apache/flink/flink-sql-connector-mysql-cdc/${CDC_VERSION}/flink-sql-connector-mysql-cdc-${CDC_VERSION}.jar"

# MySQL JDBC driver
download_jar "MySQL JDBC ${MYSQL_JDBC_VERSION}" \
    "https://repo1.maven.org/maven2/com/mysql/mysql-connector-j/${MYSQL_JDBC_VERSION}/mysql-connector-j-${MYSQL_JDBC_VERSION}.jar"

# Hadoop uber JAR (required by Paimon for filesystem access)
download_jar "Hadoop Uber" \
    "https://repo1.maven.org/maven2/org/apache/flink/flink-shaded-hadoop-2-uber/2.8.3-10.0/flink-shaded-hadoop-2-uber-2.8.3-10.0.jar"

echo -e "\n  JARs in ${FLINK_HOME}/lib/:"
ls -lh "$FLINK_HOME"/lib/paimon-*.jar "$FLINK_HOME"/lib/flink-sql-connector-mysql-*.jar "$FLINK_HOME"/lib/mysql-connector-*.jar "$FLINK_HOME"/lib/flink-shaded-hadoop-*.jar 2>/dev/null | awk '{print "    " $NF " (" $5 ")"}'

# ── Step 4: Enable Prometheus metrics plugin ──
echo -e "\n${YELLOW}Step 4: Enabling Prometheus metrics plugin...${NC}"
PROM_PLUGIN=$(find "$FLINK_HOME/plugins" -name "flink-metrics-prometheus-*.jar" 2>/dev/null | head -1)
if [ -n "$PROM_PLUGIN" ]; then
    PROM_JAR=$(basename "$PROM_PLUGIN")
    if [ -f "$FLINK_HOME/lib/$PROM_JAR" ]; then
        echo -e "  ${DIM}✓ $PROM_JAR already in lib/${NC}"
    else
        cp "$PROM_PLUGIN" "$FLINK_HOME/lib/"
        echo -e "  ${GREEN}✓${NC} Copied $PROM_JAR → lib/"
    fi
else
    echo -e "  ${YELLOW}●${NC} Prometheus plugin not found in plugins/ — metrics export disabled"
fi

# ── Step 5: Configure Flink ──
echo -e "\n${YELLOW}Step 5: Configuring Flink...${NC}"

cat > "$FLINK_HOME/conf/flink-conf.yaml" << EOF
# ── QB Network Graph CDC — Flink Config ──
jobmanager.rpc.address: localhost
jobmanager.rpc.port: 6123
jobmanager.memory.process.size: 1600m

taskmanager.memory.process.size: 2048m
taskmanager.numberOfTaskSlots: 10

parallelism.default: 1

# Checkpointing
state.backend: hashmap
state.checkpoints.dir: file://${WAREHOUSE_PATH}/_checkpoints
state.savepoints.dir: file://${WAREHOUSE_PATH}/_savepoints
execution.checkpointing.interval: 30s
execution.checkpointing.mode: EXACTLY_ONCE
execution.checkpointing.min-pause: 10s

# Web UI
rest.port: 8081
rest.flamegraph.enabled: true

# SQL Client
sql-client.execution.result-mode: TABLEAU

# ── Prometheus Metrics Reporter ──
# Exposes metrics at :9249/metrics
# OTEL Collector scrapes this endpoint
metrics.reporter.prom.factory.class: org.apache.flink.metrics.prometheus.PrometheusReporterFactory
metrics.reporter.prom.port: 9249
EOF

echo -e "  ${GREEN}✓${NC} flink-conf.yaml written (20 task slots, 6GB TM)"
echo -e "  ${GREEN}✓${NC} Prometheus metrics at http://localhost:9249/metrics"

# ── Step 6: Create warehouse directory ──
echo -e "\n${YELLOW}Step 6: Creating warehouse directory...${NC}"
mkdir -p "$WAREHOUSE_PATH"
echo -e "  ${GREEN}✓${NC} $WAREHOUSE_PATH"

# ── Step 7: Check MySQL ──
echo -e "\n${YELLOW}Step 7: Checking MySQL...${NC}"
if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^qb-mysql$"; then
    ROW_COUNT=$(docker exec qb-mysql mysql -u qb_admin -pqb_admin_pass quickbooks -sNe "SELECT COUNT(*) FROM vendors" 2>/dev/null || echo "0")
    echo -e "  ${GREEN}✓${NC} qb-mysql running (${ROW_COUNT} vendor rows)"
else
    echo -e "  ${RED}✗${NC} qb-mysql not running. Start it first:"
    echo "    docker start qb-mysql"
    exit 1
fi

# ── Step 8: Set FLINK_HOME in shell profile ──
echo -e "\n${YELLOW}Step 8: Configuring shell environment...${NC}"

# Local env file for run-pipeline.sh
echo "export FLINK_HOME=\"$FLINK_HOME\"" > "$SCRIPT_DIR/.flink-env"
echo "export PAIMON_WAREHOUSE_PATH=\"$WAREHOUSE_PATH\"" >> "$SCRIPT_DIR/.flink-env"
echo -e "  ${GREEN}✓${NC} .flink-env written"

# Add to shell profile so $FLINK_HOME works in any terminal
SHELL_RC="$HOME/.zshrc"
[ -f "$HOME/.bash_profile" ] && [ ! -f "$HOME/.zshrc" ] && SHELL_RC="$HOME/.bash_profile"

if ! grep -q "FLINK_HOME" "$SHELL_RC" 2>/dev/null; then
    echo "" >> "$SHELL_RC"
    echo "# Flink (added by qb-network-graph-cdc setup)" >> "$SHELL_RC"
    echo "export FLINK_HOME=\"$FLINK_HOME\"" >> "$SHELL_RC"
    echo "export PATH=\"\$FLINK_HOME/bin:\$PATH\"" >> "$SHELL_RC"
    echo -e "  ${GREEN}✓${NC} Added FLINK_HOME to $SHELL_RC"
else
    echo -e "  ${DIM}✓ FLINK_HOME already in $SHELL_RC${NC}"
fi

# ── Done ──
echo -e "\n${GREEN}═══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}Setup complete!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
echo ""
echo -e "  FLINK_HOME: ${CYAN}${FLINK_HOME}${NC}"
echo ""
echo -e "  ${YELLOW}▸ Open a new terminal (or run: source $SHELL_RC)${NC}"
echo -e "  ${YELLOW}▸ Then:${NC}"
echo ""
echo -e "  Start Flink:    ${CYAN}\$FLINK_HOME/bin/start-cluster.sh${NC}"
echo -e "  Web UI:         ${CYAN}http://localhost:8081${NC}"
echo -e "  Run pipeline:   ${CYAN}./run-pipeline.sh${NC}  (option 4)"
echo -e "  Stop Flink:     ${CYAN}\$FLINK_HOME/bin/stop-cluster.sh${NC}"
echo ""
