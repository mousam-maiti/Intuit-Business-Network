/**
 * Mock data for development. Mirrors the shape of backend API responses.
 * When VITE_USE_MOCKS=true, API modules return this data directly.
 */

// ── Entities (golden records) ────────────────────────────

export const ENTITIES = [
  { id: 'e1', name: 'Acme Construction Co', industry: '236220', city: 'Austin', state: 'TX', confidence: 0.96, vendors: 23, clients: 45, volume: 4200000, variants: ['Acme Const', 'ACME Construction'], legalStructure: 'LLC', naics: '236220', commodities: ['Building Materials', 'Concrete', 'Steel'], serviceArea: 'Central Texas', x: 400, y: 300 },
  { id: 'e2', name: 'Bob\u2019s Plumbing LLC', industry: '238220', city: 'Austin', state: 'TX', confidence: 0.94, vendors: 12, clients: 34, volume: 2300000, variants: ['Bobs Plumbing', 'BP LLC'], legalStructure: 'LLC', naics: '238220', commodities: ['Pipes', 'Fixtures', 'Water Heaters'], serviceArea: 'Travis County', x: 250, y: 180 },
  { id: 'e3', name: 'Metro Supplies Direct', industry: '423720', city: 'Dallas', state: 'TX', confidence: 0.88, vendors: 8, clients: 67, volume: 5100000, variants: ['Metro Supply', 'MSD Inc'], legalStructure: 'Corp', naics: '423720', commodities: ['Plumbing Supplies', 'HVAC Parts', 'Tools'], serviceArea: 'North Texas', x: 560, y: 200 },
  { id: 'e4', name: 'R&J Electric Services', industry: '238210', city: 'Round Rock', state: 'TX', confidence: 0.91, vendors: 15, clients: 28, volume: 1800000, variants: ['R & J Electrical', 'RJ Electric'], legalStructure: 'LLC', naics: '238210', commodities: ['Wiring', 'Panels', 'Lighting'], serviceArea: 'Williamson County', x: 300, y: 430 },
  { id: 'e5', name: 'BuildRight Inc', industry: '236220', city: 'San Antonio', state: 'TX', confidence: 0.97, vendors: 31, clients: 52, volume: 6700000, variants: ['Build Right', 'BuildRight Construction'], legalStructure: 'Inc', naics: '236220', commodities: ['Building Materials', 'Concrete', 'Roofing'], serviceArea: 'South Texas', x: 520, y: 400 },
  { id: 'e6', name: 'FastPipe Industries', industry: '423720', city: 'Houston', state: 'TX', confidence: 0.85, vendors: 6, clients: 41, volume: 3400000, variants: ['Fast Pipe', 'FastPipe Inc'], legalStructure: 'Inc', naics: '423720', commodities: ['PVC Pipe', 'Copper Pipe', 'Fittings'], serviceArea: 'Gulf Coast', x: 150, y: 330 },
  { id: 'e7', name: 'Tool Depot', industry: '423510', city: 'Austin', state: 'TX', confidence: 0.92, vendors: 4, clients: 89, volume: 7800000, variants: ['The Tool Depot', 'Tool Depot LLC'], legalStructure: 'LLC', naics: '423510', commodities: ['Power Tools', 'Hand Tools', 'Safety Equipment'], serviceArea: 'Statewide TX', x: 650, y: 320 },
  { id: 'e8', name: 'Lone Star Engineering', industry: '541330', city: 'Austin', state: 'TX', confidence: 0.89, vendors: 9, clients: 18, volume: 1200000, variants: ['LS Engineering', 'Lone Star Eng'], legalStructure: 'LLC', naics: '541330', commodities: ['Structural Design', 'Civil Plans', 'Permits'], serviceArea: 'Central Texas', x: 430, y: 140 },
  { id: 'e9', name: 'SiteWork Pros', industry: '238910', city: 'Georgetown', state: 'TX', confidence: 0.87, vendors: 11, clients: 22, volume: 980000, variants: ['Site Work Professionals'], legalStructure: 'Sole Prop', naics: '238910', commodities: ['Excavation', 'Grading', 'Demolition'], serviceArea: 'Williamson County', x: 180, y: 450 },
  { id: 'e10', name: 'TechFlow Solutions', industry: '541512', city: 'Austin', state: 'TX', confidence: 0.93, vendors: 7, clients: 35, volume: 2100000, variants: ['Tech Flow', 'TechFlow IT'], legalStructure: 'Corp', naics: '541512', commodities: ['Cloud Services', 'Networking', 'Cybersecurity'], serviceArea: 'Remote / National', x: 600, y: 140 },
];

// ── Relationships (edges: source PAYS target) ───────────

export const RELATIONSHIPS = [
  { source: 'e1', target: 'e2',  volume: 450000, count: 38, status: 'active' },
  { source: 'e1', target: 'e3',  volume: 320000, count: 24, status: 'active' },
  { source: 'e1', target: 'e4',  volume: 280000, count: 31, status: 'active' },
  { source: 'e5', target: 'e1',  volume: 890000, count: 12, status: 'active' },
  { source: 'e1', target: 'e7',  volume: 190000, count: 45, status: 'active' },
  { source: 'e1', target: 'e8',  volume: 150000, count:  8, status: 'dormant' },
  { source: 'e1', target: 'e10', volume:  95000, count:  6, status: 'active' },
  { source: 'e2', target: 'e3',  volume: 210000, count: 52, status: 'active' },
  { source: 'e2', target: 'e6',  volume: 180000, count: 36, status: 'active' },
  { source: 'e9', target: 'e2',  volume:  75000, count:  9, status: 'dormant' },
  { source: 'e3', target: 'e5',  volume: 540000, count: 67, status: 'active' },
  { source: 'e3', target: 'e7',  volume: 380000, count: 41, status: 'active' },
  { source: 'e4', target: 'e5',  volume: 340000, count: 28, status: 'active' },
  { source: 'e4', target: 'e7',  volume: 120000, count: 18, status: 'active' },
  { source: 'e9', target: 'e4',  volume:  65000, count:  7, status: 'dormant' },
  { source: 'e5', target: 'e8',  volume: 220000, count: 14, status: 'active' },
  { source: 'e6', target: 'e9',  volume:  45000, count: 11, status: 'active' },
  { source: 'e10', target: 'e8', volume: 110000, count:  5, status: 'active' },
];

// ── Transaction history (chart data) ────────────────────

export const MONTHLY_VOLUME = [
  { month: 'Sep', vol: 180 }, { month: 'Oct', vol: 220 }, { month: 'Nov', vol: 310 },
  { month: 'Dec', vol: 420 }, { month: 'Jan', vol: 480 }, { month: 'Feb', vol: 340 },
];

// ── Pending entity resolution matches ───────────────────

export const PENDING_MATCHES = [
  { id: 'm1', inputName: 'R & J Electrical', inputCategory: 'Electrical', inputLocation: 'Austin, TX', candidate: ENTITIES[3], confidence: 0.78, age: '2 hours ago', scores: { name: 0.78, industry: 0.88, location: 0.61, commodity: 0.74 }, sharedNeighbors: ['Acme Construction Co', 'BuildRight Inc', 'Tool Depot'] },
  { id: 'm2', inputName: 'Fast Pipe Supply', inputCategory: 'Plumbing Supplies', inputLocation: 'Houston, TX', candidate: ENTITIES[5], confidence: 0.67, age: '5 hours ago', scores: { name: 0.62, industry: 0.91, location: 0.72, commodity: 0.43 }, sharedNeighbors: ['Bob\u2019s Plumbing LLC'] },
  { id: 'm3', inputName: 'LS Engineering Group', inputCategory: 'Engineering', inputLocation: 'Austin, TX', candidate: ENTITIES[7], confidence: 0.71, age: '1 day ago', scores: { name: 0.69, industry: 0.95, location: 0.82, commodity: 0.38 }, sharedNeighbors: ['Acme Construction Co', 'TechFlow Solutions'] },
];

// ── Auto-detected connections (CDC pipeline resolved) ───

export const AUTO_DETECTED = [
  { id: 'a1', type: 'vendor', source: 'Bill #1047', sourceDate: 'Feb 14', entity: ENTITIES[1], resolution: 'auto', tier: 1, confidence: 0.96, latency: '32ms', time: '2 hours ago' },
  { id: 'a2', type: 'vendor', source: 'Bill #1043', sourceDate: 'Feb 12', entity: ENTITIES[6], resolution: 'auto', tier: 1, confidence: 0.94, latency: '28ms', time: '1 day ago' },
  { id: 'a3', type: 'client', source: 'Invoice #2891', sourceDate: 'Feb 11', entity: ENTITIES[4], resolution: 'auto', tier: 1, confidence: 0.97, latency: '41ms', time: '2 days ago' },
  { id: 'a4', type: 'vendor', source: 'Check #4402', sourceDate: 'Feb 8', entity: ENTITIES[9], resolution: 'auto', tier: 1, confidence: 0.91, latency: '35ms', time: '5 days ago' },
];

// ── Manually added connections ──────────────────────────

export const MANUAL_ADDED = [
  { id: 'ma1', type: 'vendor', entity: ENTITIES[2], addedVia: 'Matched to existing entity', confidence: 0.88, time: '3 days ago' },
  { id: 'ma2', type: 'client', entity: ENTITIES[8], addedVia: 'Created as new entity', confidence: null, time: '1 week ago' },
];

// ── AI tool call sequence ───────────────────────────────

export const AI_TOOLS = [
  { name: 'user_context',    label: 'Fetching your business context' },
  { name: 'knowledge_graph', label: 'Identifying competitors in your sector' },
  { name: 'network_traverse',label: 'Cross-referencing vendor networks' },
];
