# QB Network Graph — Database Schema (Liquibase)

Complete MySQL schema for the QuickBooks Business Network Graph system. Managed by Liquibase for version-controlled, repeatable migrations.

## Overview

16 changesets across two domains:

| Range | Domain | Description |
|---|---|---|
| 0001–0011 | **QuickBooks Source** | CDC-captured tables — companies, vendors, customers, invoices, bills, payments, match_decisions, cdc_reader grants |
| 0012–0016 | **Golden Records** | Entity resolution output — golden_records, relationships, resolution_audit, pending_resolution, cdc grants |

```
QuickBooks Source (0001-0011)         Golden Records (0012-0016)
┌───────────────────────────┐        ┌──────────────────────────────┐
│ companies (QB user)       │        │ golden_records               │
│ vendors (buy-side)        │───────▶│   (mastered entities)        │
│ customers (sell-side)     │        │ relationships                │
│ invoices + line_items     │        │   (edges with volume)        │
│ bills + line_items        │        │ resolution_audit             │
│ payments                  │        │   (every agent decision)     │
│ match_decisions           │◀───────│ pending_resolution           │
│ cdc_reader (binlog user)  │        │   (human review queue)       │
└───────────────────────────┘        └──────────────────────────────┘
```

## Prerequisites

- **MySQL 8.0+** running on localhost:3306
- **Liquibase 4.x** installed ([download](https://www.liquibase.com/download))
- **MySQL Connector/J** JAR (e.g., `mysql-connector-j-8.3.0.jar`)

## Database Setup

```bash
# 1. Create database and admin user (run as MySQL root)
mysql -u root -p <<'SQL'
CREATE DATABASE IF NOT EXISTS quickbooks
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'qb_admin'@'%' IDENTIFIED BY 'qb_admin_pass';
GRANT ALL PRIVILEGES ON quickbooks.* TO 'qb_admin'@'%';
FLUSH PRIVILEGES;
SQL

# 2. Verify connection
mysql -u qb_admin -pqb_admin_pass -e "SELECT 1" quickbooks
```

## Running Migrations

```bash
cd db/

# Option A: Using liquibase CLI directly
liquibase update \
  --classpath=/path/to/mysql-connector-j-8.3.0.jar \
  --url="jdbc:mysql://localhost:3306/quickbooks?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=UTC" \
  --username=qb_admin \
  --password=qb_admin_pass \
  --changelog-file=changelog/db.changelog-master.yaml

# Option B: Using liquibase.properties (already configured)
liquibase --classpath=/path/to/mysql-connector-j-8.3.0.jar update
```

Liquibase tracks applied changesets in `DATABASECHANGELOG`. If 0001–0011 are already applied (from earlier sessions), only 0012–0016 will run.

## Verifying Migrations

```bash
# Check applied changesets
liquibase --classpath=/path/to/mysql-connector-j-8.3.0.jar status

# Or query directly
mysql -u qb_admin -pqb_admin_pass quickbooks \
  -e "SELECT id, filename, dateexecuted FROM DATABASECHANGELOG ORDER BY orderexecuted"

# Verify golden record tables exist
mysql -u qb_admin -pqb_admin_pass quickbooks \
  -e "SHOW TABLES LIKE 'golden%'; SHOW TABLES LIKE 'relation%'; SHOW TABLES LIKE 'resolution%'; SHOW TABLES LIKE 'pending%';"

# Verify indexes on golden_records
mysql -u qb_admin -pqb_admin_pass quickbooks \
  -e "SHOW INDEX FROM golden_records"
```

## Changeset Details

### 0001–0011: QuickBooks Source Tables

These model the existing QuickBooks MySQL database that our CDC pipeline reads from:

| Changeset | Table | Purpose |
|---|---|---|
| 0001 | `companies` | QB user profiles (the business using QB) |
| 0002 | `vendors` | Businesses the QB user buys from — **primary phantom entity source** |
| 0003 | `customers` | Businesses/people the QB user sells to |
| 0004 | `products_services` | Commodity signal (what's being traded) |
| 0005 | `invoices` | Sell-side transactions |
| 0006 | `invoice_line_items` | Invoice detail rows |
| 0007 | `bills` | Buy-side transactions |
| 0008 | `bill_line_items` | Bill detail rows |
| 0009 | `payments` | Confirmed money flow (proves relationship) |
| 0010 | `match_decisions` | Human review feedback loop — **only table our system writes to in QB schema** |
| 0011 | `cdc_reader` | MySQL user with binlog grants for CDC |

### 0012–0016: Golden Record Tables (NEW)

These are the entity resolution output — written by the Entity Resolution Agent:

#### 0012: `golden_records`

The mastered entity table. One row per resolved business entity.

```sql
golden_records (
    golden_record_id    VARCHAR(36) PK,      -- "G-a1b2c3d4"
    canonical_name      VARCHAR(255),         -- "BOBS PLUMBING LLC"
    name_variants       JSON,                 -- ["Bob's Plumbing", "BP Plumbing"]

    -- Denormalized identity dimensions (from persona JSON)
    ein                 VARCHAR(9),           -- EIN for instant match
    phone_digits        VARCHAR(10),
    email               VARCHAR(255),

    -- Industry
    naics_code          VARCHAR(6),           -- "238220"
    naics_sector        VARCHAR(2),           -- "23"
    naics_subsector     VARCHAR(3),           -- "238"

    -- Location
    state               CHAR(2),              -- "TX"
    city                VARCHAR(100),          -- "AUSTIN" (uppercase)
    zip5                VARCHAR(5),
    zip3                VARCHAR(3),

    -- Commodity
    commodity_keywords  JSON,                 -- ["pvc pipe", "copper fitting"]
    service_categories  JSON,

    -- Behavioral
    total_volume        DECIMAL(14,2),
    avg_transaction     DECIMAL(12,2),
    transaction_count   INT,
    volume_bracket      VARCHAR(10),          -- "SMALL", "MEDIUM", "LARGE"

    -- Resolution metadata
    source_count        INT DEFAULT 1,
    source_records      JSON,                 -- ["1:v-42", "3:v-18"]
    confidence          DECIMAL(4,3),         -- 0.000–0.999
    status              VARCHAR(15),          -- ACTIVE | PROVISIONAL | MERGED
    merged_into         VARCHAR(36),          -- FK to survivor if MERGED
    entity_type         VARCHAR(15),          -- QB_USER | PHANTOM

    -- Full persona for agent reads
    persona             JSON,
    bucket_keys         JSON,                 -- Precomputed for find_candidates

    created_at          TIMESTAMP(3),
    updated_at          TIMESTAMP(3)
)
```

**Key indexes** (these replace the Redis bucket sorted sets):
- `idx_gr_ein` (UNIQUE) — Tier 1 instant match by EIN
- `idx_gr_naics_state` — Industry + geography filter
- `idx_gr_city_state` — Location-based lookup
- `idx_gr_zip3` — Zip prefix search
- `idx_gr_state` — State filter
- `ft_gr_name` (FULLTEXT) — Fuzzy name search

#### 0013: `relationships`

Edges in the business network graph.

```sql
relationships (
    edge_id             VARCHAR(36) PK,
    source_entity_id    VARCHAR(36) FK → golden_records,  -- payer
    target_entity_id    VARCHAR(36) FK → golden_records,  -- payee
    transaction_volume  DECIMAL(14,2),                    -- edge weight
    transaction_count   INT,
    commodity_flow      JSON,                             -- UNSPSC codes
    first_transaction   DATE,
    last_transaction    DATE,
    status              VARCHAR(10) DEFAULT 'ACTIVE',
    UNIQUE (source_entity_id, target_entity_id)
)
```

#### 0014: `resolution_audit`

Append-only audit log — every agent decision is recorded.

```sql
resolution_audit (
    audit_id            VARCHAR(36) PK,
    event_id            VARCHAR(36),
    record_id           VARCHAR(100),      -- orphan record that triggered resolution
    decision            VARCHAR(20),       -- MERGE | NEW_ENTITY | REVIEW | NO_MERGE_FOUND
    trigger_type        VARCHAR(30),       -- LAYER_1_EIN | AI_AGENT_EMBEDDING | AI_AGENT_LLM
    target_golden_id    VARCHAR(36),       -- which GR was matched (if merge)
    absorbed_golden_id  VARCHAR(36),       -- which GR was absorbed (if golden merge)
    confidence          DECIMAL(4,3),
    dimension_scores    JSON,
    reasoning           TEXT,
    key_factors         JSON,
    candidates_evaluated INT,
    llm_calls           INT,
    embedding_calls     INT,
    total_duration_ms   INT,
    evaluation_chain    JSON,
    golden_record_before JSON,
    golden_record_after  JSON,
    created_at          TIMESTAMP(3)
)
```

#### 0015: `pending_resolution`

Human review queue for ambiguous matches.

```sql
pending_resolution (
    match_id            VARCHAR(36) PK,
    orphan_golden_id    VARCHAR(36) FK → golden_records,    -- PROVISIONAL golden record
    candidate_golden_id VARCHAR(36) FK → golden_records,    -- proposed match
    confidence          DECIMAL(4,3),
    dimension_scores    JSON,
    reasoning           TEXT,
    key_uncertainty     TEXT,
    status              VARCHAR(15) DEFAULT 'PENDING',      -- PENDING | APPROVED | REJECTED
    reviewer            VARCHAR(255),
    reviewed_at         TIMESTAMP(3),
    created_at          TIMESTAMP(3)
)
```

#### 0016: CDC grants

Grants `SELECT` on all 4 golden record tables to the `cdc_reader` user (created in 0011) so downstream Flink CDC jobs can read changes.

## Rollback

```bash
# Rollback last N changesets
liquibase --classpath=/path/to/mysql-connector-j-8.3.0.jar rollback-count 5

# Rollback to a specific tag (if tagged)
liquibase --classpath=/path/to/mysql-connector-j-8.3.0.jar rollback <tag>
```

## Project Structure

```
db/
├── liquibase.properties                    # Connection config
├── changelog/
│   ├── db.changelog-master.yaml            # Includes all 16 changesets in order
│   └── versions/
│       ├── 0001-create-companies.yaml
│       ├── 0002-create-vendors.yaml
│       ├── ...
│       ├── 0011-create-cdc-reader.yaml
│       ├── 0012-create-golden-records.yaml    ← NEW
│       ├── 0013-create-relationships.yaml     ← NEW
│       ├── 0014-create-resolution-audit.yaml  ← NEW
│       ├── 0015-create-pending-resolution.yaml ← NEW
│       └── 0016-grant-cdc-golden-records.yaml ← NEW
```

## How the Agent Uses These Tables

```
find_candidates (read)
  golden_records WHERE ein = ?              → idx_gr_ein
  golden_records WHERE naics_code LIKE ?    → idx_gr_naics_state
  golden_records MATCH(canonical_name)...   → ft_gr_name

merge_into_golden_record (write)
  UPDATE golden_records SET ... WHERE golden_record_id = ?

create_golden_record (write)
  INSERT INTO golden_records (...)

merge_golden_records (transactional write)
  BEGIN
    UPDATE golden_records SET ... (survivor)
    UPDATE golden_records SET status='MERGED' (absorbed)
    INSERT INTO resolution_audit (...)
  COMMIT

submit_for_review (write)
  INSERT INTO golden_records (..., status='PROVISIONAL')
  INSERT INTO pending_resolution (...)

log_decision (write)
  INSERT INTO resolution_audit (...)
```

## Related Projects

- **qb-network-graph-entity-agent** — Python agent that reads/writes these tables
- **qb-network-graph-classifier-orchestrator** — Java service that classifies CDC events and feeds the agent
- **qb-ontology** — GraphDB T-Box (NAICS/UNSPSC/GEO ontology)
