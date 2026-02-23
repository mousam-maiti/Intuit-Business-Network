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
    useMocks: import.meta.env.VITE_USE_MOCKS === 'true',
    enableAI: import.meta.env.VITE_ENABLE_AI_ASSIST === 'true',
    enableWebsockets: import.meta.env.VITE_ENABLE_WEBSOCKETS === 'true',
  },
  auth: {
    domain: import.meta.env.VITE_AUTH_DOMAIN || '',
    clientId: import.meta.env.VITE_AUTH_CLIENT_ID || '',
  },
  currentEntityId: import.meta.env.VITE_CURRENT_ENTITY_ID || 'e1',
};
