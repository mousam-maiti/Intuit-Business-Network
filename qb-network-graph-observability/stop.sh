#!/bin/bash
# ============================================================
# QB Observability Stack — Stop
# ============================================================

GREEN='\033[0;32m'
DIM='\033[2m'
NC='\033[0m'

echo "Stopping observability stack..."

docker stop qb-otel-collector qb-kibana qb-elasticsearch 2>/dev/null
docker rm qb-otel-collector qb-kibana qb-elasticsearch 2>/dev/null

echo -e "${GREEN}✓ Stopped.${NC}"
echo -e "${DIM}  ES data persists in volume 'qb_es_data'.${NC}"
echo -e "${DIM}  To wipe: docker volume rm qb_es_data${NC}"
echo -e "${DIM}  To remove network: docker network rm qb-observability${NC}"
