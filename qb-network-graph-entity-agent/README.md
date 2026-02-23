# QB Network Graph — Entity Resolution Agent (v3)

Resolves orphan business records (vendors/customers from QuickBooks CDC) against
a golden record corpus using escalating comparison: **deterministic → embedding → LLM**.

v3: MySQL source of truth + Milvus vector search. Redis and Paimon removed from agent.

## Architecture

```
                    ┌─────────────────────────────────────────────┐
  Classifier        │          Entity Resolution Agent            │
  Orchestrator      │                                             │
  (ClassifiedPersona)│  POST /resolve                             │
        ──────▶     │    │                                        │
                    │    ▼                                        │
                    │  Orchestrator (escalation strategy)         │
                    │    │                                        │
                    │    ├─ Step 1: find_candidates    ─── MySQL  │
                    │    ├─ Step 2: compare_fields     ─── Pure   │
                    │    ├─ Step 3: semantic_similarity ─── Gemini │
                    │    └─ Step 4: llm_reasoning      ─── Claude │
                    │    │                                        │
                    │    ▼                                        │
                    │  MERGE | NEW_ENTITY | REVIEW                │
                    │    │                                        │
                    │    ├─ MySQL  (golden records, audit, rels)  │
                    │    ├─ Milvus (vector search embeddings)     │
                    │    ├─ GraphDB (KG triples, ontology)        │
                    │    └─ OTEL   (traces + metrics)             │
                    └─────────────────────────────────────────────┘
```

## 3 MCP Tool Servers

| Server | Tools | Store |
|---|---|---|
| **candidate_evaluator** | `find_candidates`, `compare_fields`, `semantic_similarity` | MySQL (indexed queries), Gemini (embeddings) |
| **knowledge_graph** | `query_ontology`, `check_shared_context`, `write_entity_triples`, `write_merge_redirect` | GraphDB SPARQL |
| **entity_writer** | `merge_into_golden_record`, `create_golden_record`, `submit_for_review`, `merge_golden_records`, `log_decision` | MySQL, Milvus, KG |

## Quickstart

### Prerequisites

- **Python 3.11+**
- **MySQL 8.0+** with the schema applied (see `db/` Liquibase project)
- **Milvus 2.4+** (optional — gracefully degrades)
- API keys: `ANTHROPIC_API_KEY` (Claude LLM), `GEMINI_API_KEY` (embeddings)

### Setup

```bash
# 1. Clone and enter project
cd qb-network-graph-entity-agent/

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your MySQL credentials, API keys, etc.

# 5. Apply database migrations (if not done)
cd ../db/
liquibase --classpath=/path/to/mysql-connector-j-8.3.0.jar update
cd ../qb-network-graph-entity-agent/

# 6. Run tests
python -m pytest tests/ -v

# 7. Start the agent
python main.py
# → http://localhost:8080/docs for Swagger UI
```

### Interactive Menu (run-agent.sh)

```bash
chmod +x setup.sh run-agent.sh
./setup.sh       # creates .env, venv, deps, validates, runs tests
./run-agent.sh   # interactive menu
```

```
  Agent
  1  Start agent                    POST /resolve on :8080
  2  Stop agent
  3  View agent logs                (tail -f)

  Test
  4  Run test suite                 42 tests
  5  Send test resolve request      (creates or matches)
  6  Send batch test requests       (5 diverse businesses)

  Monitor
  7  Show agent stats               GET /stats
  8  Show golden records            (MySQL query)
  9  Show audit log                 (resolution decisions)

  Observability
  o  Start OTEL stack               ES + Kibana + Collector
  k  Open Kibana                    http://localhost:5601
  d  Setup Kibana dashboards
  p  Show Prometheus metrics        curl :8889/metrics
```

## Configuration

All config is externalized via `.env` (env vars always win over YAML):

```bash
# Priority: env vars > .env > agent-config.yaml > defaults
```

### Core Environment Variables

| Category | Env Var | Default | Notes |
|---|---|---|---|
| **MySQL** | `MYSQL_HOST` | `localhost` | Golden record source of truth |
| | `MYSQL_PORT` | `3306` | |
| | `MYSQL_USER` | `qb_admin` | |
| | `MYSQL_PASSWORD` | `qb_admin_pass` | |
| | `MYSQL_DATABASE` | `quickbooks` | |
| | `MYSQL_POOL_SIZE` | `5` | Connection pool |
| **Milvus** | `MILVUS_HOST` | `localhost` | Vector search (optional) |
| | `MILVUS_PORT` | `19530` | |
| **Thresholds** | `THRESHOLD_AUTO_MERGE` | `0.85` | Above this → auto merge |
| | `THRESHOLD_HUMAN_REVIEW` | `0.60` | Above this → human review |
| **Weights** | `WEIGHT_IDENTITY` | `0.35` | Persona dimension weights |
| | `WEIGHT_INDUSTRY` | `0.25` | |
| | `WEIGHT_LOCATION` | `0.15` | |
| | `WEIGHT_COMMODITY` | `0.15` | |
| | `WEIGHT_BEHAVIORAL` | `0.10` | |
| **LLM** | `ANTHROPIC_API_KEY` | — | Required for Step 4 |
| | `LLM_MODEL` | `claude-sonnet-4-20250514` | |
| **Embedding** | `GEMINI_API_KEY` | — | For Milvus vectors + Step 3 |
| | `EMBEDDING_MODEL` | `text-embedding-004` | |
| **GraphDB** | `KG_SPARQL_ENDPOINT` | `http://localhost:7200/repos/qb-ontology` | Optional |
| **OTEL** | `OTEL_ENABLED` | `true` | Traces + metrics |
| | `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` | |
| **Redis** | `REDIS_ENABLED` | `false` | Tier 2 — disabled by default |

See `.env.example` for the full list of 45+ configurable values.

All external services degrade gracefully — no MySQL driver → mock, no Milvus → mock, no LLM → REVIEW, no OTEL → disabled.

## Endpoints

### POST /resolve

Main resolution endpoint. Accepts a `ClassifiedPersona` and returns a decision.

```bash
curl -X POST http://localhost:8080/resolve \
  -H "Content-Type: application/json" \
  -d '{
    "event_id": "evt-1-42",
    "record_id": "v-42",
    "record_type": "vendor",
    "company_id": 1,
    "chain_depth": 0,
    "classified_persona": {
      "identity": {
        "normalized_name": "BOBS PLUMBING",
        "legal_suffix": "LLC",
        "ein_clean": "743218976",
        "phone_digits": "5125550101",
        "email": "bob@bobsplumbing.com"
      },
      "industry": {
        "naics_code": "423720",
        "naics_sector": "42",
        "commodity_keywords": ["pvc pipe", "copper fitting"]
      },
      "location": {
        "state": "TX",
        "city_norm": "AUSTIN",
        "zip3": "787",
        "zip5": "78745"
      },
      "commodity": {
        "top_keywords": ["pvc pipe", "copper fitting"],
        "service_categories": ["Materials"]
      },
      "behavioral": {
        "volume_bracket": "MEDIUM",
        "avg_transaction": 1787.23,
        "transaction_count": 47
      }
    }
  }'
```

Response:
```json
{
  "event_id": "evt-1-42",
  "decision": "MERGE",
  "target_golden_record_id": "G-a1b2c3d4",
  "confidence": 0.92,
  "dimension_scores": {
    "identity": 0.95,
    "industry": 0.88,
    "location": 1.0,
    "commodity": 0.75,
    "behavioral": 0.60
  },
  "reasoning": "Merged into BOBS PLUMBING LLC (DETERMINISTIC)",
  "key_factors": ["strong_identity_match", "EIN_exact", "same_location"],
  "evaluation_chain": [...],
  "agent_metadata": {
    "total_duration_ms": 45,
    "llm_calls": 0,
    "embedding_calls": 0,
    "candidates_evaluated": 3
  }
}
```

### POST /re-evaluate

Re-evaluates a golden record after enrichment adds new bucket keys.

```bash
curl -X POST http://localhost:8080/re-evaluate \
  -H "Content-Type: application/json" \
  -d '{
    "golden_record_id": "G-a1b2c3d4",
    "new_bucket_keys": ["naics4:4237+TX", "city:AUSTIN+TX"],
    "chain_depth": 0
  }'
```

### GET /health

```bash
curl http://localhost:8080/health
# {"status": "healthy", "service": "entity-resolution-agent", "version": "3.0.0"}
```

### GET /stats

```bash
curl http://localhost:8080/stats
# {"requests": 142, "merges": 98, "creates": 31, "reviews": 13, "errors": 0, "uptime_seconds": 3600}
```

## Escalation Strategy

```
Orphan record arrives
  │
  ▼
Step 1: find_candidates (MySQL indexed queries)
  │ 0 candidates → NEW_ENTITY
  │ 1+ candidates → Step 2
  ▼
Step 2: compare_fields (deterministic scoring)
  │ > 0.85 → MERGE (DETERMINISTIC)
  │ < 0.40 all → NEW_ENTITY
  │ 0.40–0.85 → Step 3
  ▼
Step 3: semantic_similarity (Gemini embeddings)
  │ Combined > 0.85 → MERGE (EMBEDDING)
  │ < 0.40 all → NEW_ENTITY
  │ 0.40–0.85 → Step 4
  ▼
Step 4: LLM reasoning (Claude)
  │ MERGE → MERGE (LLM)
  │ NEW_ENTITY → NEW_ENTITY
  │ Ambiguous → REVIEW (human queue)
  ▼
Step 5: Write action + audit (always)
```

~70% of records resolve at Step 2 (deterministic). ~20% need embeddings. ~10% need LLM.

## Data Stores

| Store | Role | Read by | Written by |
|---|---|---|---|
| **MySQL** | Source of truth (ACID) | Agent (find_candidates, golden record reads), UI | Agent (entity_writer) |
| **Milvus** | Vector search (ANN) | UI search bar, Agent "find similar" | Agent (entity_writer, Pattern A immediate) |
| **GraphDB** | Ontology reasoning (SPARQL) | Agent (compare_fields cross-taxonomy), UI graph viz | Agent (entity_writer) |
| **OTEL** | Observability | Kibana dashboards | Agent (auto-instrumented) |

### MySQL Tables (written by agent)

| Table | Purpose |
|---|---|
| `golden_records` | Mastered entities — one row per resolved business |
| `relationships` | Business network edges with transaction volume |
| `resolution_audit` | Every agent decision (append-only) |
| `pending_resolution` | Human review queue for ambiguous matches |

### MySQL Indexes (used by find_candidates)

| Index | Bucket Key Pattern | Query |
|---|---|---|
| `idx_gr_ein` | `ein:{value}` | `WHERE ein = ?` |
| `ft_gr_name` | `name:{token}+{state}` | `MATCH(canonical_name) AGAINST(? IN BOOLEAN MODE)` |
| `idx_gr_naics_state` | `naics4:{code}+{state}` | `WHERE naics_code LIKE ? AND state = ?` |
| `idx_gr_city_state` | `city:{city}+{state}` | `WHERE city = ? AND state = ?` |
| `idx_gr_zip3` | `zip3:{value}` | `WHERE zip3 = ?` |

All queries include `AND status != 'MERGED'`. All sub-10ms at 1M records.

### Milvus Collection Schema

| Field | Type | Dim | Source Text |
|---|---|---|---|
| `name_embedding` | FloatVector | 128 | canonical_name + name_variants |
| `industry_vector` | FloatVector | 64 | NAICS label + category |
| `commodity_vector` | FloatVector | 64 | commodity keywords |
| `location_embedding` | FloatVector | 32 | city + state + zip |
| `behavioral_vector` | FloatVector | 64 | volume bracket + avg txn |
| `composite_vector` | FloatVector | 256 | Weighted concat (fallback) |

Scalar fields: `golden_record_id`, `state`, `naics_prefix`, `confidence`, `entity_type`, `source_count`.

Embeddings via Gemini `text-embedding-004` with `output_dimensionality` for native dim reduction.

## Write Path

Every golden record mutation follows this sequence:

```
1. MySQL COMMIT    (~5ms)    — source of truth, ACID
2. Milvus UPSERT  (~150ms)  — vector embeddings (Pattern A: immediate)
3. KG Triples     (~30ms)   — ontology links (optional)
```

For `merge_golden_records` (the critical operation), MySQL uses a single transaction:
```sql
BEGIN
  UPDATE golden_records SET ... WHERE golden_record_id = :survivor_id;
  UPDATE golden_records SET status='MERGED', merged_into=:survivor_id WHERE golden_record_id = :absorbed_id;
  INSERT INTO resolution_audit (...);
COMMIT
```

## Observability

OTEL traces for every `/resolve` call:

```
resolve (root)
├── step.find_candidates          candidates_found, buckets_checked
├── step.compare_fields           composite, disqualified
├── step.semantic_similarity      composite_similarity, model
├── step.llm_reasoning            decision, confidence, fallback
└── (merge | create | submit_review)
```

8 metrics: `resolution.duration_ms`, `resolution.decisions`, `resolution.step_duration_ms`,
`resolution.llm_calls`, `resolution.embedding_calls`, `resolution.candidate_count`,
`resolution.errors`, `resolution.active`

## Persona Dimensions

The `ClassifiedPersona` is the agent's input. 5 dimensions, each scored independently:

| Dimension | Weight | Fields | Scoring |
|---|---|---|---|
| **Identity** | 0.35 | name, EIN, phone, email | Jaro-Winkler on name, exact match on EIN/phone |
| **Industry** | 0.25 | NAICS code, sector, keywords | Exact/prefix match, ontology cross-taxonomy |
| **Location** | 0.15 | state, city, zip5, zip3 | Hierarchical (state=base, city=bonus, zip=bonus) |
| **Commodity** | 0.15 | top_keywords, service_categories | Jaccard overlap on keyword sets |
| **Behavioral** | 0.10 | volume_bracket, avg_transaction, count | Bracket match, ratio proximity |

Hard disqualifiers: different EIN → instant reject. Different state → instant reject.

## Project Structure

```
qb-network-graph-entity-agent/
├── setup.sh                    # one-time setup
├── run-agent.sh                # interactive menu
├── .env.example                # all env vars with defaults (copy → .env)
├── .gitignore
├── agent-config.yaml           # YAML base config (overridden by .env)
├── requirements.txt
├── main.py                     # FastAPI app — wires MySQL, Milvus, GraphDB, LLM
├── config.py                   # config loader — MySQLConfig, MilvusConfig, etc.
├── orchestrator.py             # brain — escalation strategy (resolve + re-evaluate)
├── models/
│   ├── persona.py              # ClassifiedPersona, GoldenRecord
│   ├── resolution.py           # request/response, comparison results
│   └── audit.py                # audit trail, pending resolutions
├── mcp/
│   ├── candidate_evaluator.py  # MCP 1: read-side (find_candidates via MySQL)
│   ├── knowledge_graph.py      # MCP 2: ontology + KG R/W (SPARQL)
│   └── entity_writer.py        # MCP 3: mutations (MySQL → Milvus → KG)
├── clients/
│   ├── mysql_client.py         # golden records, bucket queries, transactional merge
│   ├── milvus_client.py        # multi-vector embeddings, hybrid search
│   ├── graphdb_client.py       # SPARQL queries + updates
│   ├── embedding_client.py     # Gemini embeddings (pairwise comparison)
│   └── llm_client.py           # Anthropic Claude reasoning
├── utils/
│   ├── scoring.py              # Jaro-Winkler, Jaccard, dimension scoring
│   ├── bucket_keys.py          # bucket key generation from persona
│   └── telemetry.py            # OTEL traces + metrics
├── observability/
│   ├── otel-collector-config.yaml
│   └── setup-kibana-dashboards.sh
└── tests/
    └── test_agent.py           # 42 tests (unit + integration)
```

## Graceful Degradation

| Service | Missing | Fallback |
|---|---|---|
| MySQL driver | Not installed | In-memory dict (full mock) |
| MySQL server | Connection refused | In-memory dict |
| Milvus | Not installed/down | In-memory list (no vector search) |
| Gemini API | No API key | Local sentence-transformers (384d) |
| sentence-transformers | Not installed | Zero vectors |
| GraphDB | Not running | KG writes silently skipped |
| Claude LLM | No API key | Fallback decision = REVIEW |
| OTEL collector | Not running | Telemetry disabled |

The agent runs with **zero external services** for local development.

## Related Projects

| Project | Language | Purpose |
|---|---|---|
| **db/** (Liquibase) | YAML/SQL | MySQL schema — 16 changesets (0001-0016) |
| **qb-network-graph-classifier-orchestrator** | Java | Reads Paimon CDC, classifies → ClassifiedPersona → POST /resolve |
| **qb-network-graph-stream-aggregator** | Flink SQL | 9 CDC jobs → Paimon bronze → 2 aggregation jobs → entity_connections |
| **qb-ontology** | RDF/TTL | GraphDB T-Box (NAICS/UNSPSC/GEO, 682 triples) |

## Design Documents

For deeper architectural context:

- `QB-Network-Graph-Knowledge-Base.md` — Full system design (data model, stores, query layer)
- `QB-Network-Graph-UI-Knowledge-Base.md` — UI design (search, graph visualization)
- `entity-resolution-agent-design.md` — Agent internals (MCP tools, orchestrator logic)
- `agent-build-plan.md` — Build phases with test criteria
