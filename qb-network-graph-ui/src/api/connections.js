import { apiClient } from './client';
import { config } from '@/config/env';
import { mockGetAutoDetected, mockGetManualConnections, mockAddConnection } from './mock/handlers';

export async function getAutoDetected() {
  if (config.flags.useMocks) return mockGetAutoDetected();
  return apiClient.get('/connections/auto');
}

export async function getManualConnections() {
  if (config.flags.useMocks) return mockGetManualConnections();
  return apiClient.get('/connections/manual');
}

export async function addConnection(payload) {
  if (config.flags.useMocks) return mockAddConnection(payload);
  return apiClient.post('/connections', payload);
}
