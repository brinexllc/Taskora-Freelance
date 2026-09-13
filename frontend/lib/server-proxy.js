import { validateEnvironment } from './environment.mjs';

function proxyError(body, status) {
  return Response.json(body, {
    status,
    headers: { 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' },
  });
}

function trustedOrigins() {
  const origins = new Set();
  for (const entry of (process.env.CSRF_TRUSTED_ORIGINS || '').split(',')) {
    try {
      const url = new URL(entry.trim());
      if (['http:', 'https:'].includes(url.protocol) && !url.username && !url.password &&
          !url.search && !url.hash && url.pathname === '/') origins.add(url.origin);
    } catch { /* Invalid configuration never expands the allowlist. */ }
  }
  return origins;
}

export async function proxyUpstream(
  request,
  path,
  { api = true, asset = false } = {},
) {
  let configuration;

  try {
    configuration = validateEnvironment();
  } catch {
    return proxyError(
      {
        code: 'API_CONFIGURATION_ERROR',
        detail: 'API configuration is unavailable.',
      },
      503,
    );
  }

  if (
    !Array.isArray(path) ||
    path.some(
      (part) => typeof part !== 'string' || !/^[a-zA-Z0-9_.-]+$/.test(part) || part === '..' || part === '.',
    )
  ) {
    return proxyError({ detail: 'Invalid path.' }, 400);
  }

  const browserUrl = new URL(request.url);
  const unsafe = !['GET', 'HEAD', 'OPTIONS'].includes(request.method);

  // Public Railway origins are explicitly configured, never inferred from
  // caller-controlled forwarded headers. Django still validates CSRF tokens.
  const allowedOrigins = trustedOrigins();
  if (allowedOrigins.size === 0 || ['local', 'test'].includes(configuration.environment)) {
    allowedOrigins.add(browserUrl.origin);
  }
  const requestOrigin = request.headers.get('origin');

  if (unsafe && !allowedOrigins.has(requestOrigin)) {
    return proxyError(
      {
        code: 'CSRF_ORIGIN_FAILED',
        detail: 'Invalid request origin.',
      },
      403,
    );
  }

  const root = api
    ? configuration.apiUrl
    : configuration.apiUrl.replace(/\/api$/, '');

  const target = new URL(
    `${root}/${path.map(encodeURIComponent).join('/')}${asset ? '' : '/'}`,
  );

  target.search = browserUrl.search;

  const headers = new Headers();

  for (const key of [
    'accept',
    'content-type',
    'cookie',
    'x-csrftoken',
    'origin',
    'referer',
    'user-agent',
    'idempotency-key',
    'x-idempotency-key',
    'x-request-id',
    'x-access-reason',
  ]) {
    const value = request.headers.get(key);
    if (value) {
      headers.set(key, value);
    }
  }

  try {
    const upstream = await fetch(target, {
      method: request.method,
      headers,
      redirect: 'manual',
      signal: AbortSignal.timeout(45000),
      ...(unsafe ? { body: await request.arrayBuffer() } : {}),
    });

    const output = new Headers({
      'Cache-Control': asset ? 'public, max-age=3600' : 'no-store',
      'X-Content-Type-Options': 'nosniff',
    });

    for (const key of [
      'content-type',
      'content-disposition',
      'retry-after',
      'content-security-policy',
      'x-frame-options',
      'referrer-policy',
      'x-request-id',
    ]) {
      const value = upstream.headers.get(key);
      if (value) {
        output.set(key, value);
      }
    }

    for (const cookie of upstream.headers.getSetCookie()) {
      output.append('set-cookie', cookie);
    }

    const location = upstream.headers.get('location');

    if (location) {
      const redirect = new URL(location, target);

      if (
        redirect.origin !== target.origin ||
        !/^\/(admin|api|static\/admin)(\/|$)/.test(redirect.pathname)
      ) {
        return proxyError(
          { detail: 'Unsupported upstream redirect.' },
          502,
        );
      }

      output.set(
        'location',
        `${redirect.pathname}${redirect.search}${redirect.hash}`,
      );
    }

    return new Response(upstream.body, {
      status: upstream.status,
      headers: output,
    });
  } catch {
    return proxyError(
      {
        code: 'API_UNAVAILABLE',
        detail:
          'The API did not respond. Retry the same request; its result may already be recorded.',
      },
      502,
    );
  }
}
