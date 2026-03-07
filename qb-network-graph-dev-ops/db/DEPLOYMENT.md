# QB Network Graph — Step-by-Step Deployment Guide

Everything you need to go from 3 tar files to a running system.

## What You Have

```
db-liquibase.tar.gz                          (8K)   — MySQL schema (16 Liquibase changesets)
qb-network-graph-entity-agent.tar.gz         (65K)  — Entity Resolution Agent v1 (Python/FastAPI baseline)
qb-network-graph-classifier-orchestrator.tar.gz (74K) — Java classifier + db/ copy + agent-updates/ (v3 patch)
```

## What You'll End Up With

```
MySQL 8.0        — golden records, relationships, audit (source of truth)
Milvus 2.4       — multi-vector search (6 vectors per entity)
Agent v3         — Python/FastAPI on :8080 (MySQL + Milvus, no Redis)
Classifier       — Java batch/stream (reads Paimon, feeds agent)
```

## Prerequisites

| Tool | Version | Check |
|---|---|---|
| Docker + Docker Compose | v2+ | `docker compose version` |
| Python | 3.11+ | `python3 --version` |
| pip | latest | `pip --version` |
| JDK | 17+ | `java --version` |
| Maven | 3.8+ | `mvn --version` |
| Liquibase | 4.x | `liquibase --version` |
| MySQL Connector/J JAR | 8.3+ | Download from https://dev.mysql.com/downloads/connector/j/ |
| wget or curl | any | For downloading Milvus compose file |

---

## Step 1: Create Working Directory

```bash
mkdir -p ~/qb-network-graph
cd ~/qb-network-graph
```

---

## Step 2: Extract All 3 Tars

```bash
# Extract in order — tar 2 contains db/ and agent-updates/ alongside the classifier
tar xzf /path/to/db-liquibase.tar.gz
tar xzf /path/to/qb-network-graph-entity-agent.tar.gz
tar xzf /path/to/qb-network-graph-classifier-orchestrator.tar.gz

# Verify directory structure
ls -la
# Expected:
#   README.md                                  (root system overview)
#   db/                                        (Liquibase project)
#   qb-network-graph-entity-agent/             (Agent v1 baseline)
#   qb-network-graph-classifier-orchestrator/  (Java classifier)
#   agent-updates/                             (v3 patch files)
```

Verify key READMEs exist:

```bash
ls db/README.md agent-updates/README.md agent-updates/README-agent-v3.md \
   qb-network-graph-classifier-orchestrator/README.md \
   qb-network-graph-entity-agent/README.md README.md
# All 6 should be present
```

---

## Step 3: Start MySQL via Docker

```bash
# Create a docker-compose for MySQL (if you don't already have one running)
cat > docker-compose-mysql.yml << 'EOF'
version: '3.8'
services:
  mysql:
    container_name: qb-mysql
    image: mysql:8.0
    ports:
      - "3306:3306"
    environment:
      MYSQL_ROOT_PASSWORD: root
      MYSQL_DATABASE: quickbooks
      MYSQL_USER: qb_admin
      MYSQL_PASSWORD: qb_admin_pass
    volumes:
      - mysql_data:/var/lib/mysql
    command: >
      --character-set-encoding=utf8mb4
      --collation-server=utf8mb4_unicode_ci
      --default-authentication-plugin=mysql_native_password
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  mysql_data:
EOF

docker compose -f docker-compose-mysql.yml up -d

# Wait for MySQL to be ready
echo "Waiting for MySQL..."
until docker exec qb-mysql mysqladmin ping -h localhost --silent 2>/dev/null; do
  sleep 2
done
echo "MySQL is ready."
```

Verify:

```bash
docker exec qb-mysql mysql -u qb_admin -pqb_admin_pass -e "SELECT 1" quickbooks
# Should return "1"
```

---

## Step 4: Run Liquibase Migrations

```bash
cd ~/qb-network-graph/db/

# Edit liquibase.properties to match your setup (already has sensible defaults)
cat liquibase.properties
# Verify url, username, password match your MySQL

# Run all 16 changesets
# Replace /path/to/ with where your MySQL Connector/J JAR lives
liquibase \
  --classpath=/path/to/mysql-connector-j-8.3.0.jar \
  update

# If liquibase.properties doesn't have the classpath, pass it explicitly:
# liquibase \
#   --classpath=/path/to/mysql-connector-j-8.3.0.jar \
#   --url="jdbc:mysql://localhost:3306/quickbooks?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=UTC" \
#   --username=qb_admin \
#   --password=qb_admin_pass \
#   --changelog-file=changelog/db.changelog-master.yaml \
#   update
```

Verify all 16 changesets applied:

```bash
docker exec qb-mysql mysql -u qb_admin -pqb_admin_pass quickbooks \
  -e "SELECT id FROM DATABASECHANGELOG ORDER BY orderexecuted"
# Should show 0001 through 0016

# Verify golden record tables exist
docker exec qb-mysql mysql -u qb_admin -pqb_admin_pass quickbooks \
  -e "SHOW TABLES"
# Should include: golden_records, relationships, resolution_audit, pending_resolution

# Verify indexes on golden_records
docker exec qb-mysql mysql -u qb_admin -pqb_admin_pass quickbooks \
  -e "SHOW INDEX FROM golden_records"
# Should include: idx_gr_ein, idx_gr_naics_state, idx_gr_city_state,
#                 idx_gr_zip3, idx_gr_state, ft_gr_name (FULLTEXT)
```

---

## Step 5: Deploy Milvus via Docker Compose

Milvus standalone requires 3 containers: etcd (metadata), MinIO (object storage), and the Milvus server itself.

```bash
cd ~/qb-network-graph/

# Download the official Milvus standalone docker-compose
wget https://github.com/milvus-io/milvus/releases/download/v2.4.17/milvus-standalone-docker-compose.yml \
  -O docker-compose-milvus.yml

# Start Milvus (3 containers)
docker compose -f docker-compose-milvus.yml up -d

# Wait for Milvus to be healthy
echo "Waiting for Milvus..."
until docker exec milvus-standalone curl -sf http://localhost:9091/healthz 2>/dev/null; do
  sleep 3
done
echo "Milvus is ready."
```

Verify all 3 containers are running:

```bash
docker compose -f docker-compose-milvus.yml ps
# Expected:
#   milvus-etcd         Up   2379/tcp, 2380/tcp
#   milvus-minio        Up   9000/tcp, 9001/tcp
#   milvus-standalone   Up   0.0.0.0:19530->19530/tcp, 0.0.0.0:9091->9091/tcp
```

Verify Milvus is accepting connections:

```bash
# Quick Python check (after pymilvus is installed in Step 7)
python3 -c "
from pymilvus import connections, utility
connections.connect(host='localhost', port='19530')
print(f'Milvus server version: {utility.get_server_version()}')
connections.disconnect('default')
"
```

**Milvus WebUI** is available at http://localhost:9091/webui/ for browsing collections and monitoring.

### Milvus Ports

| Port | Service | Purpose |
|---|---|---|
| 19530 | Milvus gRPC | Agent connects here (pymilvus) |
| 9091 | Milvus HTTP | Health check + WebUI |
| 9000 | MinIO API | Object storage (internal) |
| 9001 | MinIO Console | MinIO web UI (optional) |
| 2379 | etcd | Metadata store (internal) |

### Milvus Data Persistence

Data is stored in `./volumes/milvus`, `./volumes/etcd`, `./volumes/minio` relative to where you ran docker compose. To wipe and restart fresh:

```bash
docker compose -f docker-compose-milvus.yml down
rm -rf volumes/
docker compose -f docker-compose-milvus.yml up -d
```

---

## Step 6: Apply Agent v3 Updates

This patches the v1 agent (Redis+Paimon) into v3 (MySQL+Milvus):

```bash
cd ~/qb-network-graph/qb-network-graph-entity-agent/

# 6a. Add new client files
cp ../agent-updates/clients/mysql_client.py   clients/
cp ../agent-updates/clients/milvus_client.py  clients/

# 6b. Replace existing files with v3 versions
cp ../agent-updates/config.py                 config.py
cp ../agent-updates/main.py                   main.py
cp ../agent-updates/orchestrator.py            orchestrator.py
cp ../agent-updates/mcp/candidate_evaluator.py mcp/
cp ../agent-updates/mcp/entity_writer.py       mcp/

# 6c. Remove obsolete Redis/Paimon client files
rm clients/redis_client.py
rm clients/paimon_client.py

# 6d. Replace README with v3 version
cp ../agent-updates/README-agent-v3.md         README.md
```

Verify no stale Redis/Paimon imports remain:

```bash
grep -rn "redis_client\|RedisClient\|paimon_client\|PaimonClient" \
  --include="*.py" . | grep -v "__pycache__" | grep -v "#"
# Should return NOTHING (zero lines)

grep -rn "mysql_client\|MySQLClient" --include="*.py" . | wc -l
# Should return 5+ (config, main, candidate_evaluator, entity_writer, mysql_client itself)
```

Verify file structure:

```bash
ls clients/
# Expected: __init__.py  embedding_client.py  graphdb_client.py
#           llm_client.py  milvus_client.py  mysql_client.py
# NOT expected: redis_client.py, paimon_client.py
```

---

## Step 7: Install Python Dependencies

```bash
cd ~/qb-network-graph/qb-network-graph-entity-agent/

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Update requirements.txt with v3 dependencies
cat > requirements.txt << 'EOF'
# Core
fastapi>=0.104.0
uvicorn>=0.24.0
pydantic>=2.5.0
pyyaml>=6.0
python-dotenv>=1.0.0

# Scoring
rapidfuzz>=3.5.0
numpy>=1.24.0

# HTTP client
httpx>=0.25.0

# MySQL (replaces redis + pypaimon)
mysql-connector-python>=8.3.0

# Milvus (vector search)
pymilvus>=2.4.0

# Embeddings
google-generativeai>=0.7.0
# sentence-transformers>=2.2.0  # Optional: local fallback if no Gemini key

# LLM
anthropic>=0.39.0

# Testing
pytest>=7.4.0
pytest-asyncio>=0.21.0

# Observability (OTEL)
opentelemetry-api>=1.20.0
opentelemetry-sdk>=1.20.0
opentelemetry-exporter-otlp-proto-grpc>=1.20.0
opentelemetry-instrumentation-fastapi>=0.41b0
opentelemetry-instrumentation-httpx>=0.41b0
EOF

# Install
pip install -r requirements.txt
```

Verify critical imports:

```bash
python3 -c "import mysql.connector; print(f'mysql-connector: {mysql.connector.__version__}')"
python3 -c "import pymilvus; print(f'pymilvus: {pymilvus.__version__}')"
python3 -c "import fastapi; print(f'fastapi: {fastapi.__version__}')"
```

---

## Step 8: Configure Agent Environment

```bash
cd ~/qb-network-graph/qb-network-graph-entity-agent/

cat > .env << 'EOF'
# ── Agent Service ───────────────────────────────────────────
AGENT_HOST=0.0.0.0
AGENT_PORT=8080

# ── MySQL (golden record source of truth) ──────────────────
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=qb_admin
MYSQL_PASSWORD=qb_admin_pass
MYSQL_DATABASE=quickbooks
MYSQL_POOL_SIZE=5

# ── Milvus (vector search) ─────────────────────────────────
MILVUS_HOST=localhost
MILVUS_PORT=19530

# ── Gemini Embeddings (for Milvus vectors + Step 3) ────────
GEMINI_API_KEY=your_gemini_api_key_here

# ── Anthropic LLM (for Step 4 — ambiguous cases) ──────────
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# ── Decision Thresholds ────────────────────────────────────
THRESHOLD_AUTO_MERGE=0.85
THRESHOLD_HUMAN_REVIEW=0.60

# ── Redis (DISABLED — Tier 2 optimization) ─────────────────
REDIS_ENABLED=false

# ── Knowledge Graph (OPTIONAL — skip if no GraphDB) ───────
# KG_SPARQL_ENDPOINT=http://localhost:7200/repositories/qb-ontology

# ── Observability (OPTIONAL) ───────────────────────────────
OTEL_ENABLED=false
EOF
```

Update `agent-config.yaml` to add MySQL and Milvus sections:

```bash
cat >> agent-config.yaml << 'EOF'

# v3 additions
mysql:
  host: localhost
  port: 3306
  user: qb_admin
  password: qb_admin_pass
  database: quickbooks
  pool_size: 5

milvus:
  host: localhost
  port: 19530

redis:
  enabled: false
EOF
```

**Important**: Replace `your_gemini_api_key_here` and `your_anthropic_api_key_here` with real API keys. Without them the agent still works but:
- No Gemini key → Milvus vectors will be zero-filled (search degrades), Step 3 (semantic similarity) uses local model or skips
- No Anthropic key → Step 4 (LLM reasoning) falls back to REVIEW decision for all ambiguous cases

---

## Step 9: Verify Agent Starts

```bash
cd ~/qb-network-graph/qb-network-graph-entity-agent/
source venv/bin/activate

python3 main.py
```

Expected startup output:

```
============================================================
Entity Resolution Agent Service READY
  MySQL:     connected
  Milvus:    connected
  GraphDB:   UNAVAILABLE
  Embedding: connected
  LLM:       connected
  OTEL:      disabled
  Thresholds: merge>0.85 review>0.6
  Golden records: 0
============================================================
INFO:     Uvicorn running on http://0.0.0.0:8080
```

If MySQL or Milvus show "MOCK (in-memory)" instead of "connected", check that the Docker containers are running and the .env credentials are correct.

Verify endpoints:

```bash
# In another terminal:
curl http://localhost:8080/health
# {"status":"healthy","service":"entity-resolution-agent","version":"3.0.0"}

curl http://localhost:8080/stats
# {"requests":0,"merges":0,"creates":0,"reviews":0,"errors":0,"uptime_seconds":...}
```

Stop the agent with Ctrl+C for now.

---

## Step 10: Run Tests

```bash
cd ~/qb-network-graph/qb-network-graph-entity-agent/
source venv/bin/activate

python3 -m pytest tests/ -v
```

Tests use in-memory mocks for all stores, so they pass without MySQL/Milvus running. This verifies the code wiring is correct after the v3 patch.

---

## Step 11: Send a Test Resolution Request

Start the agent in background:

```bash
cd ~/qb-network-graph/qb-network-graph-entity-agent/
source venv/bin/activate
python3 main.py &
AGENT_PID=$!
sleep 3
```

Send a test request:

```bash
curl -s -X POST http://localhost:8080/resolve \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "test-001",
    "record_id": "v-42",
    "record_type": "vendor",
    "company_id": 1,
    "chain_depth": 0,
    "classified_persona": {
      "identity": {
        "normalized_name": "BOBS PLUMBING",
        "name_first_token": "BOBS",
        "name_tokens": ["BOBS", "PLUMBING"],
        "legal_suffix": "LLC",
        "ein_clean": "743218976",
        "phone_digits": "5125550101",
        "email": "bob@bobsplumbing.com",
        "email_domain": "bobsplumbing.com"
      },
      "industry": {
        "naics_code": "423720",
        "naics_sector": "42",
        "naics_subsector": "423",
        "original_category": "Plumbing Supply",
        "commodity_keywords": ["pvc pipe", "copper fitting"]
      },
      "location": {
        "state": "TX",
        "city_norm": "AUSTIN",
        "zip3": "787",
        "zip5": "78745"
      },
      "commodity": {
        "top_keywords": ["pvc pipe", "copper fitting", "water heater"],
        "service_categories": ["Materials"]
      },
      "behavioral": {
        "volume_bracket": "MEDIUM",
        "avg_transaction": 1787.23,
        "transaction_count": 47
      },
      "sparsity": {
        "identity": 5,
        "industry": 4,
        "location": 4,
        "commodity": 3,
        "behavioral": 4
      }
    }
  }' | python3 -m json.tool
```

Expected response (first record — no existing golden records to match):

```json
{
  "event_id": "test-001",
  "decision": "NEW_ENTITY",
  "target_golden_record_id": "G-xxxxxxxx",
  "confidence": 0.0,
  "reasoning": "No candidates found in any bucket",
  ...
}
```

Verify it was written to MySQL:

```bash
docker exec qb-mysql mysql -u qb_admin -pqb_admin_pass quickbooks \
  -e "SELECT golden_record_id, canonical_name, state, naics_code, confidence, status FROM golden_records"
# Should show 1 row: G-xxxxxxxx | BOBS PLUMBING | TX | 423720 | 0.5 | ACTIVE
```

Verify it was written to Milvus:

```bash
python3 -c "
from pymilvus import connections, Collection
connections.connect(host='localhost', port='19530')
col = Collection('golden_records')
col.load()
print(f'Milvus entity count: {col.num_entities}')
connections.disconnect('default')
"
# Should print: Milvus entity count: 1
```

Send the same record again — should MERGE this time:

```bash
curl -s -X POST http://localhost:8080/resolve \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "test-002",
    "record_id": "v-43",
    "record_type": "vendor",
    "company_id": 2,
    "chain_depth": 0,
    "classified_persona": {
      "identity": {
        "normalized_name": "BOBS PLUMBING",
        "ein_clean": "743218976"
      },
      "industry": { "naics_code": "423720", "naics_sector": "42" },
      "location": { "state": "TX", "city_norm": "AUSTIN" },
      "commodity": { "top_keywords": ["pvc pipe"] },
      "behavioral": { "volume_bracket": "MEDIUM" }
    }
  }' | python3 -m json.tool
```

Expected: `"decision": "MERGE"` with `"target_golden_record_id"` matching the first record's ID. The EIN exact match triggers a deterministic merge at Step 2.

Verify merge in MySQL:

```bash
docker exec qb-mysql mysql -u qb_admin -pqb_admin_pass quickbooks \
  -e "SELECT golden_record_id, source_count, confidence FROM golden_records WHERE status='ACTIVE'"
# source_count should now be 2, confidence > 0.5

docker exec qb-mysql mysql -u qb_admin -pqb_admin_pass quickbooks \
  -e "SELECT audit_id, decision, target_golden_id, confidence FROM resolution_audit"
# Should show 2 rows: NEW_ENTITY and MERGE
```

Stop the agent:

```bash
kill $AGENT_PID
```

---

## Step 12: Build the Classifier Orchestrator

```bash
cd ~/qb-network-graph/qb-network-graph-classifier-orchestrator/

# Build with Maven
mvn clean package -DskipTests

# Or use the run script
chmod +x run.sh
./run.sh --build
```

The classifier reads from Paimon `entity_connections` and POSTs to the agent. It requires a Paimon warehouse with data. For standalone testing without Paimon:

```bash
# Classify-only mode outputs JSON files (no agent or Paimon needed)
./run.sh --classify-only

# With the agent running, batch mode will POST classified personas:
# ./run.sh
```

See `qb-network-graph-classifier-orchestrator/README.md` for all modes and configuration.

---

## Step 13: Full Stack Verification

With everything running, verify the complete stack:

```bash
# 1. Check MySQL
docker exec qb-mysql mysqladmin ping -h localhost --silent && echo "MySQL: OK"

# 2. Check Milvus
curl -sf http://localhost:9091/healthz && echo "Milvus: OK"

# 3. Start agent
cd ~/qb-network-graph/qb-network-graph-entity-agent/
source venv/bin/activate
python3 main.py &
sleep 3

# 4. Check agent
curl -sf http://localhost:8080/health && echo "Agent: OK"

# 5. Check stats
curl -s http://localhost:8080/stats | python3 -m json.tool
```

---

## Port Summary

| Port | Service | Required? |
|---|---|---|
| 3306 | MySQL | Yes |
| 19530 | Milvus gRPC | Yes |
| 9091 | Milvus HTTP/WebUI | Monitoring only |
| 9000 | MinIO (Milvus storage) | Internal |
| 9001 | MinIO Console | Optional |
| 2379 | etcd (Milvus metadata) | Internal |
| 8080 | Entity Resolution Agent | Yes |
| 7200 | GraphDB (optional) | No — KG writes skip if unavailable |

---

## Docker Management

### Start everything

```bash
cd ~/qb-network-graph/
docker compose -f docker-compose-mysql.yml up -d
docker compose -f docker-compose-milvus.yml up -d
```

### Stop everything

```bash
docker compose -f docker-compose-milvus.yml down
docker compose -f docker-compose-mysql.yml down
```

### Nuke and restart (deletes all data)

```bash
docker compose -f docker-compose-milvus.yml down -v
docker compose -f docker-compose-mysql.yml down -v
rm -rf volumes/
# Then re-run Steps 3-5
```

---

## Troubleshooting

### MySQL: "Access denied for user"

```bash
# Check credentials
docker exec qb-mysql mysql -u qb_admin -pqb_admin_pass -e "SELECT 1"
# If this fails, recreate the user:
docker exec qb-mysql mysql -u root -proot -e "
  DROP USER IF EXISTS 'qb_admin'@'%';
  CREATE USER 'qb_admin'@'%' IDENTIFIED BY 'qb_admin_pass';
  GRANT ALL PRIVILEGES ON quickbooks.* TO 'qb_admin'@'%';
  FLUSH PRIVILEGES;
"
```

### Milvus: "connection refused on 19530"

```bash
# Check if all 3 Milvus containers are running
docker compose -f docker-compose-milvus.yml ps
# If milvus-standalone is restarting, check logs:
docker logs milvus-standalone --tail 50
# Common issue on Mac: needs 8GB+ RAM allocated to Docker
```

### Agent: "MySQL: MOCK (in-memory)"

```bash
# mysql-connector-python not installed
pip install mysql-connector-python
# Or check .env has correct MYSQL_HOST/PORT/USER/PASSWORD
```

### Agent: "Milvus: MOCK (in-memory)"

```bash
# pymilvus not installed
pip install pymilvus
# Or Milvus isn't running — check docker compose -f docker-compose-milvus.yml ps
```

### Liquibase: "Could not find driver"

```bash
# Need the MySQL JDBC driver JAR on classpath
# Download from https://dev.mysql.com/downloads/connector/j/
# Then pass: --classpath=/path/to/mysql-connector-j-8.3.0.jar
```

### Agent: "Gemini embedding failed"

```bash
# Check GEMINI_API_KEY in .env
# Without it: vectors are zero-filled (search won't work well)
# Agent still functions — just Milvus search quality degrades
```

---

## File Map After Setup

```
~/qb-network-graph/
├── README.md                                     (system overview)
├── docker-compose-mysql.yml                       (Step 3)
├── docker-compose-milvus.yml                      (Step 5 — downloaded)
├── volumes/                                       (Milvus data — auto-created)
│
├── db/                                            (Liquibase — Step 4)
│   ├── README.md
│   ├── liquibase.properties
│   └── changelog/
│       ├── db.changelog-master.yaml
│       └── versions/
│           ├── 0001-create-companies.yaml
│           ├── ... (16 changesets)
│           └── 0016-grant-cdc-golden-records.yaml
│
├── qb-network-graph-entity-agent/                 (Agent v3 — Steps 6-11)
│   ├── README.md                                  (v3 docs)
│   ├── .env                                       (Step 8)
│   ├── agent-config.yaml                          (Step 8)
│   ├── requirements.txt                           (Step 7)
│   ├── venv/                                      (Step 7)
│   ├── main.py                                    (v3 — from agent-updates/)
│   ├── config.py                                  (v3)
│   ├── orchestrator.py                            (v3)
│   ├── clients/
│   │   ├── mysql_client.py                        (NEW — from agent-updates/)
│   │   ├── milvus_client.py                       (NEW — from agent-updates/)
│   │   ├── embedding_client.py                    (unchanged)
│   │   ├── graphdb_client.py                      (unchanged)
│   │   └── llm_client.py                          (unchanged)
│   ├── mcp/
│   │   ├── candidate_evaluator.py                 (v3)
│   │   ├── entity_writer.py                       (v3)
│   │   └── knowledge_graph.py                     (unchanged)
│   ├── models/                                    (unchanged)
│   ├── utils/                                     (unchanged)
│   ├── tests/                                     (unchanged)
│   └── observability/                             (unchanged)
│
├── qb-network-graph-classifier-orchestrator/      (Java — Step 12)
│   ├── README.md
│   ├── .env
│   ├── pom.xml
│   ├── run.sh
│   └── src/
│
└── agent-updates/                                 (migration patch — consumed in Step 6)
    ├── README.md                                  (migration guide)
    └── README-agent-v3.md                         (agent v3 docs)
```
