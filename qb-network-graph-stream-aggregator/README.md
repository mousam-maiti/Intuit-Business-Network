# QB Network Graph — Stream Aggregator

Continuously aggregates bronze CDC data into a silver `entity_connections` table in Paimon. This is the **mastering input** — one enriched row per (QB account, referenced business) with identity fields + running transaction aggregates.

## Architecture

```
staged_vendors ──┐                      staged_bills ──────┐
staged_customers ┘                      staged_invoices ───┘
       │                                       │
  Job 1: Identity Sync                  Job 2: Transaction Agg
  (display_name, EIN, city,             (SUM volume, COUNT txns,
   category, contact info)               MIN/MAX dates)
       │                                       │
       └───────────┐           ┌───────────────┘
                   ▼           ▼
            entity_connections (Paimon)
            ┌─────────────────────────────────┐
            │ PK: (company_id, connection_id, │
            │      connection_type)            │
            │                                 │
            │ Identity: last_non_null_value    │
            │ Volume:   sum                   │
            │ Counts:   sum                   │
            │ Dates:    min / max             │
            └─────────────────────────────────┘
```

Two long-running Flink streaming jobs write partial records. Paimon's `aggregation` merge engine combines them on the primary key. Each field has its own merge strategy.

## Prerequisites

- Flink cluster running (`$FLINK_HOME/bin/start-cluster.sh`)
- Paimon + Flink CDC JARs in `$FLINK_HOME/lib/`
- 9 CDC jobs running (bronze tables populated)
- Paimon warehouse at `/Users/mousammaiti/IntuitQB-StreamHouse`

## Usage

```bash
# Full pipeline — creates table, submits jobs, verifies
./run.sh

# Check job status
./run.sh --status

# Re-run verification queries
./run.sh --verify

# Cancel entity connections jobs
./run.sh --stop
```

## Configuration

Edit `.env`:

```
WAREHOUSE_PATH=/Users/mousammaiti/IntuitQB-StreamHouse
FLINK_REST_URL=http://localhost:8081
```

## Output

After running, you'll have 11 Flink jobs:
- 9 CDC jobs (MySQL → Paimon bronze)
- 2 aggregator jobs (Paimon bronze → silver/entity_connections)

The `entity_connections` table contains ~636 rows (469 vendor + 167 customer connections) with identity and behavioral data merged together. This is the input for the entity resolution / mastering pipeline.

## Files

```
qb-network-graph-stream-aggregator/
├── run.sh                              # Main runner (create + submit + verify)
├── .env                                # Configuration
├── README.md
└── sql/
    ├── create-entity-connections.sql   # Table DDL (aggregation merge engine)
    ├── job-identity-sync.sql           # Job 1: vendors + customers → identity
    ├── job-transaction-agg.sql         # Job 2: bills + invoices → aggregates
    └── verify.sql                      # 7 verification queries
```
