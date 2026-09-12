export const API_URL = '/api';
let csrfToken = '';
let csrfRequest;

async function ensureCsrf() {
  if (csrfToken) return csrfToken;
  csrfRequest ||= fetch('/api/auth/csrf/', {
    credentials: 'same-origin',
    cache: 'no-store',
  })
    .then(async (response) => {
      if (!response.ok) throw new Error('CSRF initialization failed.');
      const payload = await response.json();
      csrfToken = payload.csrf_token;
      return csrfToken;
    })
    .finally(() => {
      csrfRequest = null;
    });
  return csrfRequest;
}

export class ApiError extends Error {
  constructor(message, status, payload) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = payload?.code;
    this.payload = payload;
    this.uncertain = !status || status >= 500;
  }
}

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
  { method = 'GET', body, signal, query } = {},
) {
  const multipart = typeof FormData !== 'undefined' && body instanceof FormData;
  const unsafe = !['GET', 'HEAD', 'OPTIONS'].includes(method.toUpperCase());
  const csrf = unsafe ? await ensureCsrf() : null;
  let response;
  try {
    response = await fetch(apiEndpoint(path, query), {
      credentials: 'same-origin',
      cache: 'no-store',
      method,
      signal,
      headers: {
        Accept: 'application/json',
        ...(body && !multipart ? { 'Content-Type': 'application/json' } : {}),
        ...(csrf ? { 'X-CSRFToken': csrf } : {}),
      },
      ...(body ? { body: multipart ? body : JSON.stringify(body) } : {}),
    });
  } catch (cause) {
    if (cause.name === 'AbortError') throw cause;
    throw new ApiError(cause.message, 0, { code: 'NETWORK_UNCERTAIN' });
  }
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
    if (response.status === 403) csrfToken = '';
    throw new ApiError(String(messages), response.status, payload);
  }
  if (payload?.csrf_token) csrfToken = payload.csrf_token;
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

export async function downloadFile(path, _sessionMarker, filename) {
  const response = await fetch(apiEndpoint(path), {
    credentials: 'same-origin',
    cache: 'no-store',
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

export function apiErrorMessage(error, t) {
  const messageKey = {
    contact_verification_required: 'contactPolicy',
    financial_operations_disabled: 'financeDisabled',
    mfa_required: 'mfaHint',
    sensitive_confirmation_required: 'sensitiveConfirmation',
    CSRF_ORIGIN_FAILED: 'sessionRenew',
    NETWORK_UNCERTAIN: 'uncertainRequest',
    API_UNAVAILABLE: 'uncertainRequest',
  }[error.code] || ({ 401: 'sessionRenew', 403: 'accessDenied', 404: 'resourceUnavailable', 429: 'requestThrottled' }[error.status]);
  return messageKey
    ? t(messageKey)
    : error.uncertain
      ? t('uncertainRequest')
      : `${t('requestFailed')}: ${error.message}`;
}
