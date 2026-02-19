import { apiClient } from './client';
import { config } from '@/config/env';
import { mockGetEntities, mockGetEntity } from './mock/handlers';

export async function getEntities(params) {
  if (config.flags.useMocks) return mockGetEntities(params);
  return apiClient.get('/entities', { params });
}

export async function getEntity(id) {
  if (config.flags.useMocks) return mockGetEntity(id);
  return apiClient.get(`/entities/${id}`);
}

export async function updateEntity(id, payload) {
  if (config.flags.useMocks) return { data: { ...payload, id } };
  return apiClient.patch(`/entities/${id}`, payload);
}
