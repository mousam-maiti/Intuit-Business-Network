import { apiClient } from './client';

export async function getAutoDetected() {
  return apiClient.get('/connections/auto');
}

export async function getManualConnections() {
  return apiClient.get('/connections/manual');
}

export async function addConnection(payload) {
  return apiClient.post('/connections', payload);
}

export async function addExistingConnection(goldenRecordId, connType) {
  return apiClient.post('/connections/add-network', { goldenRecordId, connType });
}
