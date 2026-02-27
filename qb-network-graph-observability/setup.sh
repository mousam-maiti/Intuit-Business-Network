#!/bin/bash
# ============================================================
# QB Observability Stack — Setup
# ============================================================
# Starts: Elasticsearch + Kibana + OTEL Collector
# All on Docker network: qb-observability
#
# Endpoints after setup:
#   Elasticsearch:  http://localhost:9200
#   Kibana:         http://localhost:5601
#   OTEL gRPC:      localhost:4317  (send metrics here)
#   OTEL HTTP:      localhost:4318
# ============================================================

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
DIM='\033[2m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo -e "${CYAN}"
echo "  ╔══════════════════════════════════════════════════╗"
echo "  ║   QB Observability Stack                        ║"
echo "  ╚══════════════════════════════════════════════════╝"
echo -e "${NC}"

# ── Step 1: Docker network ──
echo -e "${YELLOW}Step 1: Docker network...${NC}"
if docker network inspect qb-observability >/dev/null 2>&1; then
    echo -e "  ${DIM}✓ qb-observability exists${NC}"
else
    docker network create qb-observability
    echo -e "  ${GREEN}✓ Created qb-observability${NC}"
fi

# ── Step 2: Elasticsearch ──
echo -e "\n${YELLOW}Step 2: Elasticsearch...${NC}"
if docker ps --format '{{.Names}}' | grep -q "^qb-elasticsearch$"; then
    echo -e "  ${DIM}✓ Already running${NC}"
else
    docker rm -f qb-elasticsearch 2>/dev/null || true
    docker run -d \
        --name qb-elasticsearch \
        --network qb-observability \
        -p 9200:9200 \
        -e discovery.type=single-node \
        -e xpack.security.enabled=false \
        -e xpack.security.http.ssl.enabled=false \
        -e ES_JAVA_OPTS="-Xms512m -Xmx512m" \
        -e cluster.name=qb-observability \
        -v qb_es_data:/usr/share/elasticsearch/data \
        docker.elastic.co/elasticsearch/elasticsearch:8.12.2
    echo -e "  ${GREEN}✓ Started${NC}"
fi

echo -e "  ${DIM}Waiting for Elasticsearch...${NC}"
for i in $(seq 1 60); do
    if curl -sf http://localhost:9200/_cluster/health >/dev/null 2>&1; then
        break
    fi
    sleep 2
done

if curl -sf http://localhost:9200/_cluster/health >/dev/null 2>&1; then
    echo -e "  ${GREEN}✓${NC} Elasticsearch ready at http://localhost:9200"
else
    echo -e "  ${RED}✗ Elasticsearch did not start${NC}"
    exit 1
fi

# ── Step 3: Kibana ──
echo -e "\n${YELLOW}Step 3: Kibana...${NC}"
if docker ps --format '{{.Names}}' | grep -q "^qb-kibana$"; then
    echo -e "  ${DIM}✓ Already running${NC}"
else
    docker rm -f qb-kibana 2>/dev/null || true
    docker run -d \
        --name qb-kibana \
        --network qb-observability \
        -p 5601:5601 \
        -e ELASTICSEARCH_HOSTS=http://qb-elasticsearch:9200 \
        -e xpack.security.enabled=false \
        docker.elastic.co/kibana/kibana:8.12.2
    echo -e "  ${GREEN}✓ Started (takes ~30s to be ready)${NC}"
fi

# ── Step 4: OTEL Collector ──
echo -e "\n${YELLOW}Step 4: OTEL Collector...${NC}"
if docker ps --format '{{.Names}}' | grep -q "^qb-otel-collector$"; then
    echo -e "  ${DIM}✓ Already running${NC}"
else
    docker rm -f qb-otel-collector 2>/dev/null || true
    docker run -d \
        --name qb-otel-collector \
        --network qb-observability \
        -p 4317:4317 \
        -p 4318:4318 \
        -p 8889:8889 \
        -v "$SCRIPT_DIR/otel-collector-config.yaml:/etc/otelcol-contrib/config.yaml" \
        otel/opentelemetry-collector-contrib:0.96.0
    echo -e "  ${GREEN}✓ Started${NC}"
fi

# ── Step 5: Create Kibana data views ──
echo -e "\n${YELLOW}Step 5: Creating Kibana data views...${NC}"

# Wait for Kibana
for i in $(seq 1 60); do
    if curl -sf http://localhost:5601/api/status >/dev/null 2>&1; then
        break
    fi
    sleep 2
done

curl -sf -X POST "http://localhost:5601/api/data_views/data_view" \
    -H "kbn-xsrf: true" \
    -H "Content-Type: application/json" \
    -d '{
        "data_view": {
            "title": "flink-metrics*",
            "name": "Flink Metrics",
            "timeFieldName": "@timestamp"
        }
    }' >/dev/null 2>&1 && echo -e "  ${GREEN}✓${NC} flink-metrics*" || echo -e "  ${DIM}↻ flink-metrics* (exists)${NC}"

curl -sf -X POST "http://localhost:5601/api/data_views/data_view" \
    -H "kbn-xsrf: true" \
    -H "Content-Type: application/json" \
    -d '{
        "data_view": {
            "title": "flink-logs*",
            "name": "Flink Logs",
            "timeFieldName": "@timestamp"
        }
    }' >/dev/null 2>&1 && echo -e "  ${GREEN}✓${NC} flink-logs*" || echo -e "  ${DIM}↻ flink-logs* (exists)${NC}"

# ── Step 6: ES index template ──
echo -e "\n${YELLOW}Step 6: Creating ES index template...${NC}"
curl -sf -X PUT "http://localhost:9200/_index_template/flink-metrics-template" \
    -H "Content-Type: application/json" \
    -d '{
        "index_patterns": ["flink-metrics*"],
        "template": {
            "mappings": {
                "properties": {
                    "@timestamp": { "type": "date" },
                    "resource.attributes.service.name": { "type": "keyword" },
                    "resource.attributes.job_name": { "type": "keyword" },
                    "resource.attributes.task_name": { "type": "keyword" },
                    "resource.attributes.operator_name": { "type": "keyword" },
                    "numRecordsInPerSecond": { "type": "float" },
                    "numRecordsOutPerSecond": { "type": "float" },
                    "numBytesInPerSecond": { "type": "float" },
                    "numBytesOutPerSecond": { "type": "float" },
                    "lastCheckpointDuration": { "type": "long" },
                    "lastCheckpointSize": { "type": "long" },
                    "numberOfCompletedCheckpoints": { "type": "long" },
                    "numberOfFailedCheckpoints": { "type": "long" },
                    "busyTimeMsPerSecond": { "type": "float" },
                    "isBackPressured": { "type": "boolean" }
                }
            },
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0
            }
        }
    }' >/dev/null 2>&1 && echo -e "  ${GREEN}✓${NC} Index template created" || echo -e "  ${DIM}↻ Index template (exists)${NC}"

# ── Verify ──
echo -e "\n${YELLOW}Verifying...${NC}"

echo -ne "  Elasticsearch:  "
curl -sf http://localhost:9200/_cluster/health >/dev/null 2>&1 \
    && echo -e "${GREEN}✓${NC} http://localhost:9200" \
    || echo -e "${RED}✗${NC}"

echo -ne "  Kibana:         "
curl -sf http://localhost:5601/api/status >/dev/null 2>&1 \
    && echo -e "${GREEN}✓${NC} http://localhost:5601" \
    || echo -e "${YELLOW}● starting...${NC}"

echo -ne "  OTEL Collector: "
docker ps --format '{{.Names}}' | grep -q "^qb-otel-collector$" \
    && echo -e "${GREEN}✓${NC} localhost:4317 (gRPC)" \
    || echo -e "${RED}✗${NC}"

echo -e "\n${GREEN}Done!${NC}"
echo ""
echo -e "  Kibana:      ${CYAN}http://localhost:5601${NC}"
echo -e "  OTEL:        ${CYAN}localhost:4317${NC} (gRPC)"
echo -e "  Flink metrics: OTEL scrapes Flink at :9249 → re-exposes at :8889"
echo -e "  Verify:      ${CYAN}curl http://localhost:8889/metrics${NC}"
echo ""
