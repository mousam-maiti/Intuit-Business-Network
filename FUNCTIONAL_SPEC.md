# QB Network Graph &mdash; Functional Specification

**Version:** 4.0
**Last Updated:** March 7, 2026
**Status:** Implementation Complete

---

## Table of Contents

- [1. Overview](#1-overview)
- [2. User-Facing Features](#2-user-facing-features)
  - [2.1 Dashboard](#21-dashboard)
  - [2.2 Business Network Graph](#22-business-network-graph)
  - [2.3 Global Search](#23-global-search)
  - [2.4 Match Review](#24-match-review)
  - [2.5 Connection Lineage](#25-connection-lineage)
  - [2.6 Connections](#26-connections)
  - [2.7 Intuit Assist (AI Chat)](#27-intuit-assist-ai-chat)
  - [2.8 Infrastructure Monitor](#28-infrastructure-monitor)
- [3. Backend REST API](#3-backend-rest-api)
  - [3.1 Entity Endpoints](#31-entity-endpoints)
  - [3.2 Relationship Endpoints](#32-relationship-endpoints)
  - [3.3 Search Endpoints](#33-search-endpoints)
  - [3.4 Matching Endpoints](#34-matching-endpoints)
  - [3.5 Connection Endpoints](#35-connection-endpoints)
  - [3.6 Native Perspective Endpoints](#36-native-perspective-endpoints)
  - [3.7 Lineage Endpoints](#37-lineage-endpoints)
  - [3.8 Infrastructure Endpoints](#38-infrastructure-endpoints)
  - [3.9 Alert Endpoints](#39-alert-endpoints)
- [4. Conversational Agent](#4-conversational-agent)
  - [4.1 WebSocket Protocol](#41-websocket-protocol)
  - [4.2 ReAct Reasoning Loop](#42-react-reasoning-loop)
  - [4.3 Response Blocks](#43-response-blocks)
  - [4.4 Session Management](#44-session-management)
- [5. MCP Tools](#5-mcp-tools)
  - [5.1 Search Tools](#51-search-tools)
  - [5.2 Knowledge Graph Tools](#52-knowledge-graph-tools)
  - [5.3 Entity Writer Tools](#53-entity-writer-tools)
  - [5.4 Candidate Tools](#54-candidate-tools)
- [6. Entity Resolution Agent](#6-entity-resolution-agent)
  - [6.1 Resolution Pipeline](#61-resolution-pipeline)
  - [6.2 Decision Types](#62-decision-types)
  - [6.3 Scoring Model](#63-scoring-model)
  - [6.4 Endpoints](#64-endpoints)
- [7. Classification Pipeline](#7-classification-pipeline)
  - [7.1 Classified Persona Model](#71-classified-persona-model)
  - [7.2 Classifiers](#72-classifiers)
  - [7.3 Sparsity Scoring](#73-sparsity-scoring)
- [8. Data Pipeline](#8-data-pipeline)
  - [8.1 CDC Ingestion](#81-cdc-ingestion)
  - [8.2 Stream Aggregation](#82-stream-aggregation)
  - [8.3 Paimon Warehouse Schema](#83-paimon-warehouse-schema)
  - [8.4 Neo4j Graph Model](#84-neo4j-graph-model)
  - [8.5 Time Travel and Audit](#85-time-travel-and-audit)
- [9. Observability](#9-observability)
- [10. Non-Functional Requirements](#10-non-functional-requirements)

---

## 1. Overview

QB Network Graph is a business network intelligence platform that maps vendor-client relationships across QuickBooks businesses. The system ingests transactional data through CDC streaming, resolves duplicate entities using a 3-tier AI escalation strategy, builds a knowledge graph, and provides an interactive UI with conversational AI for exploring business networks.

### Problem Statement

Given a QuickBooks ecosystem of ~1 million businesses with up to 100 direct relationships each, the platform must:

- Allow businesses to view and navigate their vendor-client network
- Enable search for specific business relationships (direct and indirect)
- Support growing the network by adding new connections that may or may not already exist under different names
- Maintain high availability under 10 million relationship searches per month

### Solution Architecture

The platform is composed of 11 services:

| Service | Port | Role |
|---------|------|------|
| React UI | 8080 | Interactive frontend |
| Backend API | 8087 | REST API serving 21 endpoints across 9 domains |
| Conversational Agent | 8082 | WebSocket-based AI chat with ReAct reasoning |
| MCP Server | 8083 | 23 MCP tools for graph queries and entity operations |
| Entity Resolution Agent | 8085 | 3-tier AI entity deduplication |
| Classifier Orchestrator | &mdash; | 5-stage business classification pipeline (Java) |
| Stream Aggregator | 8081 | Flink SQL jobs for data normalization |
| CDC | &mdash; | 9 Flink jobs capturing MySQL changes |
| LLM Providers | &mdash; | Shared pluggable LLM/embedding abstraction |
| Observability | 4317 | OTEL Collector, Elasticsearch, Kibana |
| Dev Ops | &mdash; | Docker Compose, Liquibase migrations |

---

## 2. User-Facing Features

### 2.1 Dashboard

**Route:** `/dashboard`

The dashboard provides a network health overview with KPI summary cards.

**KPI Cards (5-column grid):**

| Metric | Source |
|--------|--------|
| Total Businesses | Entity count from Neo4j |
| Total Relationships | Relationship count from Neo4j |
| Active Relationships | Relationships with status = `active` |
| Dormant Relationships | Relationships with status = `dormant` |
| Total Volume | Aggregate transaction value (formatted) |

**Visualizations:**

- **Industry Distribution** &mdash; Pie chart grouped by NAICS sector across all entities. 6-color palette with legend showing sector names and counts.
- **Relationship Types** &mdash; Pie chart showing vendor vs. client split for the selected entity.
- **Transaction Volume Trend** &mdash; Area chart of monthly transaction volume over time. Data from `/entities/{id}/volume`.
- **Top Hub Entities** &mdash; Ranked list of top 3 entities by total connection count (vendors + clients). Shows rank, industry icon, name, location, connections, and annual volume. Links to network view.

**Pending Actions (2-column grid):**

| Action | Icon | Destination |
|--------|------|-------------|
| Matches awaiting review | AlertTriangle | Review page |
| Dormant relationships | Info | Network page |

**Entity Resolution Stats (3-column grid):**

| Tier | Description | Target |
|------|-------------|--------|
| Tier 1 | Auto-determined (deterministic) | ~82% |
| Tier 2 | AI persona match (embedding + LLM) | ~15% |
| Manual | Human review | ~3% |

---

### 2.2 Business Network Graph

**Route:** `/network`

Interactive force-directed graph showing the user's vendor-client network.

#### Graph Visualization

- **Layout:** BFS radial algorithm. Center entity at (500, 400). Depth-1 nodes at 200px radius, evenly distributed. Depth-2+ nodes fan out from their parent.
- **Node Colors:** Company (green ring), Vendor (orange), Client (blue), 1-hop (lighter), 2+-hop (lightest)
- **Edge Styles:** Vendor edges (orange), Client edges (blue), Dormant (dashed gray)
- **Interactions:** Click to select entity, drag-to-pan on canvas, zoom in/out, fullscreen toggle

#### Toolbar Controls

| Button | Behavior |
|--------|----------|
| All / Vendors / Clients | Filter visible edges by type (with counts) |
| Find Path | Enter path mode: click start entity, then click end entity. Displays shortest path as `A -> B -> C` with hop count. Shows "No path found" if disconnected. |
| Trace Supply Chain | Enter chain mode with Upstream/Downstream toggle. Displays traversal chain with entity count and edge count. |
| Add Connection | Opens AddConnectionModal |

#### Entity Detail Sidebar (320px, right panel)

Appears when an entity is selected on the graph:

- **Header:** Entity name, industry, location
- **Stats Row:** Vendors count, Clients count, Transaction volume
- **Confidence Gauge:** Circular SVG (72x72) showing match confidence %
- **Volume Chart:** Monthly bar chart of transaction volume
- **Relationship Lists:** Vendors and clients sorted by volume, with dollar amounts
- **Actions:**
  - Edit &mdash; inline field editing
  - Merge into... &mdash; opens MergeFlowModal
  - Ask Intuit Assist &mdash; passes entity context to AI chat
  - Remove Connection &mdash; removes from user's network
  - Trace Supply Chain &mdash; enters supply chain mode for this entity

#### AddConnectionModal

Multi-section form for adding a new vendor or client:

- **Type Selector:** Vendor (purple) / Client (green) toggle
- **Pipeline Explainer:** `You fill form -> Writes to QB MySQL -> CDC picks up -> Same pipeline`
- **Identity Section:** Business name, EIN / Tax ID (instant match indicator), Contact person, Email, Phone
- **Industry & Commodities:** Category / Industry (free text, mapped to NAICS by classifier), Commodity keywords
- **Location:** Address, City, State, Zip

On submit: writes to MySQL, triggers CDC pipeline, which flows through classification and entity resolution.

#### MergeFlowModal

Multi-step wizard for merging two entities from the user's native perspective:

1. **Search & Select Target:** Search for the surviving entity
2. **Merge Comparison:** Side-by-side field comparison showing N fields that differ. Arrow indicating source -> surviving entity.
3. **AI Analysis:** Intuit Assist runs multi-tool analysis (entity_profile, graph_overlap, field_similarity, merge_risk) and shows match assessment with confidence %.
4. **Field Resolution:** Per-field selector to choose which value to keep. Chosen values become native overrides on the surviving entity.
5. **Confirm:** "Confirm native merge" button

---

### 2.3 Global Search

**Route:** `/search`

Search across the entire Intuit Business Network.

#### Search Input

- Placeholder: "Search businesses, industries, commodities..."
- Real-time search with debounce
- Loading spinner during fetch
- Clear button (X) when text present

#### Filters (Left Sidebar, 192px)

**Network Membership:**

| Filter | Description |
|--------|-------------|
| All results | Unfiltered result count |
| In my network | Entities with existing relationship to user |
| Not in network | External entities available to add |

**Industry Facets:** Dynamically generated from results. Shows top 8 industries with result counts.

#### Sort Options

Dropdown with: Relevance (default), Volume, Connections, Confidence

#### Result Cards

Each result displays:

- Entity name (link style), industry, location, connection count
- Relevance / confidence score (% badge, color-coded)
- "not in network" badge for external entities
- For existing connections: RelTypeBadge (vendor/client), annual volume, transaction count, dormant indicator

#### Entity Detail Sidebar (320px, right panel)

Same EntityDetailPanel as Network page, plus context-specific actions:

| Button | Condition | Action |
|--------|-----------|--------|
| Add to Network | Entity not in user's network | Opens AddConnectionModal with Vendor/Client selector |
| Show on Network | Entity in network | Navigates to Network page, selects entity |
| Remove Connection | Entity in network | Removes relationship |

---

### 2.4 Match Review

**Route:** `/review`

Human-in-the-loop review queue for uncertain entity matches escalated by the Entity Resolution Agent.

#### Master-Detail Layout

**Left Panel (320px) &mdash; Pending Match List:**

Each item shows:
- Confidence badge (green >= 85%, orange 60-85%, red < 60%)
- Trigger type badge: Deterministic, Embedding, LLM Review, AI Review
- Entity name, NAICS category, location
- Time since creation (e.g., "Just now", "2h ago")

Below pending items: **Resolved** section listing previously handled matches with Check (green, merged) or XCircle (red, rejected) icons.

**Right Panel &mdash; Match Detail:**

**Orphan Record Widget:**
- Name, NAICS category, location, AI confidence %, trigger type
- 5 dimension score bars:

| Dimension | Range | Visual |
|-----------|-------|--------|
| Name | 0-100% | Horizontal bar (green/orange/red) |
| Industry | 0-100% | Horizontal bar |
| Location | 0-100% | Horizontal bar |
| Commodity | 0-100% | Horizontal bar |
| Behavioral | 0-100% | Horizontal bar |

- Shared neighbors list (if any)

**Candidate Golden Records (scrollable list):**

Per candidate:
- Canonical name, golden record ID
- "AI Recommended" badge (if top-ranked by agent)
- Industry, location, source count
- Name variants (first 3, "+N more" expandable)
- Similarity bar (gradient: green >= 85%, orange 60-85%, red < 60%)
- **"Merge into this"** button (green)

**Bottom Action:**
- **"Reject &mdash; Create New Entity"** button (red) &mdash; creates a new golden record from the orphan

---

### 2.5 Connection Lineage

**Route:** `/lineage`

Audit trail and time travel for any golden record entity.

#### Entity Selector

Dropdown in the header to select from all entities that have lineage records.

#### Time Travel Slider

Horizontal timeline showing all audit events as dots. Dragging the slider reconstructs entity state at that point in time. Shows "Now" or the selected date.

#### Three-Column Layout

**Left Panel (176px) &mdash; Filters & Stats:**

Decision filters (checkboxes):
- Merged, Created, Review, No match, Restored

Trigger filters (checkboxes):
- EIN match, Embedding, LLM, New entity, Re-eval, User action

Stats:
- Total events count
- Total merges count
- Average confidence %

**Center Panel &mdash; Timeline:**

Vertical timeline of `TimelineEntry` components. Each entry shows:

- Timestamp (date + time)
- Decision badge (colored: merge = green, create = green, review = orange, no_match = gray, restore = blue)
- Trigger type badge with icon
- Confidence %
- Description text (e.g., "User accepted merge of G-05417bd3 into G-a755e3e2")
- Expandable detail sections:
  - **Evaluation Chain:** Step-by-step resolution logic with trigger tags (e.g., `strong_identity_match`, `industry_match`, `commodity_overlap_67%`)
  - **Before/After Snapshots:** Side-by-side field comparison (FieldDiff component)
  - **Dimension Scores:** Bar visualization of per-dimension scores

**Right Panel (224px) &mdash; Entity Snapshot:**

Shows the entity profile as of the selected time travel point or current state. Includes:
- Entity name and type
- Confidence score
- Name variants list
- Commodities
- "No connection state available at this date" fallback

#### Restore Functionality

Each timeline entry has a **Restore** button that:
1. Shows confirmation modal: "All changes made after this point will be undone"
2. Displays the restore datetime
3. On confirm: calls `POST /lineage/restore/{entity_id}` with the target timestamp

---

### 2.6 Connections

**Route:** `/connections`

View and manage auto-detected and manual connections.

#### Auto-Detected Connections

Source: CDC pipeline (invoices, bills, payments)

Pipeline explainer (horizontal flow):
```
QB invoice/bill -> CDC binlog -> Flink normalize -> Entity resolve -> Graph edge
```

Each connection shows:
- Entity name, RelTypeBadge (vendor/client)
- Source and date, industry, location
- Match confidence %, resolution tier, processing latency, timestamp

Footer: "N connections auto-detected in last 7 days, M total this month"

#### Manually Added Connections

Source: AddConnectionModal (from Network or Search pages)

Same display format as auto-detected, with "Added via Search / {time}" attribution.

#### Actions

- **Add Connection** button (header) &mdash; opens AddConnectionModal
- Entity Detail Sidebar with merge capability

---

### 2.7 Intuit Assist (AI Chat)

**Route:** `/assist` (full page) and side panel on other pages

Conversational AI interface for natural language queries across the business network.

#### Session History Sidebar (260px, collapsible)

- **"New chat"** button at top
- Session list sorted by recency:
  - Active session highlighted (green icon)
  - Title (auto-generated from first message, or "Untitled conversation")
  - Message count (e.g., "5 msgs")
  - Time ago (e.g., "2h ago")
- Click to switch session

#### Chat Header

- Sidebar toggle button
- Title: "Intuit Assist"
- Connection status badge: Connected (green) / Disconnected (red)
- Subtitle: session title or default description

#### Chat Messages Area

Messages render as structured blocks:

| Block Type | Rendering |
|------------|-----------|
| Content | Formatted text / markdown |
| Entities | Entity table with id, name, industry, location columns |
| Chart | Recharts visualization (bar, pie, or area chart) |
| Table | Generic table with headers and rows |
| Scores | Dimension comparison bars |
| Signals | Risk / opportunity indicator badges |
| Actions | Suggested next-step buttons |
| Followup | Suggested follow-up question chips |

Tool call events render as collapsible cards showing tool name and execution status.
Thought events render as italic reasoning steps.

#### Chat Input

- Text input with placeholder: "Ask about your network..."
- Send button (green)
- Context injection: when opened from an entity's "Ask Intuit Assist" button, the entity context is automatically included

#### Example Queries

| Query | Capabilities Used |
|-------|-------------------|
| "Show me Acme Corp's vendor network" | `query_network` &rarr; graph visualization |
| "What industries are most common?" | `aggregate_stats` &rarr; pie chart |
| "Trace the supply chain from Dell" | `traverse_supply_chain` &rarr; chain display |
| "Find shortest path between A and B" | `find_shortest_path` &rarr; path display |
| "Detect clusters in my network" | `detect_cluster` &rarr; cluster analysis |
| "What's at risk if Sysco disappears?" | `assess_risk_impact` &rarr; impact table + bar chart |
| "Compare these two entities" | `describe_entity` x2 + `compare_fields` &rarr; scores |

---

### 2.8 Infrastructure Monitor

**Route:** `/infra`

Grafana-inspired dark-themed dashboard for real-time system health monitoring.

#### Design System

| Token | Value |
|-------|-------|
| Background | `#111217` |
| Card surface | `#1E2028` |
| Card border | `#2D3139` |
| Primary text | `#D8DEE9` |
| Muted text | `#6E7681` |
| Status green | `#73BF69` |
| Status yellow | `#FADE2A` |
| Status red | `#F2495C` |

Auto-refreshes every 30 seconds with manual refresh button.

#### Service Health Panel

Grid of service cards, each showing:

| Service | Port | Extra Detail |
|---------|------|--------------|
| Backend API | 8087 | "REST API + Graph queries" |
| Conv Agent | 8082 | MCP tool count |
| Entity Agent | 8085 | MCP tool count |
| MCP Server | 8083 | &mdash; |
| Elasticsearch | 9200 | Cluster name |
| Kibana | 5601 | Version |
| OTEL Collector | 4317 | "Traces + Metrics + Logs" |

Status badges: connected (green), unknown (yellow), disconnected (red)

#### Key Metrics Panel

| Metric | Sub-metrics |
|--------|-------------|
| Entities | Total, active, merged |
| Relationships | Total, buys_from, sells_to |
| Golden Records | Total, active |
| Audit Trail | Total, pending review |

#### Data Store Panels

**Redis Cache:**
- Memory: used MB / peak MB
- Stats: Total keys, Hit rate %, Hits, Misses
- Cached key types: entity, rels, subgraph, connections, search, traverse

**Neo4j Graph:**
- Entity breakdown: total, active, merged
- Relationship breakdown: buys_from, sells_to, total

**Paimon Warehouse:**
- Warehouse path
- Table row counts: golden_records, golden_records_active, relationships, pending_resolution, pending_review, resolution_audit, connection_alerts

**Elasticsearch:**
- Cluster health (green/yellow/red), node count, active shards
- Index list: name, doc count, store size

**OTEL Collector:**
- Ports: gRPC :4317, HTTP :4318, Prometheus :8889
- Pipeline throughput: traces indexed, logs indexed

#### LLM Providers Panel

| Agent | Fields |
|-------|--------|
| Conversational Agent | Provider, Model, Connection status |
| Entity Resolution Agent | LLM Provider, LLM Model, Embedding Provider, Embedding Model, Status |

---

## 3. Backend REST API

Base path: `/api/v1`

### 3.1 Entity Endpoints

| Method | Path | Description | Parameters |
|--------|------|-------------|------------|
| `GET` | `/entities` | List entities | `q`, `industry`, `company_id` |
| `GET` | `/entities/{entity_id}` | Get entity detail | &mdash; |
| `PATCH` | `/entities/{entity_id}` | Update entity fields | Body: field values |

### 3.2 Relationship Endpoints

| Method | Path | Description | Parameters |
|--------|------|-------------|------------|
| `GET` | `/relationships` | All relationships | `company_id` |
| `GET` | `/entities/{id}/relationships` | Entity's direct relationships | &mdash; |
| `GET` | `/entities/{id}/network` | Multi-hop subgraph | `depth` (default: 2) |
| `GET` | `/entities/{id}/supply-chain` | Supply chain traversal | `direction` (upstream/downstream), `depth` (default: 5) |
| `GET` | `/entities/{a}/shortest-path/{b}` | BFS shortest path | &mdash; |
| `GET` | `/entities/{a}/common-neighbors/{b}` | Shared neighbors | `limit` (default: 20) |
| `GET` | `/entities/{id}/cluster` | Cluster detection | `max_size` (default: 20) |
| `GET` | `/entities/{id}/impact` | Risk impact analysis | `max_depth` (default: 3) |
| `GET` | `/entities/{id}/volume` | Monthly transaction volume | `company_id` |

### 3.3 Search Endpoints

| Method | Path | Description | Parameters |
|--------|------|-------------|------------|
| `GET` | `/search` | Entity search | `q`, `industry`, `sortBy` (relevance/volume/connections/confidence), `limit` (default: 50) |

Search results are cached in Redis with configurable TTL.

### 3.4 Matching Endpoints

| Method | Path | Description | Parameters |
|--------|------|-------------|------------|
| `GET` | `/matching/pending` | Pending matches | &mdash; |
| `GET` | `/matching/{id}/candidates` | Candidates for a match | &mdash; |
| `POST` | `/matching/{id}/resolve` | Accept/reject match | Body: `resolution`, `candidateGoldenId` |
| `POST` | `/matching/resolve` | Ad-hoc resolution | Body: `name`, `ein`, `city`, `state`, `industry` |

### 3.5 Connection Endpoints

| Method | Path | Description | Parameters |
|--------|------|-------------|------------|
| `GET` | `/connections/auto` | Auto-detected connections | &mdash; |
| `GET` | `/connections/manual` | Manually added connections | &mdash; |
| `POST` | `/connections` | Add new connection | Body: entity fields, `connType` |
| `POST` | `/connections/add-network` | Add existing entity to network | Body: `goldenRecordId` |
| `POST` | `/connections/remove` | Remove connection | Body: `entityId` |

### 3.6 Native Perspective Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/native/overrides` | All user field overrides |
| `GET` | `/native/overrides/{entity_id}` | Overrides for one entity |
| `PATCH` | `/native/overrides/{entity_id}` | Save field overrides |
| `DELETE` | `/native/overrides/{entity_id}/{field}` | Reset one field override |
| `GET` | `/native/merges` | All native merges |
| `POST` | `/native/merges` | Create native merge |
| `DELETE` | `/native/merges/{merge_id}` | Undo native merge |

### 3.7 Lineage Endpoints

| Method | Path | Description | Parameters |
|--------|------|-------------|------------|
| `GET` | `/lineage/entities` | Entities with audit trails | &mdash; |
| `GET` | `/lineage/trail/{entity_id}` | Audit trail for entity | `limit` (default: 100) |
| `GET` | `/lineage/snapshot/{entity_id}` | Entity state at point in time | `date` (ISO 8601) |
| `POST` | `/lineage/restore/{entity_id}` | Restore to historical state | Body: `timestamp` |

### 3.8 Infrastructure Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/infra/metrics` | Aggregate health metrics (Redis, Neo4j, Paimon, Elasticsearch, Kibana, OTEL) |

### 3.9 Alert Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/alerts` | Pending alerts |
| `POST` | `/alerts/{alert_id}/dismiss` | Acknowledge alert |

---

## 4. Conversational Agent

### 4.1 WebSocket Protocol

**Endpoint:** `WS /ws/{session_id}?user_id={user_id}`

**Client-to-Server Messages:**

| Type | Fields | Description |
|------|--------|-------------|
| `message` | `content`, `context` (optional) | User chat message |
| `clear_context` | &mdash; | Reset conversation context |
| `ping` | &mdash; | Keep-alive |

**Server-to-Client Messages:**

| Type | Fields | Description |
|------|--------|-------------|
| `session_info` | `session_id`, `title`, `message_count` | Sent on connect |
| `tool_call` | `tool`, `args`, `result` | MCP tool execution event |
| `thought` | `content` | Agent reasoning step |
| `response` | `content`, `entities`, `chart`, `table`, `scores`, `signals`, `actions`, `followup` | Final response |
| `error` | `message` | Error message |
| `context_cleared` | `session_id` | Context reset confirmation |
| `pong` | &mdash; | Keep-alive response |

### 4.2 ReAct Reasoning Loop

The agent follows a Thought-Action-Observation loop (max 8 iterations):

1. **Thought** &mdash; LLM reasons about what information is needed
2. **Action** &mdash; LLM selects an MCP tool and provides JSON arguments
3. **Observation** &mdash; Tool result (truncated to fit context) is fed back to LLM
4. **Repeat** until LLM outputs `Answer: {...}` with the final structured response

Each thought and tool call is streamed to the client in real-time via WebSocket.

### 4.3 Response Blocks

The final `Answer` is a JSON object with optional blocks:

| Field | Type | Description |
|-------|------|-------------|
| `content` | string | Main response text (markdown) |
| `entities` | array | Entity list for table rendering |
| `chart` | object | `{type: "bar"|"pie"|"area", title, data}` |
| `table` | object | `{headers, rows}` for generic tables |
| `scores` | array | Dimension comparison visualizations |
| `signals` | array | Risk/opportunity indicators |
| `actions` | array | Suggested next-step buttons |
| `followup` | array | Suggested follow-up question chips |
| `thought_steps` | int | Number of ReAct iterations used |

### 4.4 Session Management

**REST Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/sessions?user_id=` | List user's sessions |
| `POST` | `/sessions?user_id=` | Create new session |
| `GET` | `/sessions/{id}/messages` | Message history |
| `DELETE` | `/sessions/{id}` | Archive session |

**Title Generation:** On the first message, the agent auto-generates a short title (max 80 chars) for the session.

**Context Compression:** When conversation history exceeds `max_messages`, older messages are summarized by the LLM to maintain context within token limits while preserving `keep_recent` most recent messages.

---

## 5. MCP Tools

The MCP Server exposes 23 tools across 4 categories. All tools are callable by the Conversational Agent and Entity Resolution Agent via the Model Context Protocol.

### 5.1 Search Tools (8 tools)

| Tool | Parameters | Description |
|------|-----------|-------------|
| `search_entities` | `query`, `naics_filter`, `state_filter`, `city_filter`, `min_confidence`, `limit` | Hybrid search: name fuzzy match + vector similarity |
| `describe_entity` | `entity_id` | Full entity profile with direct neighbors |
| `query_network` | `entity_id`, `depth`, `direction` | Multi-hop subgraph traversal |
| `aggregate_stats` | `group_by`, `state_filter`, `naics_filter`, `min_confidence` | Group-by analytics (industry, location, etc.) |
| `search_by_relationship` | `entity_id`, `relationship_type`, `company_id` | Find entities by relationship |
| `get_company_connections` | `company_id`, `connection_type`, `sort_by`, `limit` | Vendor/customer lists with volume |
| `get_merge_history` | `entity_id`, `limit` | Resolution audit trail for entity |
| `traverse_supply_chain` | `start_entity_id`, `hops`, `max_per_hop`, `min_volume` | Multi-hop supply chain traversal |

### 5.2 Knowledge Graph Tools (7 tools)

| Tool | Parameters | Description |
|------|-----------|-------------|
| `query_ontology` | `query_type`, `code_a`, `code_b` | SPARQL queries against RDF ontology (INDUSTRY_RELATION, COMMODITY_RELATION, GEO_CONTAINMENT) |
| `check_shared_context` | `entity_a_id`, `known_counterparties` | Ontology-aware neighbor analysis |
| `batch_industry_filter` | `reference_naics`, `candidates` | Filter candidates by industry relation |
| `find_shortest_path` | `entity_a`, `entity_b` | BFS shortest connection path |
| `find_common_neighbors` | `entity_a_id`, `entity_b_id`, `limit` | Shared direct neighbors between entities |
| `detect_cluster` | `entity_id`, `max_size` | Business cluster / community detection |
| `assess_risk_impact` | `entity_id`, `max_depth` | Downstream impact analysis if entity is removed |

### 5.3 Entity Writer Tools (5 tools)

| Tool | Parameters | Description |
|------|-----------|-------------|
| `merge_into_golden_record` | `orphan_record_id`, `orphan_persona`, `golden_record_id`, `merge_reasoning`, `company_id`, `record_type` | Merge orphan into existing golden record |
| `create_golden_record` | `orphan_record_id`, `orphan_persona`, `creation_reasoning`, `company_id`, `record_type` | Create new golden record from orphan |
| `submit_for_review` | `orphan_record_id`, `orphan_persona`, `candidate_golden_record_id`, `review_reasoning`, `company_id`, `record_type` | Escalate to human review queue |
| `merge_golden_records` | `survivor_id`, `absorbed_id`, `merge_reasoning` | Merge two existing golden records |
| `log_decision` | `event_id`, `record_id`, `decision`, `target_golden_record_id`, `confidence`, `dimension_scores`, `reasoning`, `key_factors`, `evaluation_chain`, `agent_metadata` | Log resolution decision to audit trail |

### 5.4 Candidate Tools (3 tools)

| Tool | Parameters | Description |
|------|-----------|-------------|
| `find_candidates` | `orphan_persona` | Bucket-based search (EIN, phone, email anchors) + vector similarity fallback |
| `compare_fields` | `orphan_persona`, `candidate` | Deterministic field-by-field comparison with blended scoring |

---

## 6. Entity Resolution Agent

### 6.1 Resolution Pipeline

The agent uses a 3-tier escalation strategy, optimizing for cost by resolving as many cases as possible at lower tiers:

```
Orphan Record (ClassifiedPersona)
    |
    v
[Tier 1] Find Candidates (bucket search + vector)
    |
    v
[Tier 2] Compare Fields (deterministic scoring per candidate)
    |
    +-- Name Gate: Jaro-Winkler similarity < 0.70 -> disqualify candidate
    |
    v
[Tier 3] LLM Reasoning (~30% of cases reach this tier)
    |-- Shared neighbor analysis
    |-- Industry/commodity coherence
    |-- Behavioral pattern alignment
    |
    v
Decision: MERGE | NEW_ENTITY | REVIEW
```

### 6.2 Decision Types

| Decision | Condition | Action |
|----------|-----------|--------|
| `MERGE` | Confidence >= 0.85, strong signal alignment | Merge orphan into golden record via MCP writer tool |
| `NEW_ENTITY` | No candidates found OR all disqualified | Create new golden record via MCP writer tool |
| `REVIEW` | Confidence 0.40-0.85, ambiguous signals | Submit to human review queue |
| `NO_MERGE_FOUND` | All candidates disqualified after evaluation | Treated as NEW_ENTITY |

### 6.3 Scoring Model

**Dimension Scores (0.0 - 1.0 each):**

| Dimension | Signals |
|-----------|---------|
| Name | Jaro-Winkler similarity, token overlap, first-token match |
| Identity | EIN match, phone match, email domain match |
| Industry | NAICS code match (sector, subsector, full code) |
| Location | State match, city match, zip3/zip5 match |
| Commodity | Keyword overlap ratio |
| Behavioral | Volume bracket alignment, transaction pattern similarity |

**Blended Confidence:** Weighted combination of dimension scores, adjusted by sparsity (dimensions with more data get higher weight).

### 6.4 Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/resolve` | Main resolution endpoint |
| `POST` | `/api/v1/re-evaluate` | Re-evaluate after enrichment |
| `GET` | `/api/v1/health` | Health check (shows LLM/embedding provider info) |
| `GET` | `/api/v1/stats` | Runtime statistics (uptime, resolution counts) |

**Request (ResolutionRequest):**
```json
{
  "event_id": "uuid",
  "record_id": "orphan-record-id",
  "classified_persona": { ... },
  "chain_depth": 0
}
```

**Response (ResolutionResponse):**
```json
{
  "decision": "MERGE",
  "target_golden_record_id": "G-abc123",
  "confidence": 0.92,
  "dimension_scores": {
    "name": 0.95, "identity": 1.0, "industry": 0.88,
    "location": 0.90, "commodity": 0.67, "behavioral": 0.80
  },
  "reasoning": "Strong EIN match with high name similarity...",
  "evaluation_chain": ["find_candidates", "compare_fields", "merge_decision"]
}
```

---

## 7. Classification Pipeline

### 7.1 Classified Persona Model

Each business record is classified across 6 dimensions:

**Identity Dimension:**
- `normalized_name` &mdash; cleaned legal name (uppercase, trimmed)
- `name_first_token` &mdash; first word of name
- `name_tokens` &mdash; all words
- `legal_suffix` &mdash; Inc, LLC, Corp, etc.
- `ein_clean` &mdash; digits only
- `phone_digits` &mdash; digits only
- `email` &mdash; lowercased
- `email_domain` &mdash; extracted domain

**Industry Dimension:**
- `naics_code` &mdash; 6-digit NAICS code
- `naics_sector` &mdash; 2-digit sector
- `naics_subsector` &mdash; 3-digit subsector
- `commodity_keywords` &mdash; extracted from category text

**Location Dimension:**
- `state` &mdash; 2-letter code
- `city_norm` &mdash; standardized city name
- `zip3` &mdash; first 3 digits
- `zip5` &mdash; full zip

**Commodity Dimension:**
- `top_keywords` &mdash; extracted commodity keywords

**Behavioral Dimension:**
- `volume_bracket` &mdash; MICRO / SMALL / MEDIUM / LARGE
- `avg_transaction` &mdash; average transaction value
- `transaction_count` &mdash; total transactions

### 7.2 Classifiers

The Classifier Orchestrator (Java) runs 5 classifiers in sequence:

| Classifier | Input | Output |
|------------|-------|--------|
| NameNormalizer | Raw display name | Tokenized name, legal suffix |
| IdentityClassifier | EIN, phone, email fields | Cleaned identity anchors |
| IndustryClassifier | Category text | NAICS code, sector, subsector |
| CommodityExtractor | Category + line item text | Keyword list |
| LocationNormalizer | Address fields | Standardized city, state, zip |
| BehavioralClassifier | Transaction history | Volume bracket, averages |

### 7.3 Sparsity Scoring

Each dimension receives a sparsity score (0-5) indicating data completeness:

| Score | Meaning |
|-------|---------|
| 0 | No data available |
| 1-2 | Partial data |
| 3-4 | Most fields present |
| 5 | All fields populated |

The Entity Resolution Agent weights dimensions by sparsity: dimensions with more complete data contribute more to the blended confidence score. This prevents penalizing entities with legitimately sparse records (e.g., a sole proprietor with no EIN).

---

## 8. Data Pipeline

### 8.1 CDC Ingestion

9 Flink CDC jobs capture MySQL binlog changes into Paimon bronze tables:

| Job | Source Table | Paimon Table |
|-----|-------------|--------------|
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

2 Flink SQL jobs transform bronze tables into silver:

- **Aggregator 1:** Joins staged vendors/customers with companies, invoices, bills, payments
- **Aggregator 2:** Computes per-connection aggregates (volume, count, last transaction)
- **Output:** `entity_connections` table (Paimon, partial-update + aggregation merge engine)

### 8.3 Paimon Warehouse Schema

**Bronze (staged) tables:** Direct CDC mirrors of MySQL source tables

**Silver table:**
- `entity_connections` &mdash; Normalized vendor/customer edges with aggregated metrics

**Gold tables:**

| Table | Description | Key Fields |
|-------|-------------|------------|
| `golden_records` | Resolved entity records | `id`, `canonical_name`, `status` (ACTIVE/MERGED), `confidence`, `persona`, `source_records`, `bucket_keys` |
| `relationships` | Transaction edges | `source_id`, `target_id`, `type` (BUYS_FROM/SELLS_TO), `volume`, `count` |
| `pending_resolution` | Human review queue | `orphan_record_id`, `candidate_id`, `confidence`, `reviewer`, `reviewed_at` |
| `resolution_audit` | Decision audit log | `event_id`, `record_id`, `decision`, `confidence`, `dimension_scores`, `reasoning`, `before_snapshot`, `after_snapshot` |
| `entity_audit_trail` | Per-entity mutation history | `entity_id`, `timestamp`, `before_json`, `after_json`, `trigger` |
| `connection_alerts` | Anomaly alerts | `alert_id`, `entity_id`, `type`, `severity`, `message` |

### 8.4 Neo4j Graph Model

**Nodes:**
- `Entity` &mdash; Properties: `id`, `canonical_name`, `industry`, `status`, `confidence`, `location`

**Relationships:**
- `BUYS_FROM` &mdash; Properties: `volume`, `transaction_count`, `last_transaction`
- `SELLS_TO` &mdash; Properties: `volume`, `transaction_count`, `last_transaction`
- `MERGED_INTO` &mdash; Properties: `merge_date`, `reasoning`

### 8.5 Time Travel and Audit

**System-level time travel:**
- Paimon daily auto-tags (watermark-based, 365 retained)
- Query any table as-of a historical tag

**Entity-level reconstruction:**
- `entity_audit_trail` stores before/after JSON snapshots per mutation
- Linked to `resolution_audit` (the WHY) via `event_id`
- Linked to PIP-5 pipeline lineage (the FROM WHAT) via `flink_job_name` + `checkpoint_id`

**Pipeline provenance (PIP-5):**
- 4 system tables: `source_job_lineage`, `sink_job_lineage`, `source_snapshot_lineage`, `sink_snapshot_lineage`
- Tracks snapshot-to-snapshot lineage across Flink jobs

---

## 9. Observability

**Stack:** OpenTelemetry Collector &rarr; Elasticsearch &rarr; Kibana

**Instrumented Services:**
- Backend API (FastAPI auto-instrumentation)
- Conversational Agent (FastAPI auto-instrumentation)
- MCP Server
- Entity Resolution Agent

**Telemetry Types:**

| Type | Exporter | Destination |
|------|----------|-------------|
| Traces | OTLP gRPC :4317 | Elasticsearch (`qb-traces` index) |
| Logs | OTLP gRPC :4317 | Elasticsearch (`qb-logs` index) |
| Metrics | Prometheus :8889 | Prometheus scrape (Flink metrics) |

**Elasticsearch Indices:**
- `qb-traces` &mdash; Distributed traces across services
- `qb-logs` &mdash; Structured application logs

---

## 10. Non-Functional Requirements

| Requirement | Target |
|-------------|--------|
| **Scale** | 1 million businesses, 100 relationships each |
| **Search throughput** | 10 million relationship searches/month |
| **Search latency** | < 200ms (Redis-cached), < 1s (cold) |
| **Entity resolution** | Tier 1: < 100ms, Tier 2: < 500ms, Tier 3: < 5s |
| **Graph traversal** | Depth-2 subgraph in < 500ms |
| **AI chat response** | < 15s for multi-tool queries |
| **CDC latency** | Near real-time (seconds from MySQL commit to Paimon write) |
| **Availability** | Services designed for independent failure (graceful degradation) |
| **LLM provider** | Pluggable via shared `llm_providers` package (default: Gemini 2.5) |
| **Data retention** | 365-day time travel via Paimon auto-tags |
| **Audit completeness** | Every entity mutation logged with before/after snapshots |
