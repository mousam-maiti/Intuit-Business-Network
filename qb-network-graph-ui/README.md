# QuickBooks Business Network Graph — Frontend

Interactive React UI for the QuickBooks Business Network Graph system design.
Demonstrates all four use cases: network visualization, search, connection management,
and entity resolution — backed by a mock API layer that mirrors the real backend contract.

## Quick Start

```bash
npm install
npm run dev       # → http://localhost:3000
npm run build     # production build → dist/
npm run preview   # preview production build
```

## Architecture

```
src/
├── main.jsx                    Entry point
├── router.jsx                  React Router config with lazy-loaded routes
│
├── config/
│   ├── env.js                  Centralized env config (API URL, WS URL, feature flags)
│   └── routes.js               Route definitions + id↔path mapping
│
├── constants/
│   ├── colors.js               QB brand tokens as JS object (for inline styles)
│   └── industries.js           NAICS code → label/sector/color lookup
│
├── utils/
│   ├── format.js               Currency/percentage formatters
│   └── graph.js                BFS path finding, relationship type derivation
│
├── api/
│   ├── client.js               Axios instance with interceptors
│   ├── websocket.js            WebSocket manager (real + mock fallback)
│   ├── entities.js             Entity CRUD
│   ├── relationships.js        Relationships + network queries
│   ├── matching.js             Entity resolution endpoints
│   ├── search.js               Text search / typeahead
│   ├── connections.js          Auto-detected + manual connections
│   ├── ai.js                   AI/Assist queries
│   └── mock/
│       ├── data.js             All mock datasets (entities, relationships, etc.)
│       ├── handlers.js         Mock API responses with latency simulation
│       └── wsHandlers.js       MockWebSocket for real-time event simulation
│
├── hooks/
│   └── useAIChat.js            Shared AI chat state (messages, tool animation)
│
├── styles/
│   ├── variables.css           CSS custom properties (QB brand tokens)
│   ├── global.css              Reset, base styles, animations
│   └── components.css          Shared component classes (widget, sidebar, modal, etc.)
│
└── components/
    ├── AppLayout.jsx           Shell: sidebar + topbar + AI panel + <Outlet>
    ├── shared/
    │   ├── Widget.jsx          Card container
    │   ├── ScoreBar.jsx        Confidence score bar
    │   ├── RelTypeBadge.jsx    Vendor/client badge
    │   ├── AIChatMessages.jsx  AI chat message list with suggestions
    │   ├── AIChatInput.jsx     AI chat input bar
    │   ├── AIPanel.jsx         Slide-over AI panel
    │   ├── MergeNotification.jsx  Entity merge toast
    │   └── index.js            Barrel export
    └── pages/
        ├── Dashboard/          KPI cards, charts, hub entities, pending actions
        ├── Network/            SVG graph + entity sidebar + path finding
        │   └── components/
        │       └── NetworkGraph.jsx   Interactive SVG graph renderer
        ├── Search/             Typeahead + faceted search + sort
        ├── Connections/        Auto-detected (CDC) + manual add with entity resolution
        ├── Review/             Tier 2 match review queue (merge/reject)
        └── Assist/             Full-page AI chat (Intuit Assist)
```

## Environment Variables

Copy `.env.example` → `.env` and customize:

| Variable | Default | Purpose |
|----------|---------|---------|
| `VITE_API_BASE_URL` | `http://localhost:8080/api/v1` | Backend REST API |
| `VITE_WS_URL` | `ws://localhost:8080/ws` | WebSocket endpoint |
| `VITE_PORT` | `3000` | Dev server port |
| `VITE_USE_MOCKS` | `true` | Toggle mock vs real API |
| `VITE_CURRENT_ENTITY_ID` | `e1` | Current user's entity (dev) |

## Mock API Layer

Every API module checks `config.flags.useMocks`:
- **true** → returns mock data from `api/mock/handlers.js` with simulated latency
- **false** → makes real HTTP calls via the axios client

Mock handlers mirror the exact response shape of the backend, so switching from
mock → real requires zero component changes. The WebSocket manager uses
`MockWebSocket` when mocks are enabled, simulating entity merge and edge weight
update events.

## Key Design Decisions

**Edge convention**: `source` PAYS `target`. If your entity is the source,
the target is your *vendor*. `getRelType(rel, entityId)` derives this.

**Routing**: React Router v6 with `useOutletContext` to pass shared state
(selected entity, privacy toggle, AI chat) from the layout shell to pages.

**Code splitting**: All 6 pages are lazy-loaded via `React.lazy()` + `Suspense`.
Vendor libraries (React, Recharts, Lucide) are split into separate chunks.

**Styling**: Hybrid approach — CSS custom properties for brand tokens, Tailwind
utilities for layout, component-level CSS classes in `components.css` for
structural elements (sidebar, topbar, modal, graph container).

## Pages

| Page | Route | System Design Concept Demonstrated |
|------|-------|------------------------------------|
| Dashboard | `/` | Network health KPIs, entity resolution stats |
| Network | `/network` | SVG graph with edge filters, path finding (BFS <30ms) |
| Search | `/search` | ES-style typeahead (<30ms), faceted filtering, sort |
| Connections | `/connections` | CDC auto-detection + manual add with two-tier entity resolution |
| Review | `/review` | Tier 2 AI persona match review queue |
| Assist | `/assist` | LLM agent + 6 MCP tool servers, streamed responses |
