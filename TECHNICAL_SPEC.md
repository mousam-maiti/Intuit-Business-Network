# QB Network Graph &mdash; Technical Specification

**Version:** 4.0
**Last Updated:** March 7, 2026

---

## Table of Contents

- [1. System Architecture](#1-system-architecture)
- [2. Database Schemas](#2-database-schemas)
  - [2.1 MySQL Source Tables](#21-mysql-source-tables)
  - [2.2 Paimon Warehouse Tables](#22-paimon-warehouse-tables)
  - [2.3 Neo4j Graph Model](#23-neo4j-graph-model)
  - [2.4 Redis Cache Schema](#24-redis-cache-schema)
- [3. Backend REST API (OpenAPI)](#3-backend-rest-api-openapi)
- [4. Conversational Agent](#4-conversational-agent)
  - [4.1 WebSocket Protocol](#41-websocket-protocol)
  - [4.2 ReAct Loop Implementation](#42-react-loop-implementation)
  - [4.3 REST Endpoints](#43-rest-endpoints)
  - [4.4 Chat Database Schema](#44-chat-database-schema)
  - [4.5 Context Compression](#45-context-compression)
- [5. Entity Resolution Agent](#5-entity-resolution-agent)
  - [5.1 Resolution Pipeline](#51-resolution-pipeline)
  - [5.2 Scoring Model](#52-scoring-model)
  - [5.3 Decision Thresholds](#53-decision-thresholds)
  - [5.4 API Endpoints](#54-api-endpoints)
  - [5.5 Data Models](#55-data-models)
- [6. MCP Server](#6-mcp-server)
  - [6.1 Tool Specifications](#61-tool-specifications)
  - [6.2 Sync API](#62-sync-api)
  - [6.3 Bucket Key Generation](#63-bucket-key-generation)
- [7. Classification Pipeline](#7-classification-pipeline)
- [8. Data Pipeline](#8-data-pipeline)
  - [8.1 CDC Jobs](#81-cdc-jobs)
  - [8.2 Stream Aggregation](#82-stream-aggregation)
  - [8.3 Time Travel and Audit](#83-time-travel-and-audit)
- [9. Shared LLM Providers Package](#9-shared-llm-providers-package)
- [10. Observability](#10-observability)
- [11. Configuration Reference](#11-configuration-reference)

---

## 1. System Architecture

### Service Topology

```
                    +-----------+
                    | React UI  |
                    | :8080     |
                    +-----+-----+
                          |
              +-----------+-----------+
              |                       |
     +--------v-------+     +--------v--------+
     | Backend API    |     | Conv Agent      |
     | FastAPI :8087  |     | FastAPI :8082   |
     +--------+-------+     +--------+--------+
              |                       |
   +----------+----------+   +-------v--------+
   |          |          |   | MCP Server     |
+--v---+ +---v---+ +---v-+  | FastMCP :8083  |
|Neo4j | |Redis  | |Paimon| | Sync API :8084 |
|:7687 | |:6379  | |(fs)  | +-------+--------+
+------+ +-------+ +------+         |
                             +-------v--------+
+----------+                 | Entity Agent   |
|MySQL     |                 | FastAPI :8085  |
|:3306     |                 +-------+--------+
+----+-----+                         |
     |                       +-------+--------+
+----v-----+                 | LLM Providers  |
|Flink CDC |                 | (shared pkg)   |
|(9 jobs)  |                 +----------------+
+----+-----+
     |
+----v---------+     +-------------------+
|Paimon Bronze |     | OTEL Collector    |
|(staged_*)    |     | gRPC :4317        |
+----+---------+     | HTTP :4318        |
     |               | Prom :8889        |
+----v---------+     +--------+----------+
|Stream Agg    |              |
|(2 Flink jobs)|     +--------v----------+
+----+---------+     | Elasticsearch     |
     |               | :9200             |
+----v---------+     +--------+----------+
|Paimon Silver |              |
|(entity_conn) |     +--------v----------+
+----+---------+     | Kibana :5601      |
     |               +-------------------+
+----v---------+
|Classifier    |
|(Java, batch) |
+----+---------+
     |
     v
Entity Agent /resolve
```

### Technology Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Frontend | React 18, Vite 5, Tailwind CSS 3, Recharts, Lucide | Node 18+ |
| Backend API | Python, FastAPI, Uvicorn | Python 3.9+ |
| Conv Agent | Python, FastAPI, WebSocket | Python 3.9+ |
| Entity Agent | Python, FastAPI | Python 3.9+ |
| MCP Server | Python, FastMCP | Python 3.9+ |
| Classifier | Java, Maven | Java 17+ |
| Graph DB | Neo4j | 5.x |
| Relational DB | MySQL | 8.0 |
| Data Warehouse | Apache Paimon (filesystem) | 0.8+ |
| Stream Processing | Apache Flink | 1.18 |
| Cache | Redis | 7.x |
| LLM | Pluggable (default: Google Gemini 2.5) | &mdash; |
| Embeddings | Pluggable (default: Gemini Embedding 001) | &mdash; |
| Ontology | GraphDB Free (RDF/SPARQL) | &mdash; |
| Observability | OpenTelemetry, Elasticsearch, Kibana | &mdash; |
| Containerization | Docker, Docker Compose | &mdash; |
| DB Migrations | Liquibase | &mdash; |

### Port Map

| Port | Service | Protocol |
|------|---------|----------|
| 3306 | MySQL | TCP |
| 4317 | OTEL Collector (gRPC) | gRPC |
| 4318 | OTEL Collector (HTTP) | HTTP |
| 5601 | Kibana | HTTP |
| 6379 | Redis | TCP |
| 7200 | GraphDB (SPARQL) | HTTP |
| 7474 | Neo4j Browser | HTTP |
| 7687 | Neo4j Bolt | Bolt |
| 8080 | UI (Vite dev server) | HTTP |
| 8081 | Flink REST API | HTTP |
| 8082 | Conversational Agent | HTTP/WS |
| 8083 | MCP Server | HTTP/SSE |
| 8084 | MCP Sync API | HTTP |
| 8085 | Entity Resolution Agent | HTTP |
| 8087 | Backend REST API | HTTP |
| 8889 | OTEL Prometheus endpoint | HTTP |
| 9200 | Elasticsearch | HTTP |

---

## 2. Database Schemas

### 2.1 MySQL Source Tables

#### companies
```sql
CREATE TABLE companies (
  company_id    BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  company_name  VARCHAR(255) NOT NULL,
  legal_name    VARCHAR(255),
  legal_structure VARCHAR(255),
  ein           VARCHAR(20),
  industry_category VARCHAR(255),
  street_address VARCHAR(255),
  city          VARCHAR(100),
  state         VARCHAR(2),
  zip           VARCHAR(10),
  primary_contact VARCHAR(255),
  email         VARCHAR(255),
  phone         VARCHAR(20),
  website       VARCHAR(255),
  status        VARCHAR(20) DEFAULT 'active',
  created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_companies_state (state),
  INDEX idx_companies_industry (industry_category),
  INDEX idx_companies_ein (ein)
);
```

#### vendors
```sql
CREATE TABLE vendors (
  vendor_id     BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  company_id    BIGINT UNSIGNED NOT NULL,
  display_name  VARCHAR(255) NOT NULL,
  ein           VARCHAR(20),
  contact_name  VARCHAR(255),
  email         VARCHAR(255),
  phone         VARCHAR(20),
  category      VARCHAR(255),
  commodity     VARCHAR(500),
  street_address VARCHAR(255),
  city          VARCHAR(100),
  state         VARCHAR(2),
  zip           VARCHAR(10),
  website       VARCHAR(255),
  expected_volume DECIMAL(14,2),
  payment_terms VARCHAR(20),
  is_active     BOOLEAN DEFAULT true,
  created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (company_id) REFERENCES companies(company_id),
  INDEX idx_vendors_company (company_id),
  INDEX idx_vendors_display_name (display_name),
  INDEX idx_vendors_ein (ein),
  INDEX idx_vendors_state (state)
);
```

#### customers
```sql
-- Identical schema to vendors
CREATE TABLE customers (
  customer_id   BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  company_id    BIGINT UNSIGNED NOT NULL,
  display_name  VARCHAR(255) NOT NULL,
  ein           VARCHAR(20),
  contact_name  VARCHAR(255),
  email         VARCHAR(255),
  phone         VARCHAR(20),
  category      VARCHAR(255),
  commodity     VARCHAR(500),
  street_address VARCHAR(255),
  city          VARCHAR(100),
  state         VARCHAR(2),
  zip           VARCHAR(10),
  website       VARCHAR(255),
  expected_volume DECIMAL(14,2),
  payment_terms VARCHAR(20),
  is_active     BOOLEAN DEFAULT true,
  created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (company_id) REFERENCES companies(company_id),
  INDEX idx_customers_company (company_id),
  INDEX idx_customers_display_name (display_name),
  INDEX idx_customers_ein (ein),
  INDEX idx_customers_state (state)
);
```

#### invoices
```sql
CREATE TABLE invoices (
  invoice_id    BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  company_id    BIGINT UNSIGNED NOT NULL,
  customer_id   BIGINT UNSIGNED NOT NULL,
  invoice_number VARCHAR(50),
  invoice_date  DATE NOT NULL,
  due_date      DATE,
  total_amount  DECIMAL(14,2) NOT NULL,
  status        VARCHAR(20) DEFAULT 'pending',
  created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (company_id) REFERENCES companies(company_id),
  FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
  INDEX idx_invoices_company (company_id),
  INDEX idx_invoices_customer (customer_id),
  INDEX idx_invoices_date (invoice_date)
);
```

#### bills
```sql
CREATE TABLE bills (
  bill_id       BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  company_id    BIGINT UNSIGNED NOT NULL,
  vendor_id     BIGINT UNSIGNED NOT NULL,
  bill_number   VARCHAR(50),
  bill_date     DATE NOT NULL,
  due_date      DATE,
  total_amount  DECIMAL(14,2) NOT NULL,
  status        VARCHAR(20) DEFAULT 'pending',
  created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (company_id) REFERENCES companies(company_id),
  FOREIGN KEY (vendor_id) REFERENCES vendors(vendor_id),
  INDEX idx_bills_company (company_id),
  INDEX idx_bills_vendor (vendor_id),
  INDEX idx_bills_date (bill_date)
);
```

#### invoice_line_items
```sql
CREATE TABLE invoice_line_items (
  line_item_id  BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  invoice_id    BIGINT UNSIGNED NOT NULL,
  item_id       BIGINT UNSIGNED,
  description   VARCHAR(500) NOT NULL,
  quantity      DECIMAL(10,2) DEFAULT 1.00,
  unit_price    DECIMAL(12,2) NOT NULL,
  amount        DECIMAL(12,2) NOT NULL,
  FOREIGN KEY (invoice_id) REFERENCES invoices(invoice_id),
  INDEX idx_invoice_line_items_invoice (invoice_id)
);
```

#### bill_line_items
```sql
CREATE TABLE bill_line_items (
  line_item_id  BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  bill_id       BIGINT UNSIGNED NOT NULL,
  item_id       BIGINT UNSIGNED,
  description   VARCHAR(500) NOT NULL,
  quantity      DECIMAL(10,2) DEFAULT 1.00,
  unit_price    DECIMAL(12,2) NOT NULL,
  amount        DECIMAL(12,2) NOT NULL,
  expense_category VARCHAR(255),
  FOREIGN KEY (bill_id) REFERENCES bills(bill_id),
  INDEX idx_bill_line_items_bill (bill_id)
);
```

#### payments
```sql
CREATE TABLE payments (
  payment_id    BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  company_id    BIGINT UNSIGNED NOT NULL,
  invoice_id    BIGINT UNSIGNED,
  bill_id       BIGINT UNSIGNED,
  payment_date  DATE NOT NULL,
  amount        DECIMAL(14,2) NOT NULL,
  payment_method VARCHAR(50),
  reference_number VARCHAR(100),
  memo          TEXT,
  created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (company_id) REFERENCES companies(company_id),
  INDEX idx_payments_company (company_id),
  INDEX idx_payments_date (payment_date),
  INDEX idx_payments_invoice (invoice_id),
  INDEX idx_payments_bill (bill_id)
);
```

#### products_services
```sql
CREATE TABLE products_services (
  item_id       BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  company_id    BIGINT UNSIGNED NOT NULL,
  name          VARCHAR(255) NOT NULL,
  description   TEXT,
  type          VARCHAR(20) DEFAULT 'service',
  unit_price    DECIMAL(12,2),
  category      VARCHAR(255),
  is_active     BOOLEAN DEFAULT true,
  created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (company_id) REFERENCES companies(company_id),
  INDEX idx_products_services_company (company_id)
);
```

#### golden_records
```sql
CREATE TABLE golden_records (
  golden_record_id VARCHAR(40) PRIMARY KEY,
  canonical_name   VARCHAR(255) NOT NULL,
  name_variants    JSON,
  ein              VARCHAR(9),
  phone_digits     VARCHAR(10),
  email            VARCHAR(255),
  contact_name     VARCHAR(255),
  naics_code       VARCHAR(6),
  naics_sector     VARCHAR(2),
  naics_subsector  VARCHAR(3),
  state            CHAR(2),
  city             VARCHAR(100),
  zip5             VARCHAR(5),
  zip3             VARCHAR(3),
  street_address   VARCHAR(255),
  commodity_keywords  JSON,
  service_categories  JSON,
  total_volume     DECIMAL(14,2),
  avg_transaction  DECIMAL(12,2),
  transaction_count INT,
  volume_bracket   VARCHAR(10),
  source_count     INT DEFAULT 1,
  source_records   JSON,
  confidence       DECIMAL(4,3),
  status           VARCHAR(15) DEFAULT 'ACTIVE',
  merged_into      VARCHAR(40),
  entity_type      VARCHAR(15) DEFAULT 'PHANTOM',
  persona          JSON,
  bucket_keys      JSON,
  created_at       TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3),
  updated_at       TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  INDEX idx_gr_status (status),
  INDEX idx_gr_merged_into (merged_into),
  INDEX idx_gr_ein (ein),
  INDEX idx_gr_state (state),
  INDEX idx_gr_naics_state (naics_code, state),
  INDEX idx_gr_zip3 (zip3),
  INDEX idx_gr_city_state (city, state),
  INDEX idx_gr_entity_type (entity_type),
  INDEX idx_gr_canonical_name (canonical_name),
  FULLTEXT ft_gr_name (canonical_name)
);
```

#### relationships
```sql
CREATE TABLE relationships (
  edge_id           VARCHAR(36) PRIMARY KEY,
  source_entity_id  VARCHAR(40) NOT NULL,
  target_entity_id  VARCHAR(40) NOT NULL,
  transaction_volume DECIMAL(14,2),
  transaction_count INT,
  commodity_flow    JSON,
  first_transaction DATE,
  last_transaction  DATE,
  status            VARCHAR(10) DEFAULT 'ACTIVE',
  created_at        TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3),
  updated_at        TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  INDEX idx_rel_source (source_entity_id),
  INDEX idx_rel_target (target_entity_id),
  UNIQUE uq_rel_edge (source_entity_id, target_entity_id)
);
```

#### resolution_audit
```sql
CREATE TABLE resolution_audit (
  audit_id          VARCHAR(36) PRIMARY KEY,
  event_id          VARCHAR(36),
  record_id         VARCHAR(100),
  perspective       VARCHAR(10) DEFAULT 'GLOBAL',
  decision          VARCHAR(20) NOT NULL,
  trigger_type      VARCHAR(30),
  target_golden_id  VARCHAR(40),
  absorbed_golden_id VARCHAR(40),
  confidence        DECIMAL(4,3),
  dimension_scores  JSON,
  reasoning         TEXT,
  key_factors       JSON,
  candidates_evaluated INT,
  llm_calls         INT,
  embedding_calls   INT,
  total_duration_ms INT,
  evaluation_chain  JSON,
  golden_record_before JSON,
  golden_record_after  JSON,
  created_at        TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3),
  INDEX idx_audit_event (event_id),
  INDEX idx_audit_target (target_golden_id),
  INDEX idx_audit_decision (decision),
  INDEX idx_audit_created (created_at)
);
```

#### pending_resolution
```sql
CREATE TABLE pending_resolution (
  match_id           VARCHAR(36) PRIMARY KEY,
  orphan_golden_id   VARCHAR(40) NOT NULL,
  candidate_golden_id VARCHAR(40) NOT NULL,
  confidence         DECIMAL(4,3),
  dimension_scores   JSON,
  reasoning          TEXT,
  key_uncertainty    TEXT,
  trigger_type       VARCHAR(30),
  status             VARCHAR(15) DEFAULT 'PENDING',
  company_id         VARCHAR(20),
  record_type        VARCHAR(10),
  reviewer           VARCHAR(255),
  reviewed_at        TIMESTAMP(3),
  created_at         TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3),
  INDEX idx_pending_status (status),
  INDEX idx_pending_orphan (orphan_golden_id),
  INDEX idx_pending_candidate (candidate_golden_id)
);
```

#### match_decisions
```sql
CREATE TABLE match_decisions (
  decision_id   BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
  match_id      VARCHAR(36) NOT NULL,
  company_id    BIGINT UNSIGNED NOT NULL,
  decision      VARCHAR(20) NOT NULL,
  reason        TEXT,
  created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_match_decisions_match (match_id),
  INDEX idx_match_decisions_company (company_id)
);
```

#### native_overrides
```sql
CREATE TABLE native_overrides (
  user_id     VARCHAR(64),
  entity_id   VARCHAR(64),
  overrides   JSON,
  created_at  TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3),
  updated_at  TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (user_id, entity_id)
);
```

#### native_merges
```sql
CREATE TABLE native_merges (
  merge_id           VARCHAR(64) PRIMARY KEY,
  user_id            VARCHAR(64) DEFAULT '1',
  source_entity_id   VARCHAR(64),
  target_entity_id   VARCHAR(64),
  origin             VARCHAR(16) DEFAULT 'user',
  reason             TEXT,
  migrated_relationships JSON,
  created_at         TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3),
  INDEX idx_nm_user (user_id)
);
```

#### manual_connections
```sql
CREATE TABLE manual_connections (
  connection_id       VARCHAR(64) PRIMARY KEY,
  user_id             VARCHAR(64) DEFAULT '1',
  conn_type           VARCHAR(16),
  entity_id           VARCHAR(64),
  entity_snapshot     JSON,
  added_via           VARCHAR(128),
  confidence          FLOAT,
  agent_status        VARCHAR(15),
  agent_decision      VARCHAR(32),
  agent_golden_record_id VARCHAR(64),
  agent_resolved_at   TIMESTAMP(3),
  created_at          TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3),
  INDEX idx_mc_user (user_id)
);
```

#### auto_connections
```sql
CREATE TABLE auto_connections (
  connection_id    VARCHAR(64) PRIMARY KEY,
  user_id          VARCHAR(64) DEFAULT '1',
  conn_type        VARCHAR(16),
  source_doc       VARCHAR(128),
  source_date      VARCHAR(32),
  entity_id        VARCHAR(64) NOT NULL,
  resolution_type  VARCHAR(16) DEFAULT 'auto',
  tier             INT DEFAULT 1,
  confidence       FLOAT,
  latency_ms       INT,
  created_at       TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3),
  INDEX idx_ac_user (user_id)
);
```

#### connection_alerts
```sql
CREATE TABLE connection_alerts (
  alert_id        VARCHAR(32) PRIMARY KEY,
  connection_id   VARCHAR(64) NOT NULL,
  user_id         VARCHAR(64) DEFAULT '1' NOT NULL,
  alert_type      VARCHAR(32) NOT NULL,
  title           VARCHAR(255) NOT NULL,
  message         TEXT,
  entity_name     VARCHAR(255),
  target_entity_id VARCHAR(64),
  confidence      FLOAT,
  dismissed       BOOLEAN DEFAULT false,
  created_at      TIMESTAMP(3) DEFAULT CURRENT_TIMESTAMP(3),
  INDEX idx_alerts_user (user_id, dismissed, created_at)
);
```

### Chat Tables (Conv Agent)

#### chat_sessions
```sql
CREATE TABLE chat_sessions (
  session_id      VARCHAR(36) PRIMARY KEY,
  user_id         VARCHAR(64) NOT NULL,
  title           VARCHAR(255),
  context_summary TEXT,
  compressed_up_to INT DEFAULT 0,
  message_count   INT DEFAULT 0,
  status          ENUM('active', 'archived') DEFAULT 'active',
  created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_user_sessions (user_id, status, updated_at DESC)
);
```

#### chat_messages
```sql
CREATE TABLE chat_messages (
  message_id  VARCHAR(36) PRIMARY KEY,
  session_id  VARCHAR(36) NOT NULL,
  role        ENUM('user', 'assistant', 'system') NOT NULL,
  content     TEXT NOT NULL,
  metadata    JSON,
  token_estimate INT DEFAULT 0,
  created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
  INDEX idx_session_messages (session_id, created_at)
);
```

### 2.2 Paimon Warehouse Tables

All Paimon tables use deduplicate merge engine, 4-8 buckets, daily auto-tags (365 retained).

**Bronze Layer** (`network_graph.*`): Direct CDC mirrors of MySQL source tables.

**Silver Layer:**
- `network_graph.entity_connections` &mdash; Merge engine: `partial-update` (non-NULL overwrites). PK: `(company_id, connection_id, connection_type)`.

**Gold Layer** (`gold.*`): `golden_records`, `relationships`, `pending_resolution`, `resolution_audit`, `connection_alerts` &mdash; identical schemas to MySQL tables above.

### 2.3 Neo4j Graph Model

#### Node: Entity
```
Properties:
  id: String (golden_record_id)
  canonical_name: String
  name_variants: List<String>
  ein: String
  phone_digits: String
  email: String
  email_domain: String
  contact_name: String
  naics_code: String
  naics_sector: String
  naics_subsector: String
  state: String
  city: String
  zip5: String
  zip3: String
  street_address: String
  commodity_keywords: List<String>
  service_categories: List<String>
  total_volume: Float
  avg_transaction: Float
  transaction_count: Integer
  volume_bracket: String
  source_count: Integer
  confidence: Float
  status: String (ACTIVE|PROVISIONAL|MERGED)
  merged_into: String
  entity_type: String (QB_USER|PHANTOM)
  embedding: List<Float> (768d, cosine similarity)
  created_at: String (ISO8601)
  updated_at: String (ISO8601)

Constraints:
  UNIQUE (id)

Indexes:
  canonical_name, status, ein, phone_digits, email_domain,
  (naics_code, state), zip3, (city, state)
  FULLTEXT on canonical_name
  VECTOR on embedding (768 dimensions, cosine)
```

#### Relationship: BUYS_FROM / SELLS_TO
```
Properties:
  edge_id: String
  transaction_volume: Float
  transaction_count: Integer
  commodity_flow: List<String>
  first_transaction: String (date)
  last_transaction: String (date)
  status: String (ACTIVE|DORMANT)
```

#### Relationship: MERGED_INTO
```
Properties:
  merge_date: String
  reasoning: String
```

#### Node: AuditEntry
```
Properties:
  audit_id, event_id, record_id, perspective, decision,
  trigger_type, target_golden_id, absorbed_golden_id,
  confidence, reasoning, created_at
```

### 2.4 Redis Cache Schema

| Key Pattern | TTL | Description |
|-------------|-----|-------------|
| `entity:{id}` | 1h | Cached entity profile |
| `rels:{id}` | 1h | Cached entity relationships |
| `subgraph:{id}:{depth}` | 30m | Cached network subgraph |
| `connections:{company_id}:{type}` | 1h | Company vendor/customer list |
| `traverse:{start_id}:{hops_hash}` | 15m | Supply chain traversal result |
| `search:{md5_hash}` | 24h | Search result cache (BE, max 200 keys LRU) |

---

## 3. Backend REST API (OpenAPI)

```yaml
openapi: "3.0.3"
info:
  title: QB Network Graph API
  version: "4.0.0"
  description: REST API for the QB business network intelligence platform
servers:
  - url: http://localhost:8087/api/v1

paths:
  /health:
    get:
      summary: Health check
      operationId: health
      tags: [Health]
      responses:
        "200":
          description: OK
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                    example: ok

  /entities:
    get:
      summary: List entities
      operationId: listEntities
      tags: [Entities]
      parameters:
        - name: q
          in: query
          schema: { type: string }
          description: Search by name
        - name: industry
          in: query
          schema: { type: string }
          description: Filter by NAICS code
        - name: company_id
          in: query
          schema: { type: string }
          description: Scope to related entities
      responses:
        "200":
          description: Entity list
          content:
            application/json:
              schema:
                type: object
                properties:
                  data:
                    type: array
                    items: { $ref: "#/components/schemas/Entity" }
                  total:
                    type: integer

  /entities/{entity_id}:
    get:
      summary: Get entity detail
      operationId: getEntity
      tags: [Entities]
      parameters:
        - name: entity_id
          in: path
          required: true
          schema: { type: string }
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  data: { $ref: "#/components/schemas/Entity" }
        "404":
          $ref: "#/components/responses/NotFound"
    patch:
      summary: Update entity fields
      operationId: updateEntity
      tags: [Entities]
      parameters:
        - name: entity_id
          in: path
          required: true
          schema: { type: string }
      requestBody:
        content:
          application/json:
            schema:
              type: object
              additionalProperties: true
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  data: { $ref: "#/components/schemas/Entity" }

  /relationships:
    get:
      summary: List all relationships
      operationId: listRelationships
      tags: [Relationships]
      parameters:
        - name: company_id
          in: query
          schema: { type: string }
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  data:
                    type: array
                    items: { $ref: "#/components/schemas/Relationship" }

  /entities/{entity_id}/relationships:
    get:
      summary: Entity direct relationships
      operationId: getEntityRelationships
      tags: [Relationships]
      parameters:
        - name: entity_id
          in: path
          required: true
          schema: { type: string }
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  data:
                    type: array
                    items: { $ref: "#/components/schemas/Relationship" }

  /entities/{entity_id}/network:
    get:
      summary: Multi-hop subgraph
      operationId: getNetwork
      tags: [Relationships]
      parameters:
        - name: entity_id
          in: path
          required: true
          schema: { type: string }
        - name: depth
          in: query
          schema: { type: integer, default: 2 }
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  data: { $ref: "#/components/schemas/NetworkGraph" }

  /entities/{entity_id}/supply-chain:
    get:
      summary: Supply chain traversal
      operationId: getSupplyChain
      tags: [Relationships]
      parameters:
        - name: entity_id
          in: path
          required: true
          schema: { type: string }
        - name: direction
          in: query
          schema: { type: string, enum: [upstream, downstream], default: upstream }
        - name: depth
          in: query
          schema: { type: integer, default: 5 }
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  data:
                    type: object
                    properties:
                      chain:
                        type: array
                        items:
                          type: object
                          properties:
                            entity: { $ref: "#/components/schemas/Entity" }
                            depth: { type: integer }
                      edges:
                        type: array
                        items: { $ref: "#/components/schemas/Relationship" }

  /entities/{id_a}/shortest-path/{id_b}:
    get:
      summary: Shortest path between entities
      operationId: getShortestPath
      tags: [Relationships]
      parameters:
        - name: id_a
          in: path
          required: true
          schema: { type: string }
        - name: id_b
          in: path
          required: true
          schema: { type: string }
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  data:
                    type: object
                    properties:
                      chain: { type: array, items: { type: object } }
                      edges: { type: array, items: { $ref: "#/components/schemas/Relationship" } }
                      hops: { type: integer }
                      message: { type: string }

  /entities/{id_a}/common-neighbors/{id_b}:
    get:
      summary: Shared neighbors
      operationId: getCommonNeighbors
      tags: [Relationships]
      parameters:
        - name: id_a
          in: path
          required: true
          schema: { type: string }
        - name: id_b
          in: path
          required: true
          schema: { type: string }
        - name: limit
          in: query
          schema: { type: integer, default: 20 }
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  data:
                    type: object
                    properties:
                      common_neighbors: { type: array, items: { type: object } }
                      count: { type: integer }
                      entity_a_name: { type: string }
                      entity_b_name: { type: string }

  /entities/{entity_id}/cluster:
    get:
      summary: Cluster detection
      operationId: getCluster
      tags: [Relationships]
      parameters:
        - name: entity_id
          in: path
          required: true
          schema: { type: string }
        - name: max_size
          in: query
          schema: { type: integer, default: 20 }
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  data:
                    type: object
                    properties:
                      entities: { type: array, items: { $ref: "#/components/schemas/Entity" } }
                      relationships: { type: array, items: { $ref: "#/components/schemas/Relationship" } }
                      density: { type: number }
                      member_count: { type: integer }
                      top_industries: { type: array, items: { type: object } }

  /entities/{entity_id}/impact:
    get:
      summary: Risk impact analysis
      operationId: getImpact
      tags: [Relationships]
      parameters:
        - name: entity_id
          in: path
          required: true
          schema: { type: string }
        - name: max_depth
          in: query
          schema: { type: integer, default: 3 }
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  data:
                    type: object
                    properties:
                      affected_entities:
                        type: array
                        items:
                          type: object
                          properties:
                            id: { type: string }
                            name: { type: string }
                            depth: { type: integer }
                            volume_at_risk: { type: number }
                      affected_count: { type: integer }
                      total_volume_at_risk: { type: number }
                      depth_distribution: { type: object }
                      concentration_warning: { type: string, nullable: true }

  /entities/{entity_id}/volume:
    get:
      summary: Monthly transaction volume
      operationId: getVolume
      tags: [Relationships]
      parameters:
        - name: entity_id
          in: path
          required: true
          schema: { type: string }
        - name: company_id
          in: query
          schema: { type: string }
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  data:
                    type: array
                    items:
                      type: object
                      properties:
                        month: { type: string }
                        vol: { type: integer }

  /search:
    get:
      summary: Entity search
      operationId: searchEntities
      tags: [Search]
      parameters:
        - name: q
          in: query
          schema: { type: string }
        - name: industry
          in: query
          schema: { type: string }
        - name: sortBy
          in: query
          schema: { type: string, enum: [relevance, volume, connections, confidence] }
        - name: limit
          in: query
          schema: { type: integer, default: 50, minimum: 1, maximum: 200 }
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  data:
                    type: array
                    items: { $ref: "#/components/schemas/Entity" }
                  total: { type: integer }
                  cached: { type: boolean }

  /matching/pending:
    get:
      summary: Pending matches
      operationId: getPendingMatches
      tags: [Matching]
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  data:
                    type: array
                    items: { $ref: "#/components/schemas/PendingMatch" }

  /matching/{match_id}/candidates:
    get:
      summary: Candidates for match
      operationId: getCandidates
      tags: [Matching]
      parameters:
        - name: match_id
          in: path
          required: true
          schema: { type: string }
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  candidates:
                    type: array
                    items:
                      type: object
                      properties:
                        entity: { $ref: "#/components/schemas/Entity" }
                        confidence: { type: number }
                  error: { type: string, nullable: true }

  /matching/{match_id}/resolve:
    post:
      summary: Resolve a pending match
      operationId: resolveMatch
      tags: [Matching]
      parameters:
        - name: match_id
          in: path
          required: true
          schema: { type: string }
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [resolution]
              properties:
                resolution: { type: string, enum: [accept, reject] }
                candidateGoldenId: { type: string }
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  data:
                    type: object
                    properties:
                      matchId: { type: string }
                      resolution: { type: string }
                      resolvedAt: { type: string, format: date-time }

  /matching/resolve:
    post:
      summary: Ad-hoc entity resolution
      operationId: resolveAdHoc
      tags: [Matching]
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                name: { type: string }
                ein: { type: string }
                city: { type: string }
                state: { type: string }
                industry: { type: string }
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  data:
                    type: object
                    properties:
                      tier: { type: integer }
                      match: { $ref: "#/components/schemas/Entity" }
                      candidates: { type: array, items: { type: object } }

  /connections/auto:
    get:
      summary: Auto-detected connections
      operationId: getAutoConnections
      tags: [Connections]
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  data: { type: array, items: { $ref: "#/components/schemas/AutoConnection" } }

  /connections/manual:
    get:
      summary: Manually added connections
      operationId: getManualConnections
      tags: [Connections]
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  data: { type: array, items: { $ref: "#/components/schemas/ManualConnection" } }

  /connections:
    post:
      summary: Add new connection
      operationId: addConnection
      tags: [Connections]
      requestBody:
        required: true
        content:
          application/json:
            schema: { $ref: "#/components/schemas/AddConnectionRequest" }
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  data:
                    type: object
                    properties:
                      id: { type: string }
                      status: { type: string }

  /connections/add-network:
    post:
      summary: Add existing entity to network
      operationId: addExistingToNetwork
      tags: [Connections]
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [goldenRecordId, connType]
              properties:
                goldenRecordId: { type: string }
                connType: { type: string, enum: [vendor, client] }
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  data:
                    type: object
                    properties:
                      added_entity_id: { type: string }
                      added_entity_name: { type: string }
                      conn_type: { type: string }
                      neighbor_count: { type: integer }
                      entities: { type: array, items: { $ref: "#/components/schemas/Entity" } }
                      relationships: { type: array, items: { $ref: "#/components/schemas/Relationship" } }

  /connections/remove:
    post:
      summary: Remove connection
      operationId: removeConnection
      tags: [Connections]
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [entityId]
              properties:
                entityId: { type: string }
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  data:
                    type: object
                    properties:
                      removed_entity_id: { type: string }
                      removed_entity_name: { type: string }
                      removed: { type: boolean }

  /native/overrides:
    get:
      summary: All user overrides
      operationId: getAllOverrides
      tags: [Native]
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  data: { type: object, additionalProperties: { type: object } }

  /native/overrides/{entity_id}:
    get:
      summary: Entity overrides
      operationId: getOverride
      tags: [Native]
      parameters:
        - name: entity_id
          in: path
          required: true
          schema: { type: string }
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  data: { type: object, nullable: true }
    patch:
      summary: Save field overrides
      operationId: saveOverride
      tags: [Native]
      parameters:
        - name: entity_id
          in: path
          required: true
          schema: { type: string }
      requestBody:
        content:
          application/json:
            schema: { type: object, additionalProperties: true }
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  data: { type: object }

  /native/overrides/{entity_id}/{field}:
    delete:
      summary: Reset field override
      operationId: deleteOverrideField
      tags: [Native]
      parameters:
        - name: entity_id
          in: path
          required: true
          schema: { type: string }
        - name: field
          in: path
          required: true
          schema: { type: string }
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  data: { type: object, nullable: true }

  /native/merges:
    get:
      summary: All native merges
      operationId: getMerges
      tags: [Native]
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  data:
                    type: array
                    items: { $ref: "#/components/schemas/NativeMerge" }
    post:
      summary: Create native merge
      operationId: createMerge
      tags: [Native]
      requestBody:
        required: true
        content:
          application/json:
            schema: { $ref: "#/components/schemas/CreateMergeRequest" }
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  data: { $ref: "#/components/schemas/NativeMerge" }

  /native/merges/{merge_id}:
    delete:
      summary: Undo native merge
      operationId: deleteMerge
      tags: [Native]
      parameters:
        - name: merge_id
          in: path
          required: true
          schema: { type: string }
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  data: { $ref: "#/components/schemas/NativeMerge" }
        "404":
          $ref: "#/components/responses/NotFound"

  /alerts:
    get:
      summary: Pending alerts
      operationId: getAlerts
      tags: [Alerts]
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  data: { type: array, items: { $ref: "#/components/schemas/Alert" } }

  /alerts/{alert_id}/dismiss:
    post:
      summary: Dismiss alert
      operationId: dismissAlert
      tags: [Alerts]
      parameters:
        - name: alert_id
          in: path
          required: true
          schema: { type: string }
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  data:
                    type: object
                    properties:
                      dismissed: { type: boolean }

  /lineage/entities:
    get:
      summary: Entities with audit trails
      operationId: getLineageEntities
      tags: [Lineage]
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  data:
                    type: array
                    items:
                      type: object
                      properties:
                        id: { type: string }
                        name: { type: string }
                        industry: { type: string }
                        status: { type: string }

  /lineage/trail/{entity_id}:
    get:
      summary: Entity audit trail
      operationId: getAuditTrail
      tags: [Lineage]
      parameters:
        - name: entity_id
          in: path
          required: true
          schema: { type: string }
        - name: limit
          in: query
          schema: { type: integer, default: 100 }
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  data: { type: array, items: { $ref: "#/components/schemas/AuditEntry" } }

  /lineage/snapshot/{entity_id}:
    get:
      summary: Entity state at point in time
      operationId: getSnapshot
      tags: [Lineage]
      parameters:
        - name: entity_id
          in: path
          required: true
          schema: { type: string }
        - name: date
          in: query
          required: true
          schema: { type: string, format: date-time }
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  data: { type: object, nullable: true }

  /lineage/restore/{entity_id}:
    post:
      summary: Restore entity to historical state
      operationId: restoreEntity
      tags: [Lineage]
      parameters:
        - name: entity_id
          in: path
          required: true
          schema: { type: string }
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [audit_id, snapshot]
              properties:
                audit_id: { type: string }
                snapshot: { type: object }
      responses:
        "200":
          content:
            application/json:
              schema:
                type: object
                properties:
                  data:
                    type: object
                    properties:
                      success: { type: boolean }
                      audit_id: { type: string }
                      error: { type: string }

  /infra/metrics:
    get:
      summary: Infrastructure metrics
      operationId: getInfraMetrics
      tags: [Infrastructure]
      responses:
        "200":
          content:
            application/json:
              schema: { $ref: "#/components/schemas/InfraMetrics" }

components:
  schemas:
    Entity:
      type: object
      properties:
        id: { type: string }
        name: { type: string }
        ein: { type: string, nullable: true }
        contactName: { type: string, nullable: true }
        email: { type: string, nullable: true }
        phone: { type: string, nullable: true }
        website: { type: string, nullable: true }
        industry: { type: string, nullable: true }
        naics: { type: string, nullable: true }
        legalStructure: { type: string, nullable: true }
        address: { type: string, nullable: true }
        city: { type: string, nullable: true }
        state: { type: string, nullable: true }
        zip: { type: string, nullable: true }
        confidence: { type: number, nullable: true }
        vendors: { type: integer }
        clients: { type: integer }
        volume: { type: number, nullable: true }
        variants: { type: array, items: { type: string } }
        commodities: { type: array, items: { type: string } }
        serviceArea: { type: string, nullable: true }

    Relationship:
      type: object
      properties:
        source: { type: string }
        target: { type: string }
        volume: { type: number, nullable: true }
        count: { type: integer, nullable: true }
        status: { type: string, nullable: true }

    NetworkGraph:
      type: object
      properties:
        entities: { type: array, items: { $ref: "#/components/schemas/Entity" } }
        relationships: { type: array, items: { $ref: "#/components/schemas/Relationship" } }

    PendingMatch:
      type: object
      properties:
        id: { type: string }
        inputName: { type: string, nullable: true }
        inputCategory: { type: string, nullable: true }
        inputLocation: { type: string, nullable: true }
        candidate: { $ref: "#/components/schemas/Entity" }
        confidence: { type: number, nullable: true }
        age: { type: string, nullable: true }
        scores: { type: object, nullable: true }
        sharedNeighbors: { type: array, items: { type: string } }
        triggerType: { type: string }

    AutoConnection:
      type: object
      properties:
        id: { type: string }
        type: { type: string, enum: [vendor, client] }
        source: { type: string }
        sourceDate: { type: string }
        entity: { $ref: "#/components/schemas/Entity" }
        resolution: { type: string, nullable: true }
        tier: { type: integer, nullable: true }
        confidence: { type: number, nullable: true }
        latency: { type: string, nullable: true }
        time: { type: string, nullable: true }

    ManualConnection:
      type: object
      properties:
        id: { type: string }
        type: { type: string }
        addedVia: { type: string }
        confidence: { type: number, nullable: true }
        time: { type: string, nullable: true }
        entity: { type: object }

    AddConnectionRequest:
      type: object
      required: [connType, name]
      properties:
        connType: { type: string, enum: [vendor, client] }
        name: { type: string }
        ein: { type: string }
        contactName: { type: string }
        email: { type: string }
        phone: { type: string }
        website: { type: string }
        category: { type: string }
        commodity: { type: string }
        address: { type: string }
        city: { type: string }
        state: { type: string }
        zip: { type: string }
        expectedVolume: { type: string }
        paymentTerms: { type: string }

    NativeMerge:
      type: object
      properties:
        id: { type: string }
        sourceEntityId: { type: string }
        targetEntityId: { type: string }
        origin: { type: string }
        reason: { type: string, nullable: true }
        timestamp: { type: string, nullable: true }
        migratedRelationships: { type: array, items: { type: object } }

    CreateMergeRequest:
      type: object
      required: [sourceEntityId, targetEntityId]
      properties:
        sourceEntityId: { type: string }
        targetEntityId: { type: string }
        reason: { type: string }
        migratedRelationships: { type: array, items: { type: object } }

    Alert:
      type: object
      properties:
        id: { type: string }
        connectionId: { type: string }
        type: { type: string }
        title: { type: string }
        message: { type: string }
        entityName: { type: string }
        targetEntityId: { type: string }
        confidence: { type: number }
        time: { type: string }

    AuditEntry:
      type: object
      properties:
        audit_id: { type: string }
        event_id: { type: string }
        record_id: { type: string }
        perspective: { type: string }
        decision: { type: string, enum: [MERGE, NEW_ENTITY, REVIEW, NO_MERGE_FOUND, RESTORE] }
        trigger_type: { type: string }
        target_golden_id: { type: string, nullable: true }
        absorbed_golden_id: { type: string, nullable: true }
        confidence: { type: number }
        dimension_scores: { type: object }
        reasoning: { type: string }
        key_factors: { type: array, items: { type: string } }
        evaluation_chain: { type: array, items: { type: object } }
        golden_record_before: { type: object, nullable: true }
        golden_record_after: { type: object, nullable: true }
        created_at: { type: string, format: date-time }

    InfraMetrics:
      type: object
      properties:
        redis:
          type: object
          properties:
            status: { type: string }
            total_keys: { type: integer }
            hits: { type: integer }
            misses: { type: integer }
            hit_rate: { type: number }
            memory_used_mb: { type: number }
            memory_peak_mb: { type: number }
            keys_by_type: { type: object }
        neo4j:
          type: object
          properties:
            status: { type: string }
            entities: { type: object }
            relationships: { type: object }
        paimon:
          type: object
          properties:
            status: { type: string }
            warehouse: { type: string }
            tables: { type: object }
        elasticsearch:
          type: object
          properties:
            status: { type: string }
            cluster_name: { type: string }
            node_count: { type: integer }
            active_shards: { type: integer }
            indices: { type: object }
        kibana:
          type: object
          properties:
            status: { type: string }
            version: { type: string }
        otel_collector:
          type: object
          properties:
            status: { type: string }
            grpc_port: { type: integer }
            http_port: { type: integer }
            prometheus_port: { type: integer }
            pipeline: { type: object }
        duration_ms: { type: integer }

  responses:
    NotFound:
      description: Resource not found
      content:
        application/json:
          schema:
            type: object
            properties:
              error: { type: string }
              detail: { type: string }
```

---

## 4. Conversational Agent

### 4.1 WebSocket Protocol

**Endpoint:** `WS /ws/{session_id}?user_id={user_id}` (port 8082)

#### Client &rarr; Server

**message:**
```json
{
  "type": "message",
  "content": "What are my top vendors?",
  "context": {
    "selectedEntity": { "id": "G-12345", "name": "Acme Corp" },
    "currentPage": "network"
  }
}
```

**ping:** `{"type": "ping"}`

**clear_context:** `{"type": "clear_context"}`

#### Server &rarr; Client

**session_info** (sent on connect):
```json
{
  "type": "session_info",
  "session_id": "<uuid>",
  "title": "Session title",
  "message_count": 5
}
```

**thought** (streamed during ReAct):
```json
{
  "type": "thought",
  "text": "I need to find the company's top vendors",
  "step": 1
}
```

**tool_call** (MCP tool execution):
```json
{
  "type": "tool_call",
  "name": "get_company_connections",
  "status": "running|done|error",
  "label": "Gathering vendor data",
  "result_preview": "..."
}
```

**response** (final answer):
```json
{
  "type": "response",
  "content": "Your top 3 vendors are...",
  "entities": ["G-12345"],
  "table": { "headers": ["Name", "Volume"], "rows": [["Vendor A", "$500K"]] },
  "chart": { "type": "bar|area|pie", "title": "Top Vendors", "data": [{"name": "A", "value": 500000}] },
  "scores": [{ "label": "Confidence", "value": 0.92 }],
  "signals": [{ "icon": "positive|negative|neutral", "text": "Healthy concentration" }],
  "actions": [{ "label": "View in network", "action": "navigate|select_entity|ask", "payload": {} }],
  "followup": "Would you like to see competitors?",
  "thought_steps": 3
}
```

**error:** `{"type": "error", "message": "Processing error: ..."}`

**context_cleared:** `{"type": "context_cleared", "session_id": "<uuid>"}`

### 4.2 ReAct Loop Implementation

**Max iterations:** 8. **System prompt** enforces strict format:

```
Thought: <1-3 sentence reasoning>
Action: tool_name({"arg": "value"})

Observation: <tool result>

Thought: <summary>
Answer: {"content": "...", "table": {...}, "chart": {...}}
```

**Parsing regexes:**
- Thought: `^Thought:\s*(.+?)(?=\n(?:Action:|Answer:)|$)`
- Action: `^Action:\s*(\w+)\((.+)\)\s*$`
- Answer: `^Answer:\s*(.+)$` (last match used)

**JSON repair:** 3-tier fallback: `json.loads` &rarr; `json_repair` &rarr; `{}` or `{"content": text}`

**Error recovery:** Malformed function calls get a corrective observation. Max iterations exceeded triggers a forced Answer prompt.

**UI context injection:** When `selectedEntity` provided, system prompt includes `company_id` and instructs agent to use `get_company_connections` for "my X" queries.

### 4.3 REST Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Component health (MCP, MySQL, LLM status) |
| `GET` | `/sessions?user_id=` | List user sessions |
| `POST` | `/sessions?user_id=` | Create session |
| `GET` | `/sessions/{id}/messages?limit=100` | Message history |
| `DELETE` | `/sessions/{id}` | Archive session |

### 4.4 Chat Database Schema

See [chat_sessions and chat_messages](#chat-tables-conv-agent) in section 2.1.

### 4.5 Context Compression

Triggered when `message_count >= max_messages` (default: 30).

1. Split messages: older (all but last 10) + recent (last 10)
2. LLM summarizes older messages into `context_summary` (max 500 words)
3. Summary persisted to `chat_sessions.context_summary`
4. Older messages deleted
5. On next request, summary injected as first history entry

---

## 5. Entity Resolution Agent

### 5.1 Resolution Pipeline

```
ClassifiedPersona (from Classifier Orchestrator)
    |
    v
[Step 1] find_candidates (MCP tool)
    |-- Identity anchors: EIN, phone, email_domain
    |-- Vector search fallback (Neo4j, state-scoped)
    |-- Bucket key search (if no vector)
    |-- 0 candidates -> NEW_ENTITY
    |
    v
[Step 2] compare_fields (MCP tool, per candidate)
    |-- 5-dimension scoring
    |-- Name gate: Jaro-Winkler < 0.75 -> skip
    |-- Hard disqualifiers: EIN mismatch, state mismatch
    |-- Fast-paths: EIN exact + same state -> 0.95
    |-- Vector score blending
    |-- composite > 0.82 -> MERGE (deterministic)
    |-- All < 0.45 -> NEW_ENTITY
    |
    v
[Step 3] LLM Reasoning (~30% of cases)
    |-- Cascade guard: chain_depth >= 3 -> force REVIEW
    |-- Evidence: persona + candidates + scores
    |-- LLM: gemini-2.5-pro (ambiguous model)
    |-- Fallback: REVIEW if LLM unavailable
    |
    v
Decision: MERGE | NEW_ENTITY | REVIEW
    |-- MERGE -> merge_into_golden_record + log_decision
    |-- NEW_ENTITY -> create_golden_record + log_decision
    |-- REVIEW -> submit_for_review + log_decision
```

### 5.2 Scoring Model

**Dimension weights:**

| Dimension | Entity Agent Weight | MCP Server Weight |
|-----------|-------------------|-------------------|
| Identity | 0.50 | 0.35 |
| Industry | 0.20 | 0.25 |
| Location | 0.12 | 0.15 |
| Commodity | 0.10 | 0.15 |
| Behavioral | 0.08 | 0.10 |

**Adaptive weight redistribution:** If a dimension has `INSUFFICIENT` data, its weight is redistributed proportionally to available dimensions.

**Name floor cap:**
- Jaro-Winkler < 0.55 &rarr; cap composite at 0.30
- Jaro-Winkler < 0.75 &rarr; cap composite at 0.40

**Dimension scoring details:**

| Dimension | Signal | Score |
|-----------|--------|-------|
| Identity | EIN exact match | 0.90-1.0 |
| Identity | Phone exact match | 0.85 |
| Identity | Email domain match | 0.70 |
| Identity | Name Jaro-Winkler | 0.0-1.0 |
| Identity | Name in variants | 1.0 |
| Industry | NAICS 6-digit exact | 1.0 |
| Industry | Subsector (3-digit) | 0.8 |
| Industry | Sector (2-digit) | 0.5 |
| Industry | Cross-taxonomy link | 0.35 |
| Location | State mismatch | 0.0 (hard disqualifier) |
| Location | ZIP5 exact | 1.0 |
| Location | ZIP3 match | 0.8 |
| Location | City match | 0.7 |
| Location | State only | 0.3 |
| Commodity | Keyword Jaccard overlap | 0.0-1.0 |
| Behavioral | Volume bracket match | 0.7 |
| Behavioral | Within 10x ratio | 0.6 |

### 5.3 Decision Thresholds

| Parameter | Entity Agent | MCP Server |
|-----------|-------------|------------|
| `auto_merge` | 0.82 | 0.85 |
| `human_review` | 0.55 | 0.60 |
| `new_entity` | 0.55 | 0.60 |
| `embedding_needed_low` | 0.45 | 0.40 |
| `embedding_needed_high` | 0.82 | 0.85 |
| `min_identity_score` (name gate) | 0.75 | &mdash; |
| `max_chain_depth` | 3 | &mdash; |
| `force_review_at_depth` | 3 | &mdash; |

### 5.4 API Endpoints

**Port 8085, prefix `/api/v1`**

#### POST /resolve

**Request:**
```json
{
  "event_id": "evt-1-v42",
  "record_id": "v-42",
  "record_type": "vendor",
  "company_id": 1,
  "chain_depth": 0,
  "classified_persona": { "identity": {...}, "industry": {...}, "location": {...}, "commodity": {...}, "behavioral": {...}, "sparsity": {...} },
  "fast_mode": false
}
```

**Response:**
```json
{
  "event_id": "evt-1-v42",
  "decision": "MERGE",
  "target_golden_record_id": "G-abc12345",
  "confidence": 0.92,
  "dimension_scores": {
    "identity": 0.95, "industry": 0.88, "location": 0.90,
    "commodity": 0.67, "behavioral": 0.80
  },
  "reasoning": "Strong EIN match with high name similarity...",
  "key_factors": ["EIN exact match", "Same state and city", "Name 95% similar"],
  "evaluation_chain": [
    {"step": "find_candidates", "candidates_found": 3, "duration_ms": 120},
    {"step": "compare_fields", "top_score": 0.92, "duration_ms": 45},
    {"step": "merge_decision", "reason": "composite > auto_merge threshold"}
  ],
  "agent_metadata": {
    "trigger_type": "AI_AGENT_DETERMINISTIC",
    "total_duration_ms": 285,
    "llm_calls": 0,
    "embedding_calls": 0,
    "candidates_evaluated": 3
  },
  "golden_record_after": {...},
  "relationship": {...},
  "audit_record": {...}
}
```

#### POST /re-evaluate

**Request:**
```json
{
  "golden_record_id": "G-abc12345",
  "new_bucket_keys": ["ein:123456789"],
  "chain_depth": 1
}
```

#### GET /health

```json
{
  "status": "healthy",
  "service": "entity-resolution-agent",
  "version": "4.0.0",
  "components": {
    "mcp_server": "connected",
    "mcp_tools": 23,
    "llm": "connected",
    "llm_provider": "gemini",
    "llm_model": "gemini-2.5-pro",
    "embedding_provider": "gemini",
    "embedding_model": "gemini-embedding-001"
  }
}
```

#### GET /stats

```json
{
  "requests": 142, "merges": 98, "creates": 30,
  "reviews": 14, "errors": 0, "uptime_seconds": 3600
}
```

### 5.5 Data Models

See `ClassifiedPersona`, `GoldenRecord`, `ComparisonResult`, `SimilarityResult`, `AuditRecord`, `PendingResolution` in [section 2.1](#golden_records) for field-level schemas.

---

## 6. MCP Server

**Port:** 8083 (MCP protocol), 8084 (Sync HTTP API)
**Transport:** FastMCP with Streamable HTTP + SSE

### 6.1 Tool Specifications

#### Candidate Tools (3)

| Tool | Parameters | Returns |
|------|-----------|---------|
| `find_candidates` | `orphan_persona: dict`, `max_candidates: int = 20` | `{candidates: [{golden_record_id, canonical_name, name_variants, persona, source_count, confidence, matched_via_buckets}], bucket_stats, duration_ms}` |
| `compare_fields` | `orphan_persona: dict`, `candidate: dict` | `ComparisonResult {identity, industry, location, commodity, behavioral, composite, weights_used, sparsity_adjusted, disqualified, disqualification_reason}` |
| `semantic_similarity` | `orphan_persona: dict`, `candidate: dict` | `{name_similarity, industry_similarity, commodity_similarity, location_similarity, composite_similarity, model_used, inference_ms}` |

#### Entity Writer Tools (5)

| Tool | Parameters | Returns |
|------|-----------|---------|
| `merge_into_golden_record` | `orphan_record_id, orphan_persona, golden_record_id, merge_reasoning, company_id, record_type` | `{success, golden_record_id, golden_record_before, golden_record_after, relationship, duration_ms}` |
| `create_golden_record` | `orphan_record_id, orphan_persona, creation_reasoning, company_id, record_type` | `{success, golden_record_id, golden_record_after, bucket_keys, relationship, duration_ms}` |
| `submit_for_review` | `orphan_record_id, orphan_persona, candidate_golden_record_id, review_reasoning, company_id, record_type` | `{success, provisional_golden_record_id, pending_match_id, golden_record_after, pending_resolution, relationship, duration_ms}` |
| `merge_golden_records` | `survivor_id, absorbed_id, merge_reasoning` | `{success, survivor_id, absorbed_id, survivor_before, survivor_after, audit_record, duration_ms}` |
| `log_decision` | `event_id, record_id, decision, target_golden_record_id, confidence, dimension_scores, reasoning, key_factors, evaluation_chain, agent_metadata` | Audit record dict |

#### Knowledge Graph Tools (7)

| Tool | Parameters | Returns |
|------|-----------|---------|
| `query_ontology` | `query_type: str`, `code_a: str`, `code_b: str` | `{related, relationship_type, semantic_distance, path_a, path_b, lowest_common_ancestor, explanation}` |
| `check_shared_context` | `entity_a_id: str`, `known_counterparties: list[str]` | `{shared_neighbors, industry_coherence, supporting_evidence}` |
| `batch_industry_filter` | `reference_naics: str`, `candidates: list[dict]` | `{reference_naics, matches, match_count, unmatched_count}` |
| `find_shortest_path` | `entity_a: str`, `entity_b: str` | `{chain, edges, hops, duration_ms}` |
| `find_common_neighbors` | `entity_a_id: str`, `entity_b_id: str`, `limit: int = 20` | `{common_neighbors, count, entity_a_name, entity_b_name}` |
| `detect_cluster` | `entity_id: str`, `max_size: int = 20` | `{nodes, edges, density, center, member_count, top_industries}` |
| `assess_risk_impact` | `entity_id: str`, `max_depth: int = 3` | `{target_entity, affected_entities, affected_count, total_volume_at_risk, depth_distribution, concentration_warning}` |

#### Search Tools (8)

| Tool | Parameters | Returns |
|------|-----------|---------|
| `search_entities` | `query, naics_filter, state_filter, city_filter, min_confidence, limit` | `{results, total_found, query, filters_applied}` |
| `describe_entity` | `entity_id: str` | `{entity, neighbors, neighbor_count, neo4j_available}` |
| `query_network` | `entity_id, depth (1-3), direction` | `{nodes, edges, node_count, edge_count, depth_reached}` |
| `aggregate_stats` | `group_by, state_filter, naics_filter, min_confidence` | `{groups, total, group_by, filters_applied}` |
| `search_by_relationship` | `entity_id, relationship_type, company_id` | `{related_entities, count, source_entity}` |
| `get_company_connections` | `company_id, connection_type, sort_by, limit` | `{connections, total, summary}` |
| `get_merge_history` | `entity_id, limit` | `{entity_id, audit_records, total_records, summary}` |
| `traverse_supply_chain` | `start_entity_id, hops: list[str], max_per_hop, min_volume` | `{paths, total_paths, nodes, insights, depth, from_cache}` |

### 6.2 Sync API

**Port 8084** (runs alongside MCP server)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/sync/golden-record` | Upsert golden record to Neo4j + embedding |
| `POST` | `/sync/relationship` | Create/update Neo4j edge |
| `POST` | `/sync/audit` | Create AuditEntry node in Neo4j |
| `POST` | `/sync/pending-resolution` | Acknowledge pending resolution |
| `POST` | `/sync/transfer-relationships` | Migrate edges after golden record merge |
| `GET` | `/sync/candidates/{orphan_golden_id}` | Get candidates for orphan (used by BE) |
| `POST` | `/backfill/embeddings` | Backfill embeddings for all entities |
| `POST` | `/backfill/volumes` | Backfill relationship volumes |

### 6.3 Bucket Key Generation

Format: `{type}:{value}` or `{type}:{value}+{state}`

| Key Type | Format | Example |
|----------|--------|---------|
| EIN | `ein:{digits}` | `ein:743218976` |
| Phone | `phone:{digits}` | `phone:5124551234` |
| Email domain | `email_domain:{domain}` | `email_domain:acme.com` |
| Name + state | `name:{TOKEN}+{STATE}` | `name:ACME+TX` |
| NAICS 4-digit | `naics4:{code}+{STATE}` | `naics4:2382+TX` |
| NAICS 3-digit | `naics3:{code}+{STATE}` | `naics3:238+TX` |
| ZIP3 | `zip3:{zip3}` | `zip3:787` |
| City | `city:{CITY}+{STATE}` | `city:AUSTIN+TX` |
| Commodity | `commodity:{KW}+{STATE}` | `commodity:PLUMBING+TX` |

---

## 7. Classification Pipeline

**Service:** `qb-network-graph-classifier-orchestrator` (Java 17, Maven)

Reads `entity_connections` from Paimon silver, runs 5 classifiers, POSTs `ClassifiedPersona` to Entity Agent `/api/v1/resolve`.

| Classifier | Input | Output |
|------------|-------|--------|
| `NameNormalizer` | `display_name` | `normalized_name`, `name_first_token`, `name_tokens`, `legal_suffix` |
| `IdentityClassifier` | `ein`, `phone`, `email` | `ein_clean`, `phone_digits`, `email`, `email_domain` |
| `IndustryClassifier` | `category` | `naics_code`, `naics_sector`, `naics_subsector` |
| `CommodityExtractor` | `category`, `commodity` | `top_keywords`, `service_categories` |
| `LocationNormalizer` | `city`, `state`, `zip` | `city_norm`, `state`, `zip3`, `zip5` |
| `BehavioralClassifier` | `total_volume`, `transaction_count` | `volume_bracket`, `avg_transaction` |

**Modes:** `batch` (read all, classify, exit) or `stream` (tail changelog continuously).

**Sparsity scoring:** Each dimension scored 0-5 based on field completeness.

---

## 8. Data Pipeline

### 8.1 CDC Jobs

9 Flink CDC jobs, each with:
- Source: MySQL binlog (`cdc_reader` user)
- Sink: Paimon bronze table
- Mode: Streaming, 30s checkpoints
- Server IDs: 5400-5408

| Job | Source | Paimon Table |
|-----|--------|-------------|
| 1 | `companies` | `staged_companies` |
| 2 | `vendors` | `staged_vendors` |
| 3 | `customers` | `staged_customers` |
| 4 | `invoices` | `staged_invoices` |
| 5 | `bills` | `staged_bills` |
| 6 | `payments` | `staged_payments` |
| 7 | `invoice_line_items` | `staged_invoice_line_items` |
| 8 | `bill_line_items` | `staged_bill_line_items` |
| 9 | `match_decisions` | `staged_match_decisions` |

### 8.2 Stream Aggregation

2 Flink SQL jobs transform bronze to silver:

**Job 1 (Identity Sync):** Joins staged vendors/customers with companies. Writes identity + location + industry fields, NULL for behavioral.

**Job 2 (Transaction Aggregation):** Computes `SUM(total_amount)`, `COUNT(*)`, `MIN(date)`, `MAX(date)` from bills/invoices. Writes behavioral fields, NULL for identity.

**Merge engine:** `partial-update` &mdash; non-NULL values overwrite, NULL values skip. Both jobs write to `entity_connections` with PK `(company_id, connection_id, connection_type)`.

### 8.3 Time Travel and Audit

**System-level:** Paimon daily auto-tags (watermark-based, 365 retained). Any gold table queryable at any historical tag.

**Entity-level:** `resolution_audit` stores `golden_record_before` and `golden_record_after` JSON snapshots per mutation. Linked to pipeline provenance via `flink_job_name` + `checkpoint_id`.

**PIP-5 Lineage:** 4 system tables (`source_job_lineage`, `sink_job_lineage`, `source_snapshot_lineage`, `sink_snapshot_lineage`) track snapshot-to-snapshot lineage across Flink jobs.

---

## 9. Shared LLM Providers Package

**Location:** `qb-network-graph-llm-providers/llm_providers/`

### Abstract Interfaces

```python
class LLMProvider(ABC):
    async def connect(self): ...
    def generate(self, prompt, system=None, temperature=None,
                 max_tokens=None, response_format=None) -> str: ...
    def chat(self, history, message, system=None,
             temperature=None, max_tokens=None) -> str: ...
    @property
    def available(self) -> bool: ...
    @property
    def model_name(self) -> str: ...

class EmbeddingProvider(ABC):
    async def connect(self): ...
    def embed(self, text) -> Optional[np.ndarray]: ...
    def embed_batch(self, texts) -> list[Optional[np.ndarray]]: ...
    @property
    def dimension(self) -> int: ...
    @property
    def available(self) -> bool: ...
```

### Factory Functions

```python
from llm_providers import create_llm_provider, create_embedding_provider

llm = create_llm_provider(provider="gemini", model="gemini-2.5-pro",
                           temperature=0.3, max_tokens=4096)
emb = create_embedding_provider(provider="gemini", model="gemini-embedding-001",
                                 dimension=768)
```

### Gemini Implementation

- `GeminiLLMProvider`: wraps `google.generativeai.GenerativeModel`. Handles `_safe_text()` extraction (MALFORMED_FUNCTION_CALL), role mapping (`assistant` &rarr; `model`), JSON mode via `response_mime_type`.
- `GeminiEmbeddingProvider`: tries new `google.genai` SDK first (supports `output_dimensionality`), falls back to deprecated `google.generativeai`.

All imports conditional (`try/except`) to avoid pulling numpy into services that don't need embeddings.

---

## 10. Observability

### OTEL Collector Pipeline

```yaml
receivers:
  otlp:
    protocols:
      grpc: { endpoint: "0.0.0.0:4317" }
      http: { endpoint: "0.0.0.0:4318" }
  prometheus:
    config:
      scrape_configs:
        - job_name: flink
          static_configs:
            - targets: ["localhost:9249"]

exporters:
  elasticsearch/traces:
    endpoints: ["http://localhost:9200"]
    traces_index: qb-traces
  elasticsearch/logs:
    endpoints: ["http://localhost:9200"]
    logs_index: qb-logs
  prometheus:
    endpoint: "0.0.0.0:8889"

pipelines:
  traces: { receivers: [otlp], exporters: [elasticsearch/traces] }
  metrics: { receivers: [prometheus], exporters: [prometheus] }
  logs: { receivers: [otlp], exporters: [elasticsearch/logs] }
```

### Instrumented Services

| Service | Metrics | Spans |
|---------|---------|-------|
| Backend API | FastAPI auto-instrumentation | All HTTP requests |
| Conv Agent | `conv.message_duration_ms`, `conv.messages`, `conv.llm_calls`, `conv.tool_calls`, `conv.errors` | Message processing, tool calls |
| Entity Agent | `resolve` root span, `step.*` child spans | Full pipeline per resolution |
| MCP Server | FastMCP auto-instrumentation | Tool executions |

---

## 11. Configuration Reference

### Backend API (`be-config.yaml`)

| Section | Key | Default | Env Override |
|---------|-----|---------|--------------|
| server | host | 0.0.0.0 | `BE_HOST` |
| server | port | 8087 | `BE_PORT` |
| mysql | host | localhost | `MYSQL_HOST` |
| mysql | port | 3306 | `MYSQL_PORT` |
| mysql | database | quickbooks | `MYSQL_DATABASE` |
| mysql | pool_size | 5 | `MYSQL_POOL_SIZE` |
| neo4j | uri | bolt://localhost:7687 | `NEO4J_URI` |
| neo4j | database | neo4j | `NEO4J_DATABASE` |
| neo4j | max_pool_size | 10 | `NEO4J_POOL_SIZE` |
| redis | db | 2 | `REDIS_DB` |
| redis | search_ttl | 86400 | `REDIS_SEARCH_TTL` |
| redis | search_max_keys | 200 | `REDIS_SEARCH_MAX_KEYS` |
| entity_agent | url | http://localhost:8085 | `ENTITY_AGENT_URL` |
| entity_agent | timeout | 30 | `ENTITY_AGENT_TIMEOUT` |
| telemetry | enabled | true | `OTEL_ENABLED` |

### Conversational Agent (`agent-config.yaml`)

| Section | Key | Default | Env Override |
|---------|-----|---------|--------------|
| server | port | 8082 | `SERVER_PORT` |
| mcp_server | url | http://localhost:8083/mcp | `MCP_SERVER_URL` |
| mcp_server | timeout_ms | 30000 | `MCP_SERVER_TIMEOUT_MS` |
| llm | provider | gemini | `LLM_PROVIDER` |
| llm | model | gemini-2.5-pro | `LLM_MODEL` |
| llm | temperature | 0.3 | `LLM_TEMPERATURE` |
| llm | max_tokens | 4096 | `LLM_MAX_TOKENS` |
| context | max_messages | 30 | `CONTEXT_MAX_MESSAGES` |
| context | keep_recent | 10 | `CONTEXT_KEEP_RECENT` |
| context | max_iterations | 8 | `CONTEXT_MAX_ITERATIONS` |

### Entity Agent (`agent-config.yaml`)

| Section | Key | Default | Env Override |
|---------|-----|---------|--------------|
| server | port | 8085 | `SERVER_PORT` |
| thresholds | auto_merge | 0.82 | `THRESHOLD_AUTO_MERGE` |
| thresholds | human_review | 0.55 | `THRESHOLD_HUMAN_REVIEW` |
| thresholds | new_entity | 0.55 | `THRESHOLD_NEW_ENTITY` |
| thresholds | min_identity_score | 0.75 | `THRESHOLD_MIN_IDENTITY` |
| weights | identity | 0.50 | `WEIGHT_IDENTITY` |
| weights | industry | 0.20 | `WEIGHT_INDUSTRY` |
| weights | location | 0.12 | `WEIGHT_LOCATION` |
| weights | commodity | 0.10 | `WEIGHT_COMMODITY` |
| weights | behavioral | 0.08 | `WEIGHT_BEHAVIORAL` |
| llm | model | gemini-2.5-flash | `LLM_MODEL` |
| llm | ambiguous_model | gemini-2.5-pro | `LLM_AMBIGUOUS_MODEL` |
| llm | temperature | 0.0 | `LLM_TEMPERATURE` |
| llm | fallback_decision | REVIEW | `LLM_FALLBACK_DECISION` |
| embedding | model | gemini-embedding-001 | `EMBEDDING_MODEL` |
| embedding | dimension | 3072 | `EMBEDDING_DIMENSION` |
| re_evaluation | max_chain_depth | 3 | `RE_EVAL_MAX_CHAIN_DEPTH` |
| re_evaluation | force_review_at_depth | 3 | `RE_EVAL_FORCE_REVIEW_AT_DEPTH` |

### MCP Server (`server-config.yaml`)

| Section | Key | Default | Env Override |
|---------|-----|---------|--------------|
| server | port | 8083 | `SERVER_PORT` |
| thresholds | auto_merge | 0.85 | `THRESHOLD_AUTO_MERGE` |
| thresholds | human_review | 0.60 | `THRESHOLD_HUMAN_REVIEW` |
| weights | identity | 0.35 | `WEIGHT_IDENTITY` |
| weights | industry | 0.25 | `WEIGHT_INDUSTRY` |
| weights | location | 0.15 | `WEIGHT_LOCATION` |
| weights | commodity | 0.15 | `WEIGHT_COMMODITY` |
| weights | behavioral | 0.10 | `WEIGHT_BEHAVIORAL` |
| neo4j | uri | bolt://localhost:7687 | `NEO4J_URI` |
| neo4j | max_pool_size | 50 | `NEO4J_POOL_SIZE` |
| redis | default_ttl | 3600 | `REDIS_DEFAULT_TTL` |
| embedding | model | gemini-embedding-001 | `EMBEDDING_MODEL` |
| embedding | dimension | 768 | `EMBEDDING_DIMENSION` |
