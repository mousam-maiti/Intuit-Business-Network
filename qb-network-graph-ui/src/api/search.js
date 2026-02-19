import { apiClient } from './client';
import { config } from '@/config/env';
import { mockSearchEntities } from './mock/handlers';

export async function searchEntities(query, filters = {}) {
  if (config.flags.useMocks) return mockSearchEntities(query, filters);
  return apiClient.get('/search', { params: { q: query, ...filters } });
}
