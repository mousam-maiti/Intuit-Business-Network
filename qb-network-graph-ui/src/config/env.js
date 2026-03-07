/** Centralized environment configuration */
export const config = {
  api: {
    baseUrl: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080/api/v1',
    wsUrl: import.meta.env.VITE_WS_URL || 'ws://localhost:8080/ws',
    chatWsUrl: import.meta.env.VITE_CHAT_WS_URL || 'ws://localhost:8082/ws',
  },
  ui: {
    port: parseInt(import.meta.env.VITE_PORT || '3000'),
  },
  flags: {
    enableAI: import.meta.env.VITE_ENABLE_AI_ASSIST === 'true',
    enableWebsockets: import.meta.env.VITE_ENABLE_WEBSOCKETS === 'true',
  },
  auth: {
    domain: import.meta.env.VITE_AUTH_DOMAIN || '',
    clientId: import.meta.env.VITE_AUTH_CLIENT_ID || '',
  },
  currentEntityId: import.meta.env.VITE_CURRENT_ENTITY_ID || '1',
  currentEntityName: import.meta.env.VITE_CURRENT_ENTITY_NAME || 'Acme Construction Co',
};

/**
 * Real Acme Construction Co entity — used as the current user entity.
 * ID is configurable via VITE_CURRENT_ENTITY_ID (default '1').
 */
export const ACME_ENTITY = {
  id: config.currentEntityId,
  name: config.currentEntityName,
  ein: '74-3218976',
  contactName: 'Marcus Rivera',
  email: 'marcus@acmeconstruction.com',
  phone: '512-555-0101',
  website: 'www.acmeconstruction.com',
  industry: '236220',
  naics: '236220',
  legalStructure: 'LLC',
  address: '4200 S Congress Ave, Ste 300',
  city: 'Austin',
  state: 'TX',
  zip: '78745',
  confidence: 1.0,
  vendors: 48,
  clients: 14,
  volume: 0,
  variants: ['Acme Construction Co LLC'],
  commodities: ['Commercial Building'],
  serviceArea: 'Central Texas',
  x: 400,
  y: 300,
};
