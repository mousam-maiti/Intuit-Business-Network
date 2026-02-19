import { apiClient } from './client';
import { config } from '@/config/env';
import { mockGetRelationships, mockGetAllRelationships, mockGetNetwork, mockGetMonthlyVolume } from './mock/handlers';

export async function getRelationships(entityId) {
  if (config.flags.useMocks) return mockGetRelationships(entityId);
  return apiClient.get(`/entities/${entityId}/relationships`);
}

export async function getAllRelationships() {
  if (config.flags.useMocks) return mockGetAllRelationships();
  return apiClient.get('/relationships');
}

export async function getNetwork(entityId, depth = 2) {
  if (config.flags.useMocks) return mockGetNetwork(entityId, depth);
  return apiClient.get(`/entities/${entityId}/network`, { params: { depth } });
}

export async function getMonthlyVolume(entityId) {
  if (config.flags.useMocks) return mockGetMonthlyVolume(entityId);
  return apiClient.get(`/entities/${entityId}/volume`);
}
