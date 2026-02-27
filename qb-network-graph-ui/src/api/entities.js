import { apiClient } from './client';
import { config } from '@/config/env';

export async function getEntities(params = {}) {
  return apiClient.get('/entities', {
    params: { company_id: config.currentEntityId, ...params }
  });
}

export async function getEntity(id) {
  return apiClient.get(`/entities/${id}`);
}

export async function updateEntity(id, payload) {
  return apiClient.patch(`/entities/${id}`, payload);
}
