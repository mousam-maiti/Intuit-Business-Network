import { ENTITIES, RELATIONSHIPS, MONTHLY_VOLUME } from './data';
import { findPath } from '@/utils/graph';
import { fmt } from '@/utils/format';
import { getIndustry } from '@/constants/industries';
import { QB } from '@/constants/colors';

// ── Intent Detection ─────────────────────────────────────

const INTENT_PATTERNS = [
  { intent: 'vendor_analysis',  keywords: ['vendor', 'supplier', 'supply', 'who sells', 'buy from', 'top vendor', 'spend'] },
  { intent: 'competitor',       keywords: ['competitor', 'competing', 'rival', 'same industry', 'similar business'] },
  { intent: 'path_finding',     keywords: ['path', 'connect', 'hop', 'between', 'linked to', 'degrees', 'route'] },
  { intent: 'risk_dependency',  keywords: ['risk', 'dependency', 'critical', 'vulnerable', 'concentration', 'single point', 'reliant'] },
  { intent: 'entity_profile',   keywords: ['who is', 'tell me about', 'profile', 'describe', 'what do you know', 'details on'] },
  { intent: 'merge_advice',     keywords: ['merge', 'duplicate', 'combine', 'consolidate', 'same entity', 'overlap'] },
  { intent: 'commodity_search', keywords: ['plumbing', 'electric', 'pipe', 'tool', 'concrete', 'steel', 'hvac', 'wiring', 'roofing', 'building material', 'excavation', 'cloud', 'cyber', 'engineering'] },
];

export function detectIntent(message) {
  const lower = message.toLowerCase();

  let intent = 'general';
  for (const pattern of INTENT_PATTERNS) {
    if (pattern.keywords.some((kw) => lower.includes(kw))) {
      intent = pattern.intent;
      break;
    }
  }

  // Scan for mentioned entity names
  let mentionedEntity = null;
  for (const e of ENTITIES) {
    const names = [e.name, ...e.variants].map((n) => n.toLowerCase());
    if (names.some((n) => lower.includes(n))) {
      mentionedEntity = e;
      break;
    }
  }

  return { intent, mentionedEntity };
}

// ── Tool Sequences ───────────────────────────────────────

const TOOL_SEQUENCES = {
  vendor_analysis:  [
    { name: 'user_context',     label: 'Loading business context' },
    { name: 'knowledge_graph',  label: 'Querying vendor relationships' },
    { name: 'network_traverse', label: 'Ranking vendors by volume' },
  ],
  competitor: [
    { name: 'user_context',     label: 'Loading business context' },
    { name: 'knowledge_graph',  label: 'Identifying same-industry entities' },
    { name: 'network_traverse', label: 'Checking shared vendor overlap' },
  ],
  path_finding: [
    { name: 'user_context',    label: 'Loading business context' },
    { name: 'network_traverse', label: 'Running BFS path search' },
    { name: 'path_analysis',   label: 'Analyzing connection path' },
  ],
  entity_profile: [
    { name: 'user_context',    label: 'Loading business context' },
    { name: 'knowledge_graph', label: 'Retrieving entity profile' },
  ],
  merge_advice: [
    { name: 'user_context',    label: 'Loading business context' },
    { name: 'knowledge_graph', label: 'Scanning for duplicates' },
    { name: 'vector_search',   label: 'Comparing name variants' },
  ],
  commodity_search: [
    { name: 'user_context',    label: 'Loading business context' },
    { name: 'vector_search',   label: 'Searching commodities' },
    { name: 'knowledge_graph', label: 'Matching entities' },
  ],
  risk_dependency: [
    { name: 'user_context',     label: 'Loading business context' },
    { name: 'knowledge_graph',  label: 'Analyzing vendor concentration' },
    { name: 'network_traverse', label: 'Evaluating dependency risk' },
  ],
  general: [
    { name: 'user_context',    label: 'Loading business context' },
    { name: 'knowledge_graph', label: 'Scanning network data' },
  ],
};

export function getToolsForIntent(intent) {
  return TOOL_SEQUENCES[intent] || TOOL_SEQUENCES.general;
}

// ── Response Generators ──────────────────────────────────

function getEntityName(e) {
  return e?.name || 'your selected entity';
}

function getVendorsOf(entityId) {
  return RELATIONSHIPS
    .filter((r) => r.source === entityId)
    .sort((a, b) => b.volume - a.volume)
    .map((r) => ({ rel: r, entity: ENTITIES.find((e) => e.id === r.target) }))
    .filter((v) => v.entity);
}

function getClientsOf(entityId) {
  return RELATIONSHIPS
    .filter((r) => r.target === entityId)
    .sort((a, b) => b.volume - a.volume)
    .map((r) => ({ rel: r, entity: ENTITIES.find((e) => e.id === r.source) }))
    .filter((v) => v.entity);
}

function generateVendorAnalysis(entity) {
  const target = entity || ENTITIES[0];
  const vendors = getVendorsOf(target.id);

  if (vendors.length === 0) {
    return {
      content: `${getEntityName(target)} doesn't have any recorded vendor relationships in the network.`,
      entities: [],
      followup: 'Try searching for suppliers by commodity to find potential vendors.',
    };
  }

  const topIds = vendors.slice(0, 3).map((v) => v.entity.id);
  const totalSpend = vendors.reduce((s, v) => s + v.rel.volume, 0);
  const topVendor = vendors[0];

  return {
    content: `I found ${vendors.length} vendor${vendors.length > 1 ? 's' : ''} for ${getEntityName(target)}, with a total annual spend of ${fmt(totalSpend)}:`,
    entities: topIds,
    table: {
      headers: ['Vendor', 'Annual Spend', 'Txns', 'Status'],
      rows: vendors.slice(0, 5).map((v) => [
        v.entity.name,
        fmt(v.rel.volume),
        String(v.rel.count),
        v.rel.status === 'active' ? 'Active' : 'Inactive',
      ]),
    },
    chart: {
      type: 'bar',
      title: 'VENDOR SPEND COMPARISON',
      data: vendors.slice(0, 5).map((v) => ({
        name: v.entity.name.slice(0, 12),
        value: v.rel.volume,
      })),
    },
    actions: [{ label: 'View in network', action: 'navigate', payload: { page: 'network' } }],
    followup: `${topVendor.entity.name} is the largest vendor at ${fmt(topVendor.rel.volume)}/yr across ${topVendor.rel.count} transactions.`,
  };
}

function generateCompetitorAnalysis(entity) {
  const target = entity || ENTITIES[0];
  const sameIndustry = ENTITIES.filter(
    (e) => e.id !== target.id && e.industry === target.industry
  );

  if (sameIndustry.length === 0) {
    return {
      content: `No other entities in the network share ${getEntityName(target)}'s industry classification (${getIndustry(target.industry).label}).`,
      entities: [],
      followup: 'This could mean low competitive visibility — or that competitors haven\'t been onboarded yet.',
    };
  }

  // Check shared vendor overlap
  const targetVendorIds = new Set(getVendorsOf(target.id).map((v) => v.entity.id));
  const withOverlap = sameIndustry.map((comp) => {
    const compVendorIds = getVendorsOf(comp.id).map((v) => v.entity.id);
    const shared = compVendorIds.filter((id) => targetVendorIds.has(id));
    return { entity: comp, sharedVendors: shared.length };
  }).sort((a, b) => b.sharedVendors - a.sharedVendors);

  const topIds = withOverlap.slice(0, 3).map((c) => c.entity.id);
  const topComp = withOverlap[0];

  return {
    content: `I found ${sameIndustry.length} entit${sameIndustry.length > 1 ? 'ies' : 'y'} in the same industry (${getIndustry(target.industry).label}) as ${getEntityName(target)}:`,
    entities: topIds,
    table: {
      headers: ['Competitor', 'Shared Vendors', 'Volume', 'Location'],
      rows: withOverlap.slice(0, 5).map((c) => [
        c.entity.name,
        String(c.sharedVendors),
        fmt(c.entity.volume),
        `${c.entity.city}, ${c.entity.state}`,
      ]),
    },
    chart: {
      type: 'bar',
      title: 'COMPETITOR VOLUME COMPARISON',
      data: withOverlap.slice(0, 5).map((c) => ({
        name: c.entity.name.slice(0, 12),
        value: c.entity.volume,
      })),
    },
    actions: [{ label: 'View in network', action: 'navigate', payload: { page: 'network' } }],
    followup: topComp.sharedVendors > 0
      ? `${topComp.entity.name} shares ${topComp.sharedVendors} vendor${topComp.sharedVendors > 1 ? 's' : ''} with you — the highest overlap in your sector.`
      : `${topComp.entity.name} is the closest match by industry, operating out of ${topComp.entity.city}, ${topComp.entity.state}.`,
  };
}

function generatePathFinding(entity, mentionedEntity) {
  const start = entity || ENTITIES[0];
  const end = mentionedEntity || ENTITIES.find((e) => e.id !== start.id);

  if (!end) {
    return {
      content: 'Please specify a target entity to find a path to.',
      entities: [],
      followup: 'Try asking something like "Find path between Acme Construction and Tool Depot".',
    };
  }

  const path = findPath(RELATIONSHIPS, start.id, end.id);

  if (!path) {
    return {
      content: `No connection path found between ${getEntityName(start)} and ${getEntityName(end)} in the current network.`,
      entities: [start.id, end.id],
      followup: 'These entities may be in disconnected parts of the network.',
    };
  }

  const hops = path.length - 1;
  const pathRows = path.map((eid, idx) => {
    const e = ENTITIES.find((x) => x.id === eid);
    const eName = e ? e.name : eid;
    let rel = '';
    if (idx < path.length - 1) {
      const r = RELATIONSHIPS.find((r) =>
        (r.source === path[idx] && r.target === path[idx + 1]) ||
        (r.target === path[idx] && r.source === path[idx + 1])
      );
      rel = r ? (r.source === path[idx] ? 'Vendor → Client' : 'Client → Vendor') : 'Connected';
    }
    return [String(idx), eName, idx === 0 ? 'Start' : idx === path.length - 1 ? 'End' : rel];
  });

  return {
    content: `Found a ${hops}-hop path from ${getEntityName(start)} to ${getEntityName(end)}:`,
    entities: path,
    table: {
      headers: ['Hop', 'Entity', 'Relationship'],
      rows: pathRows,
    },
    followup: `The shortest route passes through ${hops - 1} intermediar${hops - 1 === 1 ? 'y' : 'ies'}. Each hop represents a direct business relationship.`,
  };
}

function generateEntityProfile(entity, mentionedEntity) {
  const target = mentionedEntity || entity || ENTITIES[0];
  const ind = getIndustry(target.industry);
  const vendors = getVendorsOf(target.id);
  const clients = getClientsOf(target.id);

  const maxVendors = Math.max(...ENTITIES.map((e) => getVendorsOf(e.id).length), 1);
  const maxClients = Math.max(...ENTITIES.map((e) => getClientsOf(e.id).length), 1);

  return {
    content: `Here's what I know about ${getEntityName(target)}:`,
    entities: [target.id],
    chart: {
      type: 'area',
      title: 'TRANSACTION VOLUME TREND',
      data: MONTHLY_VOLUME.map((d) => ({ name: d.month, value: d.vol })),
      config: { stroke: QB.green, fill: QB.greenLight },
    },
    scores: [
      { label: 'Confidence', value: target.confidence },
      { label: 'Vendor density', value: Math.min(vendors.length / maxVendors, 1) },
      { label: 'Client density', value: Math.min(clients.length / maxClients, 1) },
    ],
    actions: [
      { label: 'View details', action: 'select_entity', payload: { entityId: target.id } },
      { label: 'Find merge candidates', action: 'ask', payload: { query: `Find duplicates of ${target.name}` } },
    ],
    followup: [
      `Industry: ${ind.label} (${ind.sector})`,
      `Location: ${target.city}, ${target.state}`,
      `Annual volume: ${fmt(target.volume)}`,
      `Commodities: ${target.commodities.join(', ')}`,
      `Network: ${vendors.length} vendor${vendors.length !== 1 ? 's' : ''}, ${clients.length} client${clients.length !== 1 ? 's' : ''}`,
      `Confidence: ${Math.round(target.confidence * 100)}%`,
      target.serviceArea ? `Service area: ${target.serviceArea}` : null,
    ].filter(Boolean).join('\n'),
  };
}

function generateMergeAdvice(entity) {
  const target = entity || ENTITIES[0];

  // Find entities with name/variant similarity or same industry + shared commodities
  const candidates = ENTITIES.filter((e) => {
    if (e.id === target.id) return false;
    // Check name overlap
    const targetNames = [target.name, ...target.variants].map((n) => n.toLowerCase());
    const eNames = [e.name, ...e.variants].map((n) => n.toLowerCase());
    const nameOverlap = targetNames.some((tn) =>
      eNames.some((en) => en.includes(tn) || tn.includes(en))
    );
    if (nameOverlap) return true;
    // Check same industry + shared commodities
    if (e.industry === target.industry) {
      const sharedComm = e.commodities.filter((c) =>
        target.commodities.some((tc) => tc.toLowerCase() === c.toLowerCase())
      );
      if (sharedComm.length >= 2) return true;
    }
    return false;
  });

  if (candidates.length === 0) {
    return {
      content: `No potential duplicates found for ${getEntityName(target)} in the network.`,
      entities: [target.id],
      followup: 'Name variants, industry codes, and commodity overlap were all checked — this entity appears unique.',
    };
  }

  const signalsForCandidate = (c) => {
    const targetNames = [target.name, ...target.variants].map((n) => n.toLowerCase());
    const cNames = [c.name, ...c.variants].map((n) => n.toLowerCase());
    const nameMatch = targetNames.some((tn) => cNames.some((cn) => cn.includes(tn) || tn.includes(cn)));
    const industryMatch = c.industry === target.industry;
    const locationMatch = c.state === target.state;
    const sharedComm = c.commodities.filter((cm) => target.commodities.some((tc) => tc.toLowerCase() === cm.toLowerCase()));
    return [
      { icon: nameMatch ? 'positive' : 'negative', text: `Name match: ${nameMatch ? 'Yes' : 'No'}` },
      { icon: industryMatch ? 'positive' : 'negative', text: `Industry match: ${industryMatch ? 'Yes' : 'No'}` },
      { icon: locationMatch ? 'positive' : 'neutral', text: `Location match: ${locationMatch ? 'Same state' : 'Different state'}` },
      { icon: sharedComm.length >= 2 ? 'positive' : 'neutral', text: `Commodity overlap: ${sharedComm.length} shared` },
    ];
  };

  return {
    content: `I found ${candidates.length} potential duplicate${candidates.length > 1 ? 's' : ''} for ${getEntityName(target)}:`,
    entities: candidates.slice(0, 3).map((c) => c.id),
    signals: signalsForCandidate(candidates[0]),
    scores: candidates.slice(0, 3).map((c) => ({
      label: c.name,
      value: Math.round((0.6 + Math.random() * 0.3) * 100) / 100,
    })),
    actions: [{ label: 'Start merge review', action: 'navigate', payload: { page: 'review' } }],
    followup: `Review these entities and use the merge tool if they represent the same business. Merging consolidates relationships and resolves duplicate records.`,
  };
}

function generateCommoditySearch(message) {
  const lower = message.toLowerCase();
  const matches = ENTITIES.filter((e) =>
    e.commodities.some((c) => lower.includes(c.toLowerCase())) ||
    lower.split(/\s+/).some((word) =>
      word.length > 3 && e.commodities.some((c) => c.toLowerCase().includes(word))
    )
  );

  if (matches.length === 0) {
    return {
      content: 'No entities found matching that commodity search.',
      entities: [],
      followup: 'Try broader terms like "plumbing", "electric", "steel", or "tools".',
    };
  }

  const topIds = matches.slice(0, 4).map((e) => e.id);
  const commoditySet = new Set();
  matches.forEach((e) => e.commodities.forEach((c) => {
    if (lower.includes(c.toLowerCase()) || lower.split(/\s+/).some((w) => w.length > 3 && c.toLowerCase().includes(w))) {
      commoditySet.add(c);
    }
  }));
  const matchedCommodities = [...commoditySet].slice(0, 3).join(', ');

  return {
    content: `I found ${matches.length} entit${matches.length > 1 ? 'ies' : 'y'} related to ${matchedCommodities || 'your search'}:`,
    entities: topIds,
    followup: matches.length > 4
      ? `Showing the top ${topIds.length} results. ${matches.length - topIds.length} more entities also match.`
      : `These entities deal in the commodities you searched for.`,
  };
}

function generateRiskAnalysis(entity) {
  const target = entity || ENTITIES[0];
  const vendors = getVendorsOf(target.id);

  if (vendors.length === 0) {
    return {
      content: `No vendor relationships found for ${getEntityName(target)} to analyze risk.`,
      entities: [],
      followup: 'Add vendor connections to enable dependency risk analysis.',
    };
  }

  const totalSpend = vendors.reduce((s, v) => s + v.rel.volume, 0);
  const withPct = vendors.map((v) => ({
    ...v,
    pct: totalSpend > 0 ? v.rel.volume / totalSpend : 0,
  }));
  const highRisk = withPct.filter((v) => v.pct > 0.4);
  const topIds = withPct.slice(0, 3).map((v) => v.entity.id);

  const riskTable = {
    headers: ['Vendor', 'Spend', '% of Total', 'Risk Level'],
    rows: withPct.slice(0, 5).map((v) => [
      v.entity.name,
      fmt(v.rel.volume),
      Math.round(v.pct * 100) + '%',
      v.pct > 0.4 ? 'High' : v.pct > 0.2 ? 'Moderate' : 'Low',
    ]),
  };

  const riskChart = {
    type: 'pie',
    title: 'SPEND CONCENTRATION',
    data: withPct.slice(0, 5).map((v) => ({
      name: v.entity.name.slice(0, 12),
      value: v.rel.volume,
    })),
  };

  const riskSignals = [
    highRisk.length > 0
      ? { icon: 'negative', text: `${highRisk.length} vendor${highRisk.length > 1 ? 's' : ''} exceed${highRisk.length === 1 ? 's' : ''} 40% spend concentration` }
      : { icon: 'positive', text: 'No single vendor exceeds 40% of total spend' },
    vendors.length >= 5
      ? { icon: 'positive', text: `Vendor base is diversified (${vendors.length} vendors)` }
      : { icon: 'neutral', text: `Limited vendor base (${vendors.length} vendor${vendors.length > 1 ? 's' : ''})` },
    withPct.some((v) => v.rel.status !== 'active')
      ? { icon: 'neutral', text: 'Some vendor relationships are inactive' }
      : { icon: 'positive', text: 'All vendor relationships are active' },
  ];

  if (highRisk.length > 0) {
    const risky = highRisk[0];
    return {
      content: `Vendor concentration risk detected for ${getEntityName(target)}:`,
      entities: topIds,
      table: riskTable,
      chart: riskChart,
      signals: riskSignals,
      followup: `${risky.entity.name} accounts for ${Math.round(risky.pct * 100)}% of total vendor spend (${fmt(risky.rel.volume)} of ${fmt(totalSpend)}). Consider diversifying to reduce single-vendor dependency.`,
    };
  }

  return {
    content: `${getEntityName(target)}'s vendor spend is well-distributed across ${vendors.length} vendors:`,
    entities: topIds,
    table: riskTable,
    chart: riskChart,
    signals: riskSignals,
    followup: `No single vendor exceeds 40% of total spend (${fmt(totalSpend)}). Vendor concentration risk is low.`,
  };
}

function generateGeneralResponse() {
  const totalEntities = ENTITIES.length;
  const totalRels = RELATIONSHIPS.length;
  const totalVolume = RELATIONSHIPS.reduce((s, r) => s + r.volume, 0);
  const activeRels = RELATIONSHIPS.filter((r) => r.status === 'active').length;
  const industries = new Set(ENTITIES.map((e) => e.industry));

  return {
    content: `Here's a summary of your business network:`,
    entities: [],
    chart: {
      type: 'area',
      title: 'NETWORK VOLUME TREND',
      data: MONTHLY_VOLUME.map((d) => ({ name: d.month, value: d.vol })),
      config: { stroke: QB.green, fill: QB.greenLight },
    },
    followup: [
      `Entities: ${totalEntities} businesses across ${industries.size} industries`,
      `Relationships: ${totalRels} connections (${activeRels} active)`,
      `Total volume: ${fmt(totalVolume)}/yr`,
      `Top entity by volume: ${ENTITIES.reduce((a, b) => a.volume > b.volume ? a : b).name}`,
    ].join('\n'),
  };
}

// ── Main Entry Point ─────────────────────────────────────

export function generateMockResponse(message, context = {}) {
  const { selectedEntity, currentPage } = context;
  const { intent, mentionedEntity } = detectIntent(message);
  const tools = getToolsForIntent(intent);

  // The entity to reason about: mentioned in query > selected in UI > fallback
  const entity = mentionedEntity || selectedEntity || null;

  let response;
  switch (intent) {
    case 'vendor_analysis':
      response = generateVendorAnalysis(entity);
      break;
    case 'competitor':
      response = generateCompetitorAnalysis(entity);
      break;
    case 'path_finding':
      response = generatePathFinding(selectedEntity, mentionedEntity);
      break;
    case 'entity_profile':
      response = generateEntityProfile(selectedEntity, mentionedEntity);
      break;
    case 'merge_advice':
      response = generateMergeAdvice(entity);
      break;
    case 'commodity_search':
      response = generateCommoditySearch(message);
      break;
    case 'risk_dependency':
      response = generateRiskAnalysis(entity);
      break;
    default:
      response = generateGeneralResponse();
  }

  return { tools, response };
}

// ── Dynamic Suggestions ──────────────────────────────────

const PAGE_SUGGESTIONS = {
  network: [
    'Show me the full network summary',
    'Which entities have the most connections?',
    'Find entities with dormant relationships',
    'What industries are represented?',
  ],
  connections: [
    'Show recently added connections',
    'Which connections were auto-detected?',
    'Find vendors added in the last week',
    'How many connections are pending review?',
  ],
  review: [
    'Which matches have the highest confidence?',
    'Show me low-confidence matches to review',
    'How many pending matches are there?',
    'Explain the matching criteria',
  ],
  search: [
    'Find plumbing suppliers in Texas',
    'Which entities have the highest volume?',
    'Search for construction companies',
    'Find businesses with low confidence scores',
  ],
};

export function getSuggestions(selectedEntity, currentPage) {
  if (selectedEntity) {
    const name = selectedEntity.name;
    return [
      `Who are ${name}'s top vendors?`,
      `Find competitors of ${name}`,
      `What is ${name}'s risk profile?`,
      `Tell me about ${name}`,
    ];
  }

  return PAGE_SUGGESTIONS[currentPage] || [
    'Which vendors also serve my competitors?',
    'Find plumbing suppliers within 2 hops',
    'What is my most critical vendor dependency?',
    'Show me the network summary',
  ];
}
