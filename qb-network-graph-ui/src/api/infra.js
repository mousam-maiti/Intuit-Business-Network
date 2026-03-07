import { apiClient } from './client';
import axios from 'axios';

export async function getInfraMetrics() {
  return apiClient.get('/infra/metrics');
}

const convAgent = axios.create({ baseURL: 'http://localhost:8082', timeout: 5000 });
convAgent.interceptors.response.use((res) => res.data, (err) => Promise.reject(err));

export async function getConvAgentHealth() {
  return convAgent.get('/health');
}

const mcp = axios.create({ baseURL: 'http://localhost:8083', timeout: 5000 });
mcp.interceptors.response.use((res) => res.data, (err) => Promise.reject(err));

export async function getMcpHealth() {
  return mcp.get('/health');
}

const entityAgent = axios.create({ baseURL: 'http://localhost:8085', timeout: 5000 });
entityAgent.interceptors.response.use((res) => res.data, (err) => Promise.reject(err));

export async function getEntityAgentHealth() {
  return entityAgent.get('/api/v1/health');
}
