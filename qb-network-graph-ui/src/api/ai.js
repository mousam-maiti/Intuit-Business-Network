import { apiClient } from './client';

export async function sendAIQuery(message, context = {}) {
  return apiClient.post('/ai/query', { message, context });
}
