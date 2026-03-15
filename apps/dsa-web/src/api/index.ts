import axios from 'axios';
import { API_BASE_URL } from '../utils/constants';
import { attachParsedApiError } from './error';

/**
 * In-memory JWT access token storage.
 * Using memory (not localStorage) for better security — tokens are cleared on tab close.
 */
let _accessToken: string | null = null;

export function setAccessToken(token: string | null) {
  _accessToken = token;
}

export function getAccessToken(): string | null {
  return _accessToken;
}

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  withCredentials: true, // For HttpOnly cookies (refresh token + legacy session)
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor: attach JWT Bearer token when available
apiClient.interceptors.request.use((config) => {
  const token = _accessToken;
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor: handle 401 with token refresh
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // Attempt JWT refresh on 401 (only once, skip for auth endpoints)
    if (
      error.response?.status === 401 &&
      !originalRequest._retry &&
      _accessToken &&
      !originalRequest.url?.includes('/auth/')
    ) {
      originalRequest._retry = true;
      try {
        const { data } = await apiClient.post('/api/v1/auth/refresh');
        _accessToken = data.access_token;
        originalRequest.headers.Authorization = `Bearer ${data.access_token}`;
        return apiClient(originalRequest);
      } catch {
        // Refresh failed — clear token and redirect to login
        _accessToken = null;
      }
    }

    // Redirect to login for 401 (both legacy and SaaS mode)
    if (error.response?.status === 401) {
      const path = window.location.pathname + window.location.search;
      const basePath = import.meta.env.BASE_URL.replace(/\/$/, '');
      if (!path.startsWith(`${basePath}/login`)) {
        const redirect = encodeURIComponent(path);
        window.location.assign(`${basePath}/login?redirect=${redirect}`);
      }
    }

    attachParsedApiError(error);
    return Promise.reject(error);
  }
);

export default apiClient;
