import { apiClient } from './client';

export async function getPendingMatches() {
  return apiClient.get('/matching/pending');
}

export async function getCandidates(matchId) {
  return apiClient.get(`/matching/${matchId}/candidates`);
}

export async function resolveMatch(matchId, resolution, candidateGoldenId = null) {
  const body = { resolution };
  if (candidateGoldenId) body.candidateGoldenId = candidateGoldenId;
  return apiClient.post(`/matching/${matchId}/resolve`, body);
}

/**
 * Run entity resolution against a manual input.
 * Returns tier (0=no match, 1=deterministic, 2=AI candidates) + results.
 */
export async function resolveEntity(input) {
  return apiClient.post('/matching/resolve', input);
}
