const environments = new Set(['local', 'test', 'staging', 'production']);

export function validateEnvironment(env = process.env) {
  const environment = env.TASKORA_ENV;
  if (!environments.has(environment))
    throw new Error(
      'TASKORA_ENV must explicitly be local, test, staging or production.',
    );
  const value = env.API_URL || env.NEXT_PUBLIC_API_URL;
  if (!value) throw new Error('API_URL or NEXT_PUBLIC_API_URL is required.');
  const api = new URL(value);
  if (
    !['http:', 'https:'].includes(api.protocol) ||
    api.username ||
    api.password ||
    api.search ||
    api.hash
  )
    throw new Error(
      'API URL must be an HTTP(S) URL without credentials, query or fragment.',
    );
  if (['production', 'staging'].includes(environment)) {
    if (!env.NEXT_PUBLIC_API_URL)
      throw new Error(
        'NEXT_PUBLIC_API_URL is required for production/staging builds and startup.',
      );
    const publicApi = new URL(env.NEXT_PUBLIC_API_URL);
    if (
      publicApi.protocol !== 'https:' ||
      /^(localhost|127\.|0\.0\.0\.0|\[::1\])/.test(publicApi.hostname) ||
      publicApi.username ||
      publicApi.password
    )
      throw new Error('NEXT_PUBLIC_API_URL must be a public HTTPS API URL.');
    if (api.protocol !== 'https:')
      throw new Error('API_URL must use HTTPS in production/staging.');
  }
  return { environment, apiUrl: api.href.replace(/\/+$/, '') };
}
