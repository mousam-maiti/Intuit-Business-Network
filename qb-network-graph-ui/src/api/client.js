import axios from 'axios';
import { config } from '@/config/env';

/**
 * Pre-configured axios instance for all API calls.
 * Base URL and interceptors are configured from environment.
 */
export const apiClient = axios.create({
  baseURL: config.api.baseUrl,
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// ── Request interceptor (auth token injection) ──────────
apiClient.interceptors.request.use(
  (req) => {
    // TODO: inject auth token from session
    // const token = getAuthToken();
    // if (token) req.headers.Authorization = `Bearer ${token}`;
    return req;
  },
  (err) => Promise.reject(err)
);

// ── Response interceptor (error normalization) ──────────
apiClient.interceptors.response.use(
  (res) => res.data,
  (err) => {
    const message =
      err.response?.data?.message ||
      err.message ||
      'An unexpected error occurred';

    console.error(`[API Error] ${err.config?.method?.toUpperCase()} ${err.config?.url}: ${message}`);
    return Promise.reject({ message, status: err.response?.status });
  }
);
