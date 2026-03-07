import axios from 'axios';

const chatClient = axios.create({
  baseURL: 'http://localhost:8082',
  timeout: 5000,
  headers: { 'Content-Type': 'application/json' },
});
chatClient.interceptors.response.use((res) => res.data, (err) => Promise.reject(err));

export async function listSessions(userId) {
  return chatClient.get('/sessions', { params: { user_id: userId } });
}

export async function getSessionMessages(sessionId, limit = 100) {
  return chatClient.get(`/sessions/${sessionId}/messages`, { params: { limit } });
}

export async function createSession(userId) {
  return chatClient.post('/sessions', null, { params: { user_id: userId } });
}
