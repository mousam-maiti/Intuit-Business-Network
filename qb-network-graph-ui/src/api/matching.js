import { apiClient } from './client';
import { config } from '@/config/env';
import { mockGetPendingMatches, mockResolveMatch, mockResolveEntity } from './mock/handlers';

export async function getPendingMatches() {
  if (config.flags.useMocks) return mockGetPendingMatches();
  return apiClient.get('/matching/pending');
}

export async function resolveMatch(matchId, resolution) {
  if (config.flags.useMocks) return mockResolveMatch(matchId, resolution);
  return apiClient.post(`/matching/${matchId}/resolve`, { resolution });
}

/**
 * Run entity resolution against a manual input.
 * Returns tier (0=no match, 1=deterministic, 2=AI candidates) + results.
 */
export async function resolveEntity(input) {
  if (config.flags.useMocks) return mockResolveEntity(input);
  return apiClient.post('/matching/resolve', input);
}
