import { apiClient } from './client';

export async function searchEntities(query, filters = {}) {
  return apiClient.get('/search', { params: { q: query, ...filters } });
}
