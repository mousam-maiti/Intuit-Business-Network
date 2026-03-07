# QB Network Graph

A full-stack business network intelligence platform that maps vendor-client relationships across QuickBooks businesses. The system ingests transactional data, resolves duplicate entities using AI, builds a knowledge graph, and provides an interactive UI with conversational AI for exploring business networks.

## Table of Contents

- [Introduction](#introduction)
- [Functional Specifications](#functional-specifications)
- [Screenshots](#screenshots)
- [Architecture](#architecture)
- [Services](#services)
- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the Platform](#running-the-platform)
- [Port Map](#port-map)
- [Data Pipeline](#data-pipeline)

---

## Introduction

QB Network Graph solves the problem of understanding business relationships at scale. Given a QuickBooks ecosystem of ~1 million businesses with up to 100 direct relationships each, the platform:

1. **Ingests** vendor, customer, invoice, bill, and payment data from MySQL via CDC streaming
2. **Classifies** each business connection through a 5-stage classifier pipeline (name, industry, commodity, location, behavioral)
3. **Resolves** duplicate entities using an escalating AI strategy: deterministic matching, embedding similarity, then LLM reasoning
4. **Stores** golden records in Neo4j (graph queries), MySQL (ACID transactions), and Paimon (warehouse analytics)
5. **Visualizes** the network in an interactive graph UI with search, lineage tracking, match review, and AI-powered chat

## Functional Specifications

### Core Use Cases

| Use Case | Description |
|----------|-------------|
| **View business network** | Interactive force-directed graph showing vendors (orange) and customers (blue) with hop-colored depth. Drag-to-pan, click to inspect entities |
| **Search relationships** | Global search with Redis-cached results. Find any business and understand direct/indirect relationships across the network |
| **Grow the network** | Add new vendor/client connections. The system resolves whether the business already exists under a different name or descriptor |
| **Entity resolution** | AI-powered deduplication: deterministic rules, vector embeddings (Gemini), and LLM reasoning merge duplicate records with full audit trails |
| **Match review** | Human-in-the-loop review queue for uncertain entity matches. Approve/reject with reasoning, triggering graph updates |
| **Connection lineage** | Time-travel through entity history: view audit trails, before/after snapshots, and Paimon pipeline provenance |
| **AI assistant** | Conversational interface (Intuit Assist) powered by Gemini 2.5 with 15 MCP tools for querying the network, traversing supply chains, detecting clusters, and assessing risk |
| **Infrastructure monitoring** | Grafana-themed dashboard showing real-time metrics for Redis, Neo4j, Paimon, Elasticsearch, Kibana, and OTEL Collector |

### AI Chat Capabilities

The conversational agent supports natural language queries with chart rendering:

- "Show me Acme Corp's vendor network" &mdash; graph visualization
- "What industries are most common in my network?" &mdash; pie chart
- "Trace the supply chain from Dell Technologies" &mdash; supply chain traversal
- "Find the shortest path between two companies" &mdash; path analysis
- "Detect clusters in my network" &mdash; community detection
- "Assess risk if Sysco goes offline" &mdash; downstream impact analysis

## Screenshots

### Business Network Graph
Interactive force-directed graph showing all vendors (orange) and customers (blue) with hop-colored depth rings around the central company entity.

![Business Network Graph](UI_Screenshots/Screenshot%202026-03-07%20at%203.20.23%20PM.png)

### Supply Chain Traversal
Trace upstream/downstream supply chains with path highlighting. The right panel shows the selected entity's profile, match score, and transaction volume.

![Supply Chain Traversal](UI_Screenshots/Screenshot%202026-03-07%20at%203.21.06%20PM.png)

### Shortest Path Finder
Find the shortest path between any two entities in the network, with the path highlighted on the graph and hop count displayed.

![Shortest Path](UI_Screenshots/Screenshot%202026-03-07%20at%203.21.58%20PM.png)

### Global Search
Search across the entire Intuit Business Network with faceted filters (network membership, industry). Results show match relevance scores and "Add to Network" actions for external entities.

![Global Search](UI_Screenshots/Screenshot%202026-03-07%20at%203.22.55%20PM.png)

### Add to Network
Add an entity from search results to your network as a vendor or client. The system resolves whether the business already exists under a different name.

![Add to Network](UI_Screenshots/Screenshot%202026-03-07%20at%203.23.13%20PM.png)

### Expanded Network View
The full network graph after growing connections, showing the dense web of vendor-client relationships across the QuickBooks ecosystem.

![Expanded Network](UI_Screenshots/Screenshot%202026-03-07%20at%203.23.40%20PM.png)

### Match Review Queue
Human-in-the-loop review for uncertain entity matches. Shows AI confidence, 5-dimension classifier scores, candidate golden records with similarity bars, and merge actions.

![Match Review](UI_Screenshots/Screenshot%202026-03-07%20at%203.24.04%20PM.png)

### Connection Lineage & Time Travel
Audit trail for any golden record entity: timeline of merge/create/review events, decision reasoning, trigger tags, and point-in-time state reconstruction.

![Connection Lineage](UI_Screenshots/Screenshot%202026-03-07%20at%203.24.29%20PM.png)

### Intuit Assist &mdash; AI Chat
Conversational AI powered by Gemini 2.5 with ReAct reasoning. Supports risk analysis, volume assessment, and auto-generated charts. Session history on the left.

![AI Chat](UI_Screenshots/Screenshot%202026-03-07%20at%203.24.52%20PM.png)

### Infrastructure Monitor (Service Health & Key Metrics)
Grafana-themed dashboard showing real-time service health, key entity/relationship/audit metrics, Redis cache stats, and Neo4j graph statistics.

![Infra Monitor Top](UI_Screenshots/Screenshot%202026-03-07%20at%203.25.52%20PM.png)

### Infrastructure Monitor (Data Stores & Observability)
Continued view showing Paimon warehouse table counts, Elasticsearch indices, and OTEL Collector pipeline throughput.

![Infra Monitor Bottom](UI_Screenshots/Screenshot%202026-03-07%20at%203.25.59%20PM.png)

### Native Merge with AI Analysis
Merge two entities from the native perspective. Intuit Assist runs a multi-tool analysis (entity profile, graph overlap, field similarity, merge risk) before confirming.

![Native Merge](UI_Screenshots/Screenshot%202026-03-07%20at%203.37.25%20PM.png)

### Add Connection Form
Add a new vendor or client connection with identity, industry, commodity, and location fields. Writes to MySQL and triggers the CDC &rarr; classification &rarr; resolution pipeline.

![Add Connection](UI_Screenshots/Screenshot%202026-03-07%20at%203.48.27%20PM.png)

---

## Architecture

```
                          +------------------+
                          |    React UI      |
                          |   (Vite :8080)   |
                          +--------+---------+
                                   |
                    +--------------+--------------+
                    |                             |
           +-------v--------+          +---------v---------+
           | Backend API    |          | Conv Agent        |
           | (FastAPI :8087)|          | (FastAPI :8082)   |
           +-------+--------+          +---------+---------+
                   |                             |
        +----------+----------+         +--------v--------+
        |          |          |         | MCP Server      |
   +----v---+ +---v----+ +---v----+    | (FastMCP :8083) |
   | Neo4j  | | Redis  | | Paimon |    +--------+--------+
   | :7687  | | :6379  | | (fs)   |             |
   +--------+ +--------+ +--------+    +--------v--------+
                                        | Entity Agent    |
   +-------------+                      | (FastAPI :8085) |
   | MySQL :3306 |                      +--------+--------+
   +------+------+                               |
          |                              +-------+-------+
   +------v------+                  +----v--+ +--v---+
   | Flink CDC   |                  | Neo4j | |MySQL |
   | (9 jobs)    |                  +-------+ +------+
   +------+------+
   +------v---------+
   | Paimon Bronze   |
   | (staged tables) |
   +------+----------+
          |
   +------v-----------+     +---------------------+
   | Stream Aggregator |     | OTEL Collector      |
   | (2 Flink jobs)    |     | :4317 -> ES -> Kibana|
   +------+------------+     +---------------------+
          |
   +------v-----------+
   | Paimon Silver     |
   | (entity_connections)|
   +------+------------+
          |
   +------v------------------+
   | Classifier Orchestrator  |
   | (Java, 5-stage pipeline) |
   +------+-------------------+
          |
          v
   Entity Agent (resolve/merge)
```

## Services

### qb-network-graph-ui
React 18 + Vite frontend with Tailwind CSS, Recharts, and Lucide icons. Features sidebar navigation, force-directed network graph, global search, match review queue, connection lineage viewer, full-page AI chat, and Grafana-themed infra monitor.

### qb-network-graph-be
FastAPI backend serving 21 REST endpoints across entities, relationships, search, matching, connections, alerts, lineage, and infrastructure metrics. Queries Neo4j, MySQL, Paimon, and Redis.

### qb-network-graph-conv-agent
Conversational AI agent using Gemini 2.5 with a ReAct reasoning loop. Supports WebSocket bidirectional chat, session persistence to MySQL, and 15 MCP tool integrations for network queries, analytics, and chart generation.

### qb-network-graph-entity-agent
Entity resolution service with escalating comparison strategy: deterministic field matching, Gemini embedding similarity, then LLM-based reasoning. Writes golden records to MySQL and Neo4j with full audit trails.

### qb-network-graph-mcp-servers
Model Context Protocol server exposing 19 tools across candidate evaluation, knowledge graph queries, entity writing, and search/analytics. Also runs a sync HTTP API for Neo4j graph pushes.

### qb-network-graph-classifier-orchestrator
Java streaming application that reads `entity_connections` from Paimon, classifies each row through 5 classifiers (name, industry, commodity, location, behavioral), and POSTs classified personas to the Entity Agent.

### qb-network-graph-stream-aggregator
Flink SQL jobs (2 aggregators) that transform Paimon bronze staged tables into a silver `entity_connections` table using partial-update and aggregation merge engines.

### qb-network-graph-cdc
Flink CDC setup with 9 streaming jobs that capture MySQL changes (companies, vendors, customers, invoices, bills, payments, line items, match decisions) into Paimon bronze tables.

### qb-network-graph-observability
OpenTelemetry infrastructure: collector config (OTLP gRPC :4317), Elasticsearch exporter, Kibana dashboards, and Prometheus scrape targets for Flink metrics.

### qb-network-graph-ontology
RDF/Turtle business ontology with NAICS/UNSPSC taxonomy (682 triples) hosted in GraphDB Free. Provides SPARQL endpoint for industry classification and shared context inference.

### qb-seed-generator
Python data generator using Faker to create realistic QuickBooks seed data (companies, vendors, customers, invoices, bills, payments) and populate MySQL and Neo4j.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | React 18, Vite 5, Tailwind CSS 3, Recharts, Lucide, React Router 6 |
| **Backend API** | Python, FastAPI, Uvicorn |
| **AI/LLM** | Google Gemini 2.5 (chat + embeddings) |
| **Agent Protocol** | Model Context Protocol (MCP) via FastMCP |
| **Graph Database** | Neo4j 5 |
| **Relational DB** | MySQL 8.0 |
| **Data Warehouse** | Apache Paimon (filesystem catalog) |
| **Stream Processing** | Apache Flink 1.18 (CDC + aggregation) |
| **Caching** | Redis |
| **Ontology** | GraphDB Free (RDF/SPARQL) |
| **Observability** | OpenTelemetry, Elasticsearch, Kibana, Prometheus |
| **Classifier** | Java 17, Maven (Paimon reader + REST client) |
| **DB Migrations** | Liquibase (YAML changelogs) |
| **Containerization** | Docker, Docker Compose |

## Prerequisites

- **Docker & Docker Compose** (for MySQL, Neo4j, Redis, Elasticsearch, Kibana, GraphDB)
- **Python 3.9+** (for backend, conv agent, entity agent, MCP server, seed generator)
- **Node.js 18+** and **npm** (for UI)
- **Java 17+** and **Maven 3.8+** (for classifier orchestrator)
- **Apache Flink 1.18** (native install for CDC and stream aggregation)
- **Google Gemini API key** (for AI features)

## Installation

### 1. Clone the repository

```bash
git clone git@github.com:mousam-maiti/Intuit-Business-Network.git
cd Intuit-Business-Network
```

### 2. Start infrastructure services

```bash
cd qb-network-graph-dev-ops
docker compose up -d
```

This starts MySQL (:3306), Neo4j (:7687), Redis (:6379), Elasticsearch (:9200), Kibana (:5601), and GraphDB (:7200).

### 3. Run database migrations

```bash
# Liquibase migrations are managed in qb-network-graph-dev-ops/db/changelog/
# They run automatically via the demo script, or manually:
docker exec qb-mysql mysql -u qb_admin -pqb_admin_pass quickbooks < schema.sql
```

### 4. Install Flink CDC

```bash
cd qb-network-graph-cdc
./setup.sh
```

This installs Flink 1.18 locally, configures the Paimon filesystem catalog, and generates CDC job SQL files.

### 5. Install Python services

Each Python service has its own virtual environment:

```bash
# Backend API
cd qb-network-graph-be
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Conversational Agent
cd qb-network-graph-conv-agent
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Entity Agent
cd qb-network-graph-entity-agent
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# MCP Server
cd qb-network-graph-mcp-servers
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Seed Generator
cd qb-seed-generator
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### 6. Build the classifier orchestrator

```bash
cd qb-network-graph-classifier-orchestrator
mvn clean package
```

### 7. Install the UI

```bash
cd qb-network-graph-ui
npm install
```

### 8. Set up observability

```bash
cd qb-network-graph-observability
./setup.sh
```

## Configuration

Each service reads from its own config file. Copy the example env files and fill in your values:

| Service | Config File | Key Settings |
|---------|-------------|--------------|
| UI | `.env` | `VITE_PORT`, `VITE_API_URL`, `VITE_WS_URL`, `VITE_USE_MOCKS` |
| Backend | `be-config.yaml` | Neo4j, MySQL, Redis, Paimon connection details |
| Conv Agent | `agent-config.yaml` | Gemini API key, MCP server URL, MySQL for sessions |
| Entity Agent | `agent-config.yaml` | Gemini API key, MySQL, Neo4j endpoints |
| MCP Server | `server-config.yaml` | Neo4j, Redis, MySQL, GraphDB, Gemini API key |
| CDC | `.env` | `FLINK_HOME`, MySQL source connection |
| Stream Aggregator | `.env` | Flink REST URL, Paimon warehouse path |
| Seed Generator | `.env` | MySQL connection, MCP sync API URL |

**Required API key**: Set `GEMINI_API_KEY` in the conv agent, entity agent, and MCP server configs.

## Running the Platform

### Quick start (demo mode)

The `demo.sh` script at the repo root handles the full lifecycle:

```bash
./demo.sh
```

This will:
1. Verify Docker services are running
2. Clear and reset all data stores (Paimon, Neo4j, Redis, MySQL tables)
3. Run Liquibase migrations and seed QuickBooks data
4. Start Flink cluster and submit 9 CDC + 2 aggregator jobs
5. Wait for CDC snapshot completion
6. Start all services in order: MCP Server, Entity Agent, Backend API, UI, Conv Agent, Classifier

### Manual start (individual services)

```bash
# 1. MCP Server + Sync API
cd qb-network-graph-mcp-servers
python server.py                    # :8083 (MCP) + :8084 (Sync API)

# 2. Entity Agent
cd qb-network-graph-entity-agent
python main.py                      # :8085

# 3. Backend API
cd qb-network-graph-be
python main.py                      # :8087

# 4. UI
cd qb-network-graph-ui
npm run dev                         # :8080

# 5. Conversational Agent
cd qb-network-graph-conv-agent
python main.py                      # :8082

# 6. Classifier Orchestrator
cd qb-network-graph-classifier-orchestrator
java -jar target/classifier-orchestrator.jar --mode stream
```

### Seed data

```bash
cd qb-seed-generator
python src/main.py generate         # Generate seed files to seed/
python src/main.py seed             # Load into MySQL
python src/main.py network          # Build global network in Neo4j
python src/main.py connections      # Create vendor/customer links
```

## Port Map

| Port | Service |
|------|---------|
| 3306 | MySQL |
| 5601 | Kibana |
| 6379 | Redis |
| 7200 | GraphDB (SPARQL) |
| 7474 | Neo4j Browser |
| 7687 | Neo4j Bolt |
| 8080 | UI (Vite dev server) |
| 8081 | Flink REST API |
| 8082 | Conversational Agent |
| 8083 | MCP Server |
| 8084 | MCP Sync API |
| 8085 | Entity Resolution Agent |
| 8087 | Backend REST API |
| 8889 | OTEL Collector (Prometheus) |
| 9200 | Elasticsearch |

## Data Pipeline

```
MySQL (source tables)
    |
    v
Flink CDC (9 jobs) ──> Paimon Bronze (staged_vendors, staged_customers, ...)
    |
    v
Stream Aggregator (2 Flink jobs) ──> Paimon Silver (entity_connections)
    |
    v
Classifier Orchestrator (5-stage: name, industry, commodity, location, behavioral)
    |
    v
Entity Agent (escalating resolution: deterministic -> embeddings -> LLM)
    |
    +──> MySQL (golden_records, resolution_audit)
    +──> Neo4j (Entity nodes, BUYS_FROM/SELLS_TO relationships)
    +──> Paimon Gold (golden_records, pending_resolution, resolution_audit)
```

### Entity Resolution Strategy

1. **Find candidates** &mdash; fuzzy name matching via RapidFuzz against existing golden records
2. **Compare fields** &mdash; deterministic field-by-field comparison (name, address, industry)
3. **Embedding similarity** &mdash; Gemini embedding cosine similarity for semantic matching
4. **LLM reasoning** &mdash; Gemini evaluates ambiguous cases with structured reasoning
5. **Decision** &mdash; AUTO_MERGE, AUTO_CREATE, or escalate to PENDING human review

### Audit & Provenance

- **Entity audit trail**: Before/after JSON snapshots per mutation in Paimon `entity_audit_trail`
- **Resolution audit**: Decision reasoning, confidence scores, and reviewer attribution
- **Pipeline lineage**: Paimon PIP-5 source/sink lineage tracking across Flink jobs
- **Time travel**: Paimon daily auto-tags (365 retained) for point-in-time reconstruction
