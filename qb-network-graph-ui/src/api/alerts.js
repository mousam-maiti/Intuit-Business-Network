import { apiClient } from './client';

export async function getAlerts() {
  return apiClient.get('/alerts');
}

export async function dismissAlert(alertId) {
  return apiClient.post(`/alerts/${alertId}/dismiss`);
}
