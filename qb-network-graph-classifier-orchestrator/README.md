# QB Network Graph — Classifier Orchestrator

Bridges the gap between raw entity connections and the Entity Resolution Agent. Reads `entity_connections` from Paimon, classifies each row into a `ClassifiedPersona`, and feeds the agent via `POST /resolve`.

## Architecture

```
Paimon (silver)                       Entity Resolution Agent
┌─────────────────────┐              ┌──────────────────────┐
│  entity_connections  │              │  POST /resolve       │
│  ┌───────┬────────┐ │  StreamTable │  {                   │
│  │Job 1  │ Job 2  │ │  Scan (Java) │    classified_persona│
│  │Identity│ Txn   │ │──────────────│    { identity,       │
│  │ Sync  │ Agg   │ │  classify    │      industry,       │
│  └───────┴────────┘ │  + POST      │      location, ... } │
│  partial-update      │              │  }                   │
│  merge engine        │              └──────────────────────┘
└─────────────────────┘
```

### What This Module Does

1. **Reads** `entity_connections` via Paimon Java API (`StreamTableScan` or batch)
2. **Classifies** each row through 5 classifiers:
   - `NameNormalizer` → `"Bob's Plumbing LLC"` → `"BOBS PLUMBING"` + tokens + legal suffix
   - `IndustryClassifier` → `"Plumbing Supply"` → NAICS `423720` + sector `42`
   - `CommodityExtractor` → `"PVC pipe, copper fittings"` → keywords + service categories
   - `LocationNormalizer` → `city/state/zip` → `AUSTIN/TX/787/78745`
   - `BehavioralClassifier` → `$84,000 / 47 txns` → `MEDIUM` bracket + avg
3. **Computes** sparsity scores per dimension (0-5 scale)
4. **POSTs** `ClassifiedPersona` to agent's `/resolve` endpoint

### Pipeline Position

```
MySQL → CDC → Paimon Bronze → Stream Aggregator → [THIS] → Entity Agent → Golden Records
         (9 jobs)              (2 jobs)            Java       Python         Paimon Silver
         BUILT                 BUILT               BUILT      BUILT          
```

## Prerequisites

- JDK 17+
- Maven 3.8+
- Paimon warehouse at `$WAREHOUSE_PATH` with `entity_connections` table populated
- Entity Resolution Agent running (optional — use `--classify-only` without it)

## Quick Start

```bash
# 1. Build + batch classify all entity connections
./run.sh

# 2. Stream mode — tail the changelog continuously
./run.sh --stream

# 3. Classify to JSON files (no agent needed)
./run.sh --classify-only

# 4. Build only
./run.sh --build

# 5. Run tests
./run.sh --test
```

## Configuration

Edit `src/main/resources/app.properties`:

```properties
warehouse.path=/path/to/paimon-warehouse
paimon.database=network_graph
source.table=entity_connections

agent.base-url=http://localhost:8000
mode=batch          # batch | stream
dry.run=false       # true = classify but skip agent calls
```

All properties can be overridden via environment variables (dots/dashes become underscores, uppercased).
For example, `warehouse.path` can be overridden with `WAREHOUSE_PATH`.

## Modes

### Batch Mode (default)
Reads the full latest snapshot of `entity_connections`, classifies all rows, POSTs each to the agent, prints summary, exits.

```bash
./run.sh              # or: java -jar target/classifier-orchestrator.jar
```

### Stream Mode
Uses Paimon's `StreamTableScan` with checkpoint/restore. Continuously tails the changelog, classifying new/changed rows as they arrive. Survives restarts via checkpoint file.

```bash
./run.sh --stream     # or: java -jar target/classifier-orchestrator.jar --stream
```

### Classify-Only Mode
Runs all classifiers but writes JSON files to `./classified-output/` instead of calling the agent. Useful for inspecting classification quality.

```bash
./run.sh --classify-only
ls classified-output/
# vendor-1-42.json  vendor-1-43.json  customer-1-1.json ...
```

## Output Example

A classified vendor row:

```json
{
  "event_id": "evt-1-42",
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
      "transaction_count": 47,
      "payment_terms": "Net 30"
    },
    "sparsity": {
      "identity": 5,
      "industry": 4,
      "location": 4,
      "commodity": 3,
      "behavioral": 4
    }
  }
}
```

## Interview Talking Points

**Q: Why Java and not Flink SQL for classification?**
> "In production, this would be a Flink DataStream job reading the `entity_connections` changelog. But classification involves NAICS lookup tables, commodity keyword extraction, and sparsity scoring — all awkward in SQL. A Java process using Paimon's `StreamTableScan` API gives us the same streaming semantics with checkpoint/restore, without the Flink framework overhead. It's the same `paimon-bundle` JAR that Flink uses internally."

**Q: How does StreamTableScan work without Flink?**
> "Paimon's Java API exposes `StreamTableScan` as a standalone class. You call `plan()` in a loop — it returns new splits whenever snapshots are committed upstream. You call `checkpoint()` to save state and `restore()` to resume. It's exactly what Flink's Paimon source connector does under the hood, but we control the loop directly."

**Q: Why not classify inside the Stream Aggregator Flink jobs?**
> "Separation of concerns. The aggregator's job is merging partial writes — identity from CDC, transaction volumes from bills/invoices. Classification is a separate transformation step that depends on the merged result. If we classified inside the aggregator, we'd need the full merged row before classifying, which conflicts with the partial-update pattern where two jobs write different columns."

## Files

```
qb-network-graph-classifier-orchestrator/
├── pom.xml                                      # Maven build with paimon-bundle + Jackson
├── src/main/resources/app.properties             # Configuration
├── run.sh                                       # Build + run script
├── README.md
└── src/
    ├── main/java/com/qb/classifier/
    │   ├── App.java                             # Main: CLI, batch/stream dispatch, stats
    │   ├── config/Config.java                   # app.properties loader
    │   ├── stream/PaimonConsumer.java           # StreamTableScan + batch read
    │   ├── classify/
    │   │   ├── NameNormalizer.java              # "Bob's Plumbing LLC" → BOBS PLUMBING + LLC
    │   │   ├── IdentityClassifier.java          # EIN/phone/email normalization
    │   │   ├── IndustryClassifier.java          # Category → NAICS (150+ mappings)
    │   │   ├── CommodityExtractor.java          # Free text → keyword list
    │   │   ├── LocationNormalizer.java          # City/state/zip normalization
    │   │   ├── BehavioralClassifier.java        # Volume brackets, avg transaction
    │   │   └── PersonaBuilder.java              # Assembles ClassifiedPersona + sparsity
    │   ├── model/
    │   │   ├── EntityConnection.java            # Paimon row → Java record
    │   │   ├── ClassifiedPersona.java           # Agent-compatible persona (Jackson)
    │   │   └── ResolutionRequest.java           # POST /resolve body
    │   └── client/
    │       └── AgentClient.java                 # HTTP client for agent service
    ├── main/resources/
    │   └── logback.xml
    └── test/java/com/qb/classifier/
        └── ClassifierTests.java                 # 20+ tests across all classifiers
```
