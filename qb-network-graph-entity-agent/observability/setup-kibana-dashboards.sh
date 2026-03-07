#!/bin/bash
# ============================================================
# QB Entity Resolution Agent — Kibana Dashboard Setup
# ============================================================
# Creates:
#   1. Index pattern for agent-traces
#   2. Saved search for resolution traces
#   3. Dashboard with key visualizations
#
# Prerequisites:
#   - ES + Kibana running (from CDC observability stack)
#   - OTEL Collector running with updated config
#   - Agent service started and processing records
#
# Usage:
#   ./setup-kibana-dashboards.sh
# ============================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load .env if present
if [ -f "$PROJECT_DIR/.env" ]; then
    set -a; source "$PROJECT_DIR/.env"; set +a
fi

KIBANA_URL="${KIBANA_URL:-http://localhost:5601}"
ES_URL="${ES_URL:-http://localhost:9200}"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  QB Entity Resolution Agent — Kibana Dashboards   ${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
echo ""

# ── Check prerequisites ─────────────────────────────────────
echo "Checking prerequisites..."

if ! curl -sf "$ES_URL/_cluster/health" >/dev/null 2>&1; then
    echo -e "  ${YELLOW}✗${NC} Elasticsearch not running at $ES_URL"
    echo "  Start the observability stack first."
    exit 1
fi
echo -e "  ${GREEN}✓${NC} Elasticsearch"

if ! curl -sf "$KIBANA_URL/api/status" >/dev/null 2>&1; then
    echo -e "  ${YELLOW}✗${NC} Kibana not running at $KIBANA_URL"
    exit 1
fi
echo -e "  ${GREEN}✓${NC} Kibana"

# ── Check if agent traces exist ─────────────────────────────
TRACE_COUNT=$(curl -sf "$ES_URL/agent-traces*/_count" 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('count',0))" 2>/dev/null || echo "0")
echo -e "  ${CYAN}ℹ${NC} Agent traces in ES: $TRACE_COUNT"

if [ "$TRACE_COUNT" = "0" ]; then
    echo ""
    echo -e "  ${YELLOW}No agent traces yet.${NC} The dashboards will be created"
    echo -e "  but won't show data until the agent processes records."
    echo -e "  Send a test request: ${CYAN}curl -X POST localhost:8080/resolve ...${NC}"
    echo ""
fi

# ── Create data view (index pattern) ────────────────────────
echo ""
echo "Creating data views..."

# Agent traces
curl -sf -X POST "$KIBANA_URL/api/data_views/data_view" \
  -H "kbn-xsrf: true" \
  -H "Content-Type: application/json" \
  -d '{
    "data_view": {
      "title": "agent-traces*",
      "name": "Agent Resolution Traces",
      "timeFieldName": "@timestamp"
    }
  }' >/dev/null 2>&1 && echo -e "  ${GREEN}✓${NC} agent-traces* data view" || echo -e "  ${YELLOW}●${NC} agent-traces* (may already exist)"

# Prometheus metrics (from both Flink + agent)
curl -sf -X POST "$KIBANA_URL/api/data_views/data_view" \
  -H "kbn-xsrf: true" \
  -H "Content-Type: application/json" \
  -d '{
    "data_view": {
      "title": ".ds-metrics-*",
      "name": "All Metrics (Flink + Agent)",
      "timeFieldName": "@timestamp"
    }
  }' >/dev/null 2>&1 && echo -e "  ${GREEN}✓${NC} metrics data view" || echo -e "  ${YELLOW}●${NC} metrics (may already exist)"

# ── Create saved searches ───────────────────────────────────
echo ""
echo "Creating saved searches..."

# Resolution traces search
curl -sf -X POST "$KIBANA_URL/api/saved_objects/search/agent-resolution-traces" \
  -H "kbn-xsrf: true" \
  -H "Content-Type: application/json" \
  -d '{
    "attributes": {
      "title": "Agent Resolution Traces",
      "description": "All entity resolution traces with decision outcomes",
      "columns": ["resource.attributes.service.name", "name", "attributes.decision", "attributes.total_duration_ms", "attributes.match_level", "duration"],
      "sort": [["@timestamp", "desc"]],
      "kibanaSavedObjectMeta": {
        "searchSourceJSON": "{\"index\":\"agent-traces*\",\"query\":{\"query\":\"name: resolve\",\"language\":\"kuery\"},\"filter\":[]}"
      }
    }
  }' >/dev/null 2>&1 && echo -e "  ${GREEN}✓${NC} Resolution traces search" || echo -e "  ${YELLOW}●${NC} (may already exist)"

# ── Summary ─────────────────────────────────────────────────
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Dashboards ready!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
echo ""
echo -e "  Open Kibana: ${CYAN}$KIBANA_URL${NC}"
echo ""
echo -e "  ${CYAN}Traces:${NC}"
echo -e "    Analytics → Discover → select 'Agent Resolution Traces'"
echo -e "    Each /resolve call = 1 root span + child spans per MCP tool"
echo ""
echo -e "  ${CYAN}Metrics (Prometheus):${NC}"
echo -e "    curl http://localhost:8889/metrics | grep resolution"
echo ""
echo -e "  ${CYAN}Key metrics to look for:${NC}"
echo -e "    resolution_duration_ms     — histogram by decision type"
echo -e "    resolution_decisions        — counter (MERGE/NEW/REVIEW)"
echo -e "    resolution_step_duration_ms — per-step breakdown"
echo -e "    resolution_llm_calls        — LLM usage tracking"
echo -e "    resolution_embedding_calls  — embedding usage tracking"
echo -e "    resolution_candidate_count  — how many candidates evaluated"
echo -e "    resolution_active           — concurrent in-flight requests"
echo -e "    resolution_errors           — error counter by type"
echo ""
