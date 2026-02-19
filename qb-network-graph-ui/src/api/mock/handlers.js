import {
  ENTITIES, RELATIONSHIPS, MONTHLY_VOLUME, PENDING_MATCHES,
  AUTO_DETECTED, MANUAL_ADDED, AI_TOOLS,
} from './data';

/** Simulate network latency */
const delay = (ms = 200) => new Promise((r) => setTimeout(r, ms));

// ── Entities ────────────────────────────────────────────

export async function mockGetEntities(params = {}) {
  await delay(100);
  let results = [...ENTITIES];
  if (params.q) {
    const q = params.q.toLowerCase();
    results = results.filter((e) =>
      e.name.toLowerCase().includes(q) ||
      e.variants.some((v) => v.toLowerCase().includes(q))
    );
  }
  if (params.industry) {
    results = results.filter((e) => e.industry === params.industry);
  }
  return { data: results, total: results.length };
}

export async function mockGetEntity(id) {
  await delay(50);
  const entity = ENTITIES.find((e) => e.id === id);
  if (!entity) throw new Error('Entity not found');
  return { data: entity };
}

// ── Relationships ───────────────────────────────────────

export async function mockGetRelationships(entityId) {
  await delay(80);
  const rels = RELATIONSHIPS.filter(
    (r) => r.source === entityId || r.target === entityId
  );
  return { data: rels };
}

export async function mockGetAllRelationships() {
  await delay(80);
  return { data: RELATIONSHIPS };
}

// ── Network / Graph ─────────────────────────────────────

export async function mockGetNetwork(entityId, depth = 2) {
  await delay(150);
  const ids = new Set([entityId]);
  const walkDepth = (currentIds, d) => {
    if (d <= 0) return;
    const nextIds = new Set();
    RELATIONSHIPS.forEach((r) => {
      if (currentIds.has(r.source)) { ids.add(r.target); nextIds.add(r.target); }
      if (currentIds.has(r.target)) { ids.add(r.source); nextIds.add(r.source); }
    });
    walkDepth(nextIds, d - 1);
  };
  walkDepth(new Set([entityId]), depth);
  const entities = ENTITIES.filter((e) => ids.has(e.id));
  const relationships = RELATIONSHIPS.filter((r) => ids.has(r.source) && ids.has(r.target));
  return { data: { entities, relationships } };
}

// ── Transaction Volume ──────────────────────────────────

export async function mockGetMonthlyVolume(entityId) {
  await delay(60);
  return { data: MONTHLY_VOLUME };
}

// ── Entity Resolution / Matching ────────────────────────

export async function mockGetPendingMatches() {
  await delay(120);
  return { data: PENDING_MATCHES };
}

export async function mockResolveMatch(matchId, resolution) {
  await delay(300);
  return { data: { matchId, resolution, resolvedAt: new Date().toISOString() } };
}

export async function mockResolveEntity(input) {
  await delay(800);
  // Simulate Tier 1 deterministic match for names containing 'bob'
  if (input.name?.toLowerCase().includes('bob') || (input.ein && input.ein.length >= 9)) {
    return {
      data: {
        tier: 1,
        match: ENTITIES[1],
        confidence: 0.91,
        latency: input.ein?.length >= 9 ? '12ms' : '47ms',
        scores: { name: 0.91, industry: 0.85, location: 0.97, commodity: 0.72 },
      },
    };
  }
  // Simulate Tier 2 candidates for other inputs
  if (input.name?.length > 3) {
    return {
      data: {
        tier: 2,
        candidates: [
          { entity: ENTITIES[3], confidence: 0.73, scores: { name: 0.68, industry: 0.88, location: 0.71, commodity: 0.65 } },
          { entity: ENTITIES[7], confidence: 0.61, scores: { name: 0.55, industry: 0.72, location: 0.82, commodity: 0.35 } },
        ],
        latency: '340ms',
      },
    };
  }
  return { data: { tier: 0, match: null } };
}

// ── Connections (CDC auto-detected + manual) ────────────

export async function mockGetAutoDetected() {
  await delay(80);
  return { data: AUTO_DETECTED };
}

export async function mockGetManualConnections() {
  await delay(80);
  return { data: [...MANUAL_ADDED] };
}

export async function mockAddConnection(payload) {
  await delay(400);
  const newConn = {
    id: 'ma-' + Date.now(),
    type: payload.connType,
    entity: payload.entity || {
      id: 'e-' + Date.now(),
      name: payload.name || 'New entity',
      industry: '236220',
      city: payload.city || 'Unknown',
      state: payload.state || 'TX',
      vendors: 0, clients: 0, volume: 0, variants: [],
    },
    addedVia: payload.entity ? 'Matched to existing entity' : 'Created as new entity',
    confidence: payload.entity ? 0.91 : null,
    time: 'Just now',
  };
  return { data: newConn };
}

// ── Search ──────────────────────────────────────────────

export async function mockSearchEntities(query, filters = {}) {
  await delay(100);
  let results = [...ENTITIES];
  if (query) {
    const q = query.toLowerCase();
    results = results.filter((e) =>
      e.name.toLowerCase().includes(q) ||
      e.commodities.some((c) => c.toLowerCase().includes(q))
    );
  }
  if (filters.industry) {
    results = results.filter((e) => e.industry === filters.industry);
  }
  if (filters.sortBy === 'volume') results.sort((a, b) => b.volume - a.volume);
  if (filters.sortBy === 'confidence') results.sort((a, b) => b.confidence - a.confidence);
  if (filters.sortBy === 'connections') results.sort((a, b) => (b.vendors + b.clients) - (a.vendors + a.clients));
  return { data: results, total: results.length };
}

// ── AI / Assist ─────────────────────────────────────────

export async function mockSendAIQuery(message) {
  // Returns tool call sequence, then final response
  const tools = [...AI_TOOLS];
  return {
    data: {
      tools,
      response: {
        content: 'I found 3 vendors that also serve businesses competing with you:',
        entities: ['e3', 'e6', 'e7'],
        followup: 'Metro Supplies Direct has the highest overlap \u2014 they serve both you and BuildRight Inc across 4 commodity categories.',
      },
    },
  };
}
