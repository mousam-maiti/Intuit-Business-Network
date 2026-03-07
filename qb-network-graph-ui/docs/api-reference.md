# QB Network Graph API Reference

## Overview

The QB Network Graph API provides entity resolution, relationship traversal, native perspective overrides, and AI-assisted network analysis for the QuickBooks business network.

### Base URL

```
http://localhost:8080/api/v1
```

### Authentication

All requests require a Bearer JWT token in the `Authorization` header:

```
Authorization: Bearer <token>
```

> **Note:** Auth is not yet implemented. The client interceptor in `src/api/client.js` has a placeholder for token injection.

### Response Envelope

All successful responses wrap data in a standard envelope:

```json
{ "data": <T> }
```

List endpoints include a `total` count:

```json
{ "data": [...], "total": 10 }
```

### Error Format

```json
{
  "message": "Entity not found",
  "status": 404
}
```

### Content Type

All requests and responses use `application/json`.

### Timeout

The client is configured with a **15-second** timeout (`src/api/client.js`).

---

## REST Endpoints

### Entities

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/entities` | List all entities |
| `GET` | `/entities/{id}` | Get a single entity |
| `PATCH` | `/entities/{id}` | Partially update an entity |

#### `GET /entities`

Returns all golden-record entities with optional filtering.

**Query Parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `q` | string | Text search across name and variants |
| `industry` | string | Filter by NAICS industry code |

**Response:**

```json
{
  "data": [
    {
      "id": "e1",
      "name": "Acme Construction Co",
      "ein": "74-3201587",
      "contactName": "John Mitchell",
      "email": "john@acmeconstruction.com",
      "phone": "(512) 555-0100",
      "website": "https://acmeconstruction.com",
      "industry": "236220",
      "naics": "236220",
      "legalStructure": "LLC",
      "address": "4500 Congress Ave",
      "city": "Austin",
      "state": "TX",
      "zip": "78701",
      "confidence": 0.96,
      "vendors": 23,
      "clients": 45,
      "volume": 4200000,
      "variants": ["Acme Const", "ACME Construction"],
      "commodities": ["Building Materials", "Concrete", "Steel"],
      "serviceArea": "Central Texas",
      "x": 400,
      "y": 300
    }
  ],
  "total": 10
}
```

**Error Codes:** `401` Unauthorized

#### `GET /entities/{id}`

**Path Parameters:** `id` (string, required) - Entity ID

**Response:** `{ "data": Entity }`

**Error Codes:** `404` Entity not found

#### `PATCH /entities/{id}`

**Path Parameters:** `id` (string, required) - Entity ID

**Request Body:** Any subset of Entity fields.

```json
{
  "contactName": "Jane Mitchell",
  "phone": "(512) 555-0200"
}
```

**Response:** `{ "data": Entity }`

**Error Codes:** `404` Entity not found

---

### Relationships

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/relationships` | List all relationships |
| `GET` | `/entities/{id}/relationships` | Get relationships for an entity |
| `GET` | `/entities/{id}/network` | Get ego network subgraph |
| `GET` | `/entities/{id}/volume` | Get monthly transaction volume |

#### `GET /relationships`

Returns every edge in the network graph.

**Response:**

```json
{
  "data": [
    {
      "source": "e1",
      "target": "e2",
      "volume": 450000,
      "count": 38,
      "status": "active"
    }
  ]
}
```

#### `GET /entities/{id}/relationships`

Returns all edges where the entity is either source (payer) or target (payee).

**Path Parameters:** `id` (string, required) - Entity ID

**Response:** `{ "data": [Relationship] }`

#### `GET /entities/{id}/network`

BFS traversal from a given entity up to `depth` hops. Returns all reachable entities and the relationships between them.

**Path Parameters:** `id` (string, required) - Entity ID

**Query Parameters:**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `depth` | integer | 2 | Number of hops to traverse (1-5) |

**Response:**

```json
{
  "data": {
    "entities": [Entity, ...],
    "relationships": [Relationship, ...]
  }
}
```

#### `GET /entities/{id}/volume`

Returns monthly transaction volume time-series data for charts.

**Path Parameters:** `id` (string, required) - Entity ID

**Response:**

```json
{
  "data": [
    { "month": "Sep", "vol": 180 },
    { "month": "Oct", "vol": 220 },
    { "month": "Nov", "vol": 310 },
    { "month": "Dec", "vol": 420 },
    { "month": "Jan", "vol": 480 },
    { "month": "Feb", "vol": 340 }
  ]
}
```

---

### Search

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/search` | Search entities |

#### `GET /search`

Full-text search across entity names and commodities with faceted filtering and sorting.

**Query Parameters:**

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `q` | string | Yes | Search query |
| `industry` | string | No | Filter by NAICS code |
| `sortBy` | string | No | `volume`, `confidence`, or `connections` |

**Response:**

```json
{
  "data": [Entity, ...],
  "total": 3
}
```

**Error Codes:** `400` Missing query parameter

---

### Matching

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/matching/pending` | List pending matches |
| `POST` | `/matching/{id}/resolve` | Resolve a pending match |
| `POST` | `/matching/resolve` | Run ad-hoc entity resolution |

#### `GET /matching/pending`

Returns entity resolution matches awaiting human review.

**Response:**

```json
{
  "data": [
    {
      "id": "m1",
      "inputName": "R & J Electrical",
      "inputCategory": "Electrical",
      "inputLocation": "Austin, TX",
      "candidate": { Entity },
      "confidence": 0.78,
      "age": "2 hours ago",
      "scores": {
        "name": 0.78,
        "industry": 0.88,
        "location": 0.61,
        "commodity": 0.74
      },
      "sharedNeighbors": ["Acme Construction Co", "BuildRight Inc", "Tool Depot"]
    }
  ]
}
```

#### `POST /matching/{id}/resolve`

Accept or reject a pending entity resolution match.

**Path Parameters:** `id` (string, required) - Match ID

**Request Body:**

```json
{
  "resolution": "accept"
}
```

`resolution` must be `"accept"` or `"reject"`.

**Response:**

```json
{
  "data": {
    "matchId": "m1",
    "resolution": "accept",
    "resolvedAt": "2026-02-21T15:30:00.000Z"
  }
}
```

**Error Codes:** `404` Match not found

#### `POST /matching/resolve`

Run entity resolution against arbitrary input. Returns a tiered result:

- **Tier 0** - No match found
- **Tier 1** - Deterministic match (EIN lookup or high-confidence name)
- **Tier 2** - AI-ranked candidates requiring manual selection

**Request Body:**

```json
{
  "name": "Bob's Plumbing",
  "ein": "74-2198463",
  "industry": "238220",
  "city": "Austin",
  "state": "TX"
}
```

**Response (Tier 1):**

```json
{
  "data": {
    "tier": 1,
    "match": { Entity },
    "confidence": 0.91,
    "latency": "12ms",
    "scores": {
      "name": 0.91,
      "industry": 0.85,
      "location": 0.97,
      "commodity": 0.72
    }
  }
}
```

**Response (Tier 2):**

```json
{
  "data": {
    "tier": 2,
    "candidates": [
      {
        "entity": { Entity },
        "confidence": 0.73,
        "scores": { "name": 0.68, "industry": 0.88, "location": 0.71, "commodity": 0.65 }
      }
    ],
    "latency": "340ms"
  }
}
```

**Response (Tier 0):**

```json
{
  "data": {
    "tier": 0,
    "match": null
  }
}
```

---

### Connections

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/connections/auto` | List auto-detected connections |
| `GET` | `/connections/manual` | List manually added connections |
| `POST` | `/connections` | Add a manual connection |

#### `GET /connections/auto`

Returns connections automatically resolved by the CDC pipeline.

**Response:**

```json
{
  "data": [
    {
      "id": "a1",
      "type": "vendor",
      "source": "Bill #1047",
      "sourceDate": "Feb 14",
      "entity": { Entity },
      "resolution": "auto",
      "tier": 1,
      "confidence": 0.96,
      "latency": "32ms",
      "time": "2 hours ago"
    }
  ]
}
```

#### `GET /connections/manual`

Returns connections added by users through manual matching or entity creation.

**Response:**

```json
{
  "data": [
    {
      "id": "ma1",
      "type": "vendor",
      "entity": { Entity },
      "addedVia": "Matched to existing entity",
      "confidence": 0.88,
      "time": "3 days ago"
    }
  ]
}
```

#### `POST /connections`

Add a manual connection. Either link an existing entity or create a new one.

**Request Body (link existing):**

```json
{
  "connType": "vendor",
  "entity": { Entity }
}
```

**Request Body (create new):**

```json
{
  "connType": "client",
  "name": "New Vendor LLC",
  "city": "Austin",
  "state": "TX"
}
```

**Response (201):**

```json
{
  "data": {
    "id": "ma-1708981234567",
    "type": "vendor",
    "entity": { Entity },
    "addedVia": "Matched to existing entity",
    "confidence": 0.91,
    "time": "Just now"
  }
}
```

---

### Native Perspective

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/native/overrides` | List all native overrides |
| `GET` | `/native/overrides/{id}` | Get overrides for an entity |
| `PATCH` | `/native/overrides/{id}` | Save overrides for an entity |
| `DELETE` | `/native/overrides/{id}/{field}` | Delete a single field override |
| `GET` | `/native/merges` | List native merges |
| `POST` | `/native/merges` | Create a native merge |
| `DELETE` | `/native/merges/{id}` | Undo a native merge |

#### `GET /native/overrides`

Returns all user-specific attribute overrides keyed by entity ID.

**Response:**

```json
{
  "data": {
    "e4": {
      "city": "Austin",
      "commodities": ["Wiring", "Panels", "Lighting", "Solar"],
      "nickname": "R&J guys",
      "notes": "Reliable, always on time",
      "tags": ["preferred"]
    },
    "e6": {
      "name": "FastPipe Supply Co",
      "serviceArea": "Houston Metro",
      "nickname": "Pipe vendor",
      "notes": "",
      "tags": ["backup-supplier"]
    }
  }
}
```

#### `GET /native/overrides/{id}`

**Path Parameters:** `id` (string, required) - Entity ID

**Response:** `{ "data": OverrideFields | null }`

Returns `null` if no overrides exist for this entity.

#### `PATCH /native/overrides/{id}`

Merges the provided fields with any existing overrides for this entity.

**Path Parameters:** `id` (string, required) - Entity ID

**Request Body:**

```json
{
  "nickname": "Our plumber",
  "tags": ["preferred", "local"]
}
```

**Response:** `{ "data": OverrideFields }` (full merged result)

#### `DELETE /native/overrides/{id}/{field}`

Removes a single field override, resetting it to the global value.

**Path Parameters:**
- `id` (string, required) - Entity ID
- `field` (string, required) - Field name to remove

**Response:** `{ "data": OverrideFields | null }` (remaining overrides, or `null` if none left)

#### `GET /native/merges`

Returns all user-driven entity merges.

**Response:**

```json
{
  "data": [
    {
      "id": "nm1",
      "sourceEntityId": "e9",
      "targetEntityId": "e4",
      "origin": "user",
      "reason": "SiteWork Pros is a DBA of R&J Electric",
      "migratedRelationships": [
        { "source": "e9", "target": "e2" },
        { "source": "e6", "target": "e9" }
      ],
      "timestamp": "2026-02-15T10:30:00Z"
    }
  ]
}
```

#### `POST /native/merges`

Create a user-driven native merge. The source entity is absorbed into the target entity and its relationships are migrated.

**Request Body:**

```json
{
  "sourceEntityId": "e9",
  "targetEntityId": "e4",
  "reason": "SiteWork Pros is a DBA of R&J Electric",
  "migratedRelationships": [
    { "source": "e9", "target": "e2" },
    { "source": "e6", "target": "e9" }
  ]
}
```

**Response (201):** `{ "data": NativeMerge }`

#### `DELETE /native/merges/{id}`

Undo a native merge, restoring the source entity and its original relationships.

**Path Parameters:** `id` (string, required) - Merge ID

**Response:** `{ "data": NativeMerge }` (the undone merge)

**Error Codes:** `404` Merge not found

---

### AI / Assist (REST Fallback)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/ai/query` | Send an AI assist query |

> **Prefer WebSocket:** Use the `ws://localhost:8080/ws/assist` channel for streaming tool calls. This REST endpoint is a synchronous fallback.

#### `POST /ai/query`

**Request Body:**

```json
{
  "message": "Who are Acme Construction's top vendors?",
  "context": {
    "selectedEntity": { Entity },
    "currentPage": "network"
  }
}
```

**Response:**

```json
{
  "data": {
    "tools": [
      { "name": "user_context", "label": "Loading business context" },
      { "name": "knowledge_graph", "label": "Querying vendor relationships" },
      { "name": "network_traverse", "label": "Ranking vendors by volume" }
    ],
    "response": {
      "content": "I found 6 vendors for Acme Construction Co, with a total annual spend of $1,485,000:",
      "entities": ["e2", "e3", "e4"],
      "table": {
        "headers": ["Vendor", "Annual Spend", "Txns", "Status"],
        "rows": [
          ["Bob's Plumbing LLC", "$450,000", "38", "Active"],
          ["Metro Supplies Direct", "$320,000", "24", "Active"]
        ]
      },
      "chart": {
        "type": "bar",
        "title": "VENDOR SPEND COMPARISON",
        "data": [
          { "name": "Bob's Plumb", "value": 450000 },
          { "name": "Metro Suppl", "value": 320000 }
        ]
      },
      "actions": [
        { "label": "View in network", "action": "navigate", "payload": { "page": "network" } }
      ],
      "followup": "Bob's Plumbing LLC is the largest vendor at $450,000/yr across 38 transactions."
    }
  }
}
```

---

## WebSocket Protocol

### Channel 1: Real-time Events

```
ws://localhost:8080/ws
```

Server-push only channel for CDC pipeline events. The client connects on startup and subscribes to event types via the `WebSocketManager` (`src/api/websocket.js`).

**Reconnection strategy:** Exponential back-off starting at 2 seconds, max 5 attempts.

**Wire format:** JSON messages with `type` and `payload` fields:

```json
{
  "type": "<event_type>",
  "payload": { ... }
}
```

#### Event: `connection.detected`

A new entity connection was auto-resolved by the CDC pipeline.

```json
{
  "type": "connection.detected",
  "payload": {
    "id": "a-1708981234567",
    "connType": "vendor",
    "source": "Bill #1083",
    "sourceDate": "Feb 14",
    "entity": { Entity },
    "tier": 1,
    "confidence": 0.93,
    "latency": "35ms",
    "time": "Just now"
  }
}
```

#### Event: `edge.updated`

Transaction volume changed on an existing relationship.

```json
{
  "type": "edge.updated",
  "payload": {
    "source": "e1",
    "target": "e3",
    "volumeDelta": 5420
  }
}
```

#### Event: `match.pending`

A new entity resolution match requires human review.

```json
{
  "type": "match.pending",
  "payload": {
    "id": "m-1708981234567",
    "inputName": "New Vendor 42",
    "confidence": 0.72
  }
}
```

---

### Channel 2: Intuit Assist Chat

```
ws://localhost:8080/ws/assist
```

Bidirectional streaming channel for AI-assisted network queries. Replaces the HTTP `POST /ai/query` endpoint for real-time tool call delivery.

#### Protocol Flow

```
Client                    Server
  |--- query ------------>|
  |<--- tool_start -------|   (per tool, streamed as each begins)
  |<--- tool_start -------|
  |<--- tool_start -------|
  |<--- response ---------|   (final structured result)
```

On error, the server sends an `error` message instead of `response`.

#### Client Message: `query`

```json
{
  "type": "query",
  "message": "Who are Acme Construction's top vendors?",
  "context": {
    "selectedEntity": { Entity },
    "currentPage": "network"
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | `"query"` | Yes | Message type discriminator |
| `message` | string | Yes | Natural language query |
| `context.selectedEntity` | Entity | No | Currently selected entity in the UI |
| `context.currentPage` | string | No | Current page: `network`, `connections`, `review`, `search`, `assist` |

#### Server Message: `tool_start`

Sent once per tool as the server begins executing it. The UI renders these as a step-by-step progress indicator.

```json
{
  "type": "tool_start",
  "tool": {
    "name": "knowledge_graph",
    "label": "Querying vendor relationships"
  }
}
```

**Tool names:** `user_context`, `knowledge_graph`, `network_traverse`, `path_analysis`, `vector_search`

**Tool sequences by intent:**

| Intent | Tools |
|--------|-------|
| `vendor_analysis` | `user_context` > `knowledge_graph` > `network_traverse` |
| `competitor` | `user_context` > `knowledge_graph` > `network_traverse` |
| `path_finding` | `user_context` > `network_traverse` > `path_analysis` |
| `entity_profile` | `user_context` > `knowledge_graph` |
| `merge_advice` | `user_context` > `knowledge_graph` > `vector_search` |
| `commodity_search` | `user_context` > `vector_search` > `knowledge_graph` |
| `risk_dependency` | `user_context` > `knowledge_graph` > `network_traverse` |
| `general` | `user_context` > `knowledge_graph` |

#### Server Message: `response`

Final structured response sent after all tools complete.

```json
{
  "type": "response",
  "data": {
    "content": "I found 6 vendors for Acme Construction Co...",
    "entities": ["e2", "e3", "e4"],
    "table": { "headers": [...], "rows": [...] },
    "chart": { "type": "bar", "title": "...", "data": [...] },
    "scores": [{ "label": "Confidence", "value": 0.96 }],
    "signals": [{ "icon": "negative", "text": "1 vendor exceeds 40% spend" }],
    "actions": [{ "label": "View in network", "action": "navigate", "payload": {} }],
    "followup": "Bob's Plumbing LLC is the largest vendor..."
  }
}
```

#### Server Message: `error`

```json
{
  "type": "error",
  "message": "Failed to process query"
}
```

---

## Data Models

### Entity

Golden-record business entity in the network graph.

| Field | Type | Required | Nullable | Description |
|-------|------|----------|----------|-------------|
| `id` | string | Yes | No | Unique identifier |
| `name` | string | Yes | No | Legal business name |
| `ein` | string | No | Yes | Employer Identification Number |
| `contactName` | string | No | Yes | Primary contact name |
| `email` | string | No | Yes | Contact email |
| `phone` | string | No | Yes | Contact phone |
| `website` | string (uri) | No | Yes | Business website |
| `industry` | string | Yes | No | NAICS industry code |
| `naics` | string | Yes | No | NAICS code (same as industry) |
| `legalStructure` | string | No | No | `LLC`, `Corp`, `Inc`, or `Sole Prop` |
| `address` | string | No | Yes | Street address |
| `city` | string | Yes | No | City |
| `state` | string | Yes | No | State (2-letter code) |
| `zip` | string | No | Yes | ZIP code |
| `confidence` | float | Yes | No | Resolution confidence (0-1) |
| `vendors` | integer | Yes | No | Vendor relationship count |
| `clients` | integer | Yes | No | Client relationship count |
| `volume` | number | Yes | No | Annual transaction volume (USD) |
| `variants` | string[] | Yes | No | Known name variants |
| `commodities` | string[] | Yes | No | Product/service categories |
| `serviceArea` | string | No | Yes | Geographic service region |
| `x` | number | No | No | Graph layout x-coordinate |
| `y` | number | No | No | Graph layout y-coordinate |

### Relationship

Directed edge representing a payer-to-payee transaction relationship.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `source` | string | Yes | Payer entity ID |
| `target` | string | Yes | Payee entity ID |
| `volume` | number | Yes | Annual transaction volume (USD) |
| `count` | integer | Yes | Number of transactions |
| `status` | string | Yes | `active` or `dormant` |

### MonthlyVolume

Single data point in a transaction volume time series.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `month` | string | Yes | Abbreviated month name |
| `vol` | number | Yes | Volume value (thousands USD) |

### MatchScores

Component scores for entity resolution matching.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | float | Yes | Name similarity score (0-1) |
| `industry` | float | Yes | Industry match score (0-1) |
| `location` | float | Yes | Location proximity score (0-1) |
| `commodity` | float | Yes | Commodity overlap score (0-1) |

### PendingMatch

Entity resolution match awaiting human review.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | Match identifier |
| `inputName` | string | Yes | Raw name from incoming document |
| `inputCategory` | string | Yes | Category from incoming document |
| `inputLocation` | string | Yes | Location from incoming document |
| `candidate` | Entity | Yes | Best-match candidate entity |
| `confidence` | float | Yes | Overall confidence (0-1) |
| `age` | string | Yes | Human-readable age |
| `scores` | MatchScores | Yes | Component match scores |
| `sharedNeighbors` | string[] | Yes | Names of shared network neighbors |

### EntityResolutionResult

Discriminated union by `tier` field:

- **Tier 0**: `{ tier: 0, match: null }` - No match
- **Tier 1**: `{ tier: 1, match: Entity, confidence, latency, scores }` - Deterministic match
- **Tier 2**: `{ tier: 2, candidates: [{entity, confidence, scores}], latency }` - AI-ranked candidates

### AutoDetected

Connection auto-resolved by the CDC pipeline.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | Connection identifier |
| `type` | string | Yes | `vendor` or `client` |
| `source` | string | Yes | Source document reference |
| `sourceDate` | string | Yes | Date from source document |
| `entity` | Entity | Yes | Resolved entity |
| `resolution` | string | Yes | Always `auto` |
| `tier` | integer | Yes | Always `1` (auto-detected are tier 1) |
| `confidence` | float | Yes | Resolution confidence (0-1) |
| `latency` | string | Yes | Resolution latency |
| `time` | string | Yes | Human-readable timestamp |

### ManualConnection

Connection added by a user through matching or entity creation.

| Field | Type | Required | Nullable | Description |
|-------|------|----------|----------|-------------|
| `id` | string | Yes | No | Connection identifier |
| `type` | string | Yes | No | `vendor` or `client` |
| `entity` | Entity | Yes | No | Linked entity |
| `addedVia` | string | Yes | No | `Matched to existing entity` or `Created as new entity` |
| `confidence` | float | No | Yes | `null` when created as new entity |
| `time` | string | Yes | No | Human-readable timestamp |

### OverrideFields

User-specific attribute overrides for the native perspective layer. Includes any subset of editable entity fields plus native-only fields.

**Editable fields:** `name`, `ein`, `contactName`, `email`, `phone`, `website`, `industry`, `naics`, `legalStructure`, `address`, `city`, `state`, `zip`, `commodities`, `serviceArea`, `variants`

**Native-only fields:**

| Field | Type | Description |
|-------|------|-------------|
| `nickname` | string | User-defined short name |
| `notes` | string | Free-text notes |
| `tags` | string[] | User-defined tags |

### NativeMerge

Record of a user-driven entity merge.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | Merge identifier |
| `sourceEntityId` | string | Yes | Entity absorbed (merged away) |
| `targetEntityId` | string | Yes | Entity that survives |
| `origin` | string | Yes | `user` or `system` |
| `reason` | string | Yes | User-provided merge reason |
| `migratedRelationships` | `{source, target}[]` | Yes | Relationships moved to target |
| `timestamp` | string (ISO 8601) | Yes | When the merge occurred |

### AIResponseData

Full AI response including tool call sequence and structured result.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `tools` | `{name, label}[]` | Yes | Tool calls executed |
| `response.content` | string | Yes | Main response text |
| `response.entities` | string[] | No | Referenced entity IDs |
| `response.table` | AITable | No | Tabular data |
| `response.chart` | AIChart | No | Chart configuration |
| `response.scores` | AIScore[] | No | Score indicators |
| `response.signals` | AISignal[] | No | Signal indicators |
| `response.actions` | AIAction[] | No | Actionable buttons |
| `response.followup` | string | No | Follow-up text |

### AITable

| Field | Type | Description |
|-------|------|-------------|
| `headers` | string[] | Column headers |
| `rows` | string[][] | Row data (each row is an array of cell strings) |

### AIChart

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | `bar`, `area`, or `pie` |
| `title` | string | Chart title |
| `data` | `{name, value}[]` | Data points |
| `config` | object | Optional styling: `{ stroke, fill }` |

### AIScore

| Field | Type | Description |
|-------|------|-------------|
| `label` | string | Score label |
| `value` | float | Score value (0-1) |

### AISignal

| Field | Type | Description |
|-------|------|-------------|
| `icon` | string | `positive`, `negative`, or `neutral` |
| `text` | string | Signal description |

### AIAction

| Field | Type | Description |
|-------|------|-------------|
| `label` | string | Button label |
| `action` | string | `navigate`, `select_entity`, or `ask` |
| `payload` | object | Action-specific payload |

---

## Environment Configuration

These environment variables configure the UI client. Set them in `.env` or `.env.local`.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `VITE_API_BASE_URL` | string | `http://localhost:8080/api/v1` | REST API base URL |
| `VITE_WS_URL` | string | `ws://localhost:8080/ws` | WebSocket URL for real-time events |
| `VITE_PORT` | integer | `3000` | Vite dev server port |
| `VITE_USE_MOCKS` | boolean | `false` | Enable mock data mode (bypass API) |
| `VITE_ENABLE_AI_ASSIST` | boolean | `false` | Enable AI assist panel and page |
| `VITE_ENABLE_WEBSOCKETS` | boolean | `false` | Enable real-time WebSocket events |
| `VITE_AUTH_DOMAIN` | string | `""` | Auth provider domain |
| `VITE_AUTH_CLIENT_ID` | string | `""` | Auth provider client ID |
| `VITE_CURRENT_ENTITY_ID` | string | `e1` | Default "current user" entity ID |
