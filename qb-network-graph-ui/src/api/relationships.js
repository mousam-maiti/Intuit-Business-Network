import { apiClient } from './client';
import { config } from '@/config/env';

export async function getRelationships(entityId) {
  return apiClient.get(`/entities/${entityId}/relationships`);
}

export async function getAllRelationships(params = {}) {
  return apiClient.get('/relationships', {
    params: { company_id: config.currentEntityId, ...params }
  });
}

export async function getNetwork(entityId, depth = 2) {
  return apiClient.get(`/entities/${entityId}/network`, { params: { depth } });
}

export async function getSupplyChain(entityId, direction = 'upstream', depth = 5) {
  return apiClient.get(`/entities/${entityId}/supply-chain`, {
    params: { direction, depth }
  });
}

export async function getMonthlyVolume(entityId) {
  return apiClient.get(`/entities/${entityId}/volume`, {
    params: { company_id: config.currentEntityId }
  });
}
