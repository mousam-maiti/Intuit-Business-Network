/**
 * Mock data for development. Mirrors the shape of backend API responses.
 * When VITE_USE_MOCKS=true, API modules return this data directly.
 */

// ── Entities (golden records) ────────────────────────────

export const ENTITIES = [
  { id: 'e1', name: 'Acme Construction Co', ein: '74-3201587', contactName: 'John Mitchell', email: 'john@acmeconstruction.com', phone: '(512) 555-0100', website: 'https://acmeconstruction.com', industry: '236220', naics: '236220', legalStructure: 'LLC', address: '4500 Congress Ave', city: 'Austin', state: 'TX', zip: '78701', confidence: 0.96, vendors: 23, clients: 45, volume: 4200000, variants: ['Acme Const', 'ACME Construction'], commodities: ['Building Materials', 'Concrete', 'Steel'], serviceArea: 'Central Texas', x: 400, y: 300 },
  { id: 'e2', name: 'Bob\u2019s Plumbing LLC', ein: '74-2198463', contactName: 'Bob Garcia', email: 'bob@bobsplumbing.com', phone: '(512) 555-0234', website: 'https://bobsplumbing.com', industry: '238220', naics: '238220', legalStructure: 'LLC', address: '812 S Lamar Blvd', city: 'Austin', state: 'TX', zip: '78704', confidence: 0.94, vendors: 12, clients: 34, volume: 2300000, variants: ['Bobs Plumbing', 'BP LLC'], commodities: ['Pipes', 'Fixtures', 'Water Heaters'], serviceArea: 'Travis County', x: 250, y: 180 },
  { id: 'e3', name: 'Metro Supplies Direct', ein: '75-4410982', contactName: 'Karen Patel', email: 'sales@metrosupplies.com', phone: '(214) 555-0871', website: 'https://metrosuppliesdirect.com', industry: '423720', naics: '423720', legalStructure: 'Corp', address: '2200 N Stemmons Fwy', city: 'Dallas', state: 'TX', zip: '75207', confidence: 0.88, vendors: 8, clients: 67, volume: 5100000, variants: ['Metro Supply', 'MSD Inc'], commodities: ['Plumbing Supplies', 'HVAC Parts', 'Tools'], serviceArea: 'North Texas', x: 560, y: 200 },
  { id: 'e4', name: 'R&J Electric Services', ein: '74-5578123', contactName: 'Raj Desai', email: 'raj@rjelectric.com', phone: '(512) 555-0492', website: null, industry: '238210', naics: '238210', legalStructure: 'LLC', address: '105 E Main St', city: 'Round Rock', state: 'TX', zip: '78664', confidence: 0.91, vendors: 15, clients: 28, volume: 1800000, variants: ['R & J Electrical', 'RJ Electric'], commodities: ['Wiring', 'Panels', 'Lighting'], serviceArea: 'Williamson County', x: 300, y: 430 },
  { id: 'e5', name: 'BuildRight Inc', ein: '74-8892301', contactName: 'Maria Santos', email: 'msantos@buildright.com', phone: '(210) 555-0615', website: 'https://buildright.com', industry: '236220', naics: '236220', legalStructure: 'Inc', address: '7890 IH-10 West', city: 'San Antonio', state: 'TX', zip: '78230', confidence: 0.97, vendors: 31, clients: 52, volume: 6700000, variants: ['Build Right', 'BuildRight Construction'], commodities: ['Building Materials', 'Concrete', 'Roofing'], serviceArea: 'South Texas', x: 520, y: 400 },
  { id: 'e6', name: 'FastPipe Industries', ein: '76-1120984', contactName: null, email: 'info@fastpipe.com', phone: '(713) 555-0338', website: 'https://fastpipe.com', industry: '423720', naics: '423720', legalStructure: 'Inc', address: '3100 Westpark Dr', city: 'Houston', state: 'TX', zip: '77005', confidence: 0.85, vendors: 6, clients: 41, volume: 3400000, variants: ['Fast Pipe', 'FastPipe Inc'], commodities: ['PVC Pipe', 'Copper Pipe', 'Fittings'], serviceArea: 'Gulf Coast', x: 150, y: 330 },
  { id: 'e7', name: 'Tool Depot', ein: '74-6673210', contactName: 'Steve Nguyen', email: 'orders@tooldepot.com', phone: '(512) 555-0799', website: 'https://tooldepot.com', industry: '423510', naics: '423510', legalStructure: 'LLC', address: '920 W Anderson Ln', city: 'Austin', state: 'TX', zip: '78757', confidence: 0.92, vendors: 4, clients: 89, volume: 7800000, variants: ['The Tool Depot', 'Tool Depot LLC'], commodities: ['Power Tools', 'Hand Tools', 'Safety Equipment'], serviceArea: 'Statewide TX', x: 650, y: 320 },
  { id: 'e8', name: 'Lone Star Engineering', ein: '74-3398712', contactName: 'Amy Chen', email: 'achen@lonestareng.com', phone: '(512) 555-0156', website: 'https://lonestareng.com', industry: '541330', naics: '541330', legalStructure: 'LLC', address: '600 W 28th St', city: 'Austin', state: 'TX', zip: '78705', confidence: 0.89, vendors: 9, clients: 18, volume: 1200000, variants: ['LS Engineering', 'Lone Star Eng'], commodities: ['Structural Design', 'Civil Plans', 'Permits'], serviceArea: 'Central Texas', x: 430, y: 140 },
  { id: 'e9', name: 'SiteWork Pros', ein: null, contactName: 'Tom Brewer', email: 'tom@siteworkpros.com', phone: '(512) 555-0411', website: null, industry: '238910', naics: '238910', legalStructure: 'Sole Prop', address: null, city: 'Georgetown', state: 'TX', zip: '78626', confidence: 0.87, vendors: 11, clients: 22, volume: 980000, variants: ['Site Work Professionals'], commodities: ['Excavation', 'Grading', 'Demolition'], serviceArea: 'Williamson County', x: 180, y: 450 },
  { id: 'e10', name: 'TechFlow Solutions', ein: '74-9901234', contactName: 'Priya Reddy', email: 'preddy@techflow.io', phone: '(512) 555-0882', website: 'https://techflow.io', industry: '541512', naics: '541512', legalStructure: 'Corp', address: '1100 S Capital of TX Hwy', city: 'Austin', state: 'TX', zip: '78746', confidence: 0.93, vendors: 7, clients: 35, volume: 2100000, variants: ['Tech Flow', 'TechFlow IT'], commodities: ['Cloud Services', 'Networking', 'Cybersecurity'], serviceArea: 'Remote / National', x: 600, y: 140 },
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

// ── Native perspective overrides (user-specific layer) ──

export const NATIVE_OVERRIDES = {
  'e4': {
    city: 'Austin',
    commodities: ['Wiring', 'Panels', 'Lighting', 'Solar'],
    nickname: 'R&J guys',
    notes: 'Reliable, always on time',
    tags: ['preferred'],
  },
  'e6': {
    name: 'FastPipe Supply Co',
    serviceArea: 'Houston Metro',
    nickname: 'Pipe vendor',
    notes: '',
    tags: ['backup-supplier'],
  },
};

// ── Native merges (user-driven, local scope) ────────────

export const NATIVE_MERGES = [
  {
    id: 'nm1',
    sourceEntityId: 'e9',
    targetEntityId: 'e4',
    origin: 'user',
    reason: 'SiteWork Pros is a DBA of R&J Electric',
    migratedRelationships: [
      { source: 'e9', target: 'e2' },
      { source: 'e6', target: 'e9' },
    ],
    timestamp: '2026-02-15T10:30:00Z',
  },
];

// ── AI tool call sequence ───────────────────────────────

export const AI_TOOLS = [
  { name: 'user_context',    label: 'Fetching your business context' },
  { name: 'knowledge_graph', label: 'Identifying competitors in your sector' },
  { name: 'network_traverse',label: 'Cross-referencing vendor networks' },
];
