const DEFAULT_API_URL = 'http://127.0.0.1:8000/api';

export const API_URL = (
  process.env.NEXT_PUBLIC_API_URL || DEFAULT_API_URL
).replace(/\/+$/, '');

export function apiEndpoint(path) {
  const normalizedPath = String(path).replace(/^\/+|\/+$/g, '');
  return `${API_URL}/${normalizedPath}/`;
}

export async function fetchProjects({ signal } = {}) {
  const response = await fetch(apiEndpoint('projects'), {
    headers: { Accept: 'application/json' },
    signal,
  });

  if (!response.ok) {
    throw new Error(`Taskora API returned HTTP ${response.status}`);
  }

  const payload = await response.json();
  return Array.isArray(payload) ? payload : (payload.results ?? []);
}
