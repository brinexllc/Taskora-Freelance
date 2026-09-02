const DEFAULT_API_URL = 'https://taskora-freelance-production.up.railway.app/api';

export const API_URL = (
  process.env.NEXT_PUBLIC_API_URL || DEFAULT_API_URL
).replace(/\/+$/, '');

export function apiEndpoint(path) {
  const normalizedPath = String(path).replace(/^\/+|\/+$/g, '');
  return `${API_URL}/${normalizedPath}/`;
}

export async function apiRequest(path, { method = 'GET', body, token, signal } = {}) {
  const response = await fetch(apiEndpoint(path), {
    method,
    signal,
    headers: {
      Accept: 'application/json',
      ...(body ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Token ${token}` } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  const payload = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    const message = payload?.detail || payload?.message || Object.values(payload || {})[0] || `HTTP ${response.status}`;
    throw new Error(Array.isArray(message) ? message[0] : message);
  }
  return payload;
}

export async function fetchProjects({ signal } = {}) {
  const payload = await apiRequest('projects', { signal });
  return Array.isArray(payload) ? payload : (payload.results ?? []);
}

export const fetchProfiles = ({ signal } = {}) => apiRequest('profiles', { signal });

export const fetchProject = (id, { signal } = {}) => apiRequest(`projects/${id}`, { signal });
export const createProject = (body, token) => apiRequest('projects', { method: 'POST', body, token });
export const createProposal = (body, token) => apiRequest('proposals', { method: 'POST', body, token });

export const register = (body) => apiRequest('auth/register', { method: 'POST', body });
export const login = (body) => apiRequest('auth/login', { method: 'POST', body });
export const logout = (token) => apiRequest('auth/logout', { method: 'POST', token });
export const getCurrentUser = (token) => apiRequest('auth/me', { token });
export const setRole = (role, token) => apiRequest('auth/role', { method: 'PUT', body: { role }, token });
export const requestPasswordReset = (email) => apiRequest('auth/password-reset/request', { method: 'POST', body: { email } });
export const verifyPasswordReset = (email, code) => apiRequest('auth/password-reset/verify', { method: 'POST', body: { email, code } });
export const confirmPasswordReset = (body) => apiRequest('auth/password-reset/confirm', { method: 'POST', body });
