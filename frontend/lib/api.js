const DEFAULT_API_URL = 'http://127.0.0.1:8000/api';
export const API_URL = (
  process.env.NEXT_PUBLIC_API_URL || DEFAULT_API_URL
).replace(/\/+$/, '');

export function apiEndpoint(path, query) {
  const normalized = String(path).replace(/^\/+|\/+$/g, '');
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query || {})) {
    for (const item of Array.isArray(value) ? value : [value]) {
      if (item !== '' && item != null) params.append(key, String(item));
    }
  }
  return `${API_URL}/${normalized}/${params.size ? `?${params}` : ''}`;
}

export async function apiRequest(
  path,
  { method = 'GET', body, token, signal, query } = {},
) {
  const multipart = typeof FormData !== 'undefined' && body instanceof FormData;
  const response = await fetch(apiEndpoint(path, query), {
    method,
    signal,
    headers: {
      Accept: 'application/json',
      ...(body && !multipart ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Token ${token}` } : {}),
    },
    ...(body ? { body: multipart ? body : JSON.stringify(body) } : {}),
  });
  const payload =
    response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    const messages =
      payload?.detail ||
      payload?.message ||
      Object.values(payload || {})
        .flat()
        .join(' ') ||
      `HTTP ${response.status}`;
    const error = new Error(String(messages));
    error.status = response.status;
    error.code = payload?.code;
    error.payload = payload;
    throw error;
  }
  return payload;
}

const pendingDirectoryRequests = new Map();
export function remoteRequest(path, options) {
  if (!['directory', 'catalog', 'skills'].includes(path))
    return apiRequest(path, options);
  const key = apiEndpoint(path, options.query);
  if (!pendingDirectoryRequests.has(key)) {
    const promise = apiRequest(path, { query: options.query }).finally(() =>
      pendingDirectoryRequests.delete(key),
    );
    pendingDirectoryRequests.set(key, promise);
  }
  return pendingDirectoryRequests.get(key);
}

export const fetchProjects = (options = {}) => apiRequest('projects', options);
export const fetchProfiles = (options = {}) => apiRequest('profiles', options);
export const fetchProject = (id, options = {}) =>
  apiRequest(`projects/${id}`, options);
export const createProject = (body, token) =>
  apiRequest('projects', { method: 'POST', body, token });
export const createProposal = (body, token) =>
  apiRequest('proposals', { method: 'POST', body, token });
export const register = (body) =>
  apiRequest('auth/register', { method: 'POST', body });
export const login = (body) =>
  apiRequest('auth/login', { method: 'POST', body });
export const logout = (token) =>
  apiRequest('auth/logout', { method: 'POST', token });
export const getCurrentUser = (token) => apiRequest('auth/me', { token });
export const setRole = (role, token) =>
  apiRequest('auth/role', { method: 'PUT', body: { role }, token });
export const requestPasswordReset = (identifier) =>
  apiRequest('auth/password-reset/request', {
    method: 'POST',
    body: { identifier },
  });
export const verifyPasswordReset = (identifier, code) =>
  apiRequest('auth/password-reset/verify', {
    method: 'POST',
    body: { identifier, code },
  });
export const confirmPasswordReset = (body) =>
  apiRequest('auth/password-reset/confirm', { method: 'POST', body });

export const downloadWork = (id, token, filename) =>
  downloadFile(`contracts/${id}/download`, token, filename);

export async function downloadFile(path, token, filename) {
  const response = await fetch(apiEndpoint(path), {
    headers: token ? { Authorization: `Token ${token}` } : {},
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || `HTTP ${response.status}`);
  }
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = filename || 'taskora-project';
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
