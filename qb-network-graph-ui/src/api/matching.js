import { apiClient } from './client';

export async function getPendingMatches() {
  return apiClient.get('/matching/pending');
}

export async function resolveMatch(matchId, resolution) {
  return apiClient.post(`/matching/${matchId}/resolve`, { resolution });
}

/**
 * Run entity resolution against a manual input.
 * Returns tier (0=no match, 1=deterministic, 2=AI candidates) + results.
 */
export async function resolveEntity(input) {
  return apiClient.post('/matching/resolve', input);
}
