import { apiClient } from './client';
import { config } from '@/config/env';
import { mockSendAIQuery } from './mock/handlers';

export async function sendAIQuery(message, context = {}) {
  if (config.flags.useMocks) return mockSendAIQuery(message);
  return apiClient.post('/ai/query', { message, context });
}
