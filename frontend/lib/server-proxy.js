import { validateEnvironment } from './environment.mjs';

export async function proxyUpstream(
  request,
  path,
  { api = true, asset = false } = {},
) {
  let configuration;

  try {
    configuration = validateEnvironment();
  } catch {
    return Response.json(
      {
        code: 'API_CONFIGURATION_ERROR',
        detail: 'API configuration is unavailable.',
      },
      { status: 503 },
    );
  }

  if (
    !Array.isArray(path) ||
    path.some(
      (part) => !/^[a-zA-Z0-9_.-]+$/.test(part) || part === '..',
    )
  ) {
    return Response.json({ detail: 'Invalid path.' }, { status: 400 });
  }

  const browserUrl = new URL(request.url);
  const unsafe = !['GET', 'HEAD', 'OPTIONS'].includes(request.method);

  // Railway/Reverse proxy может передавать request.url с внутренним hostname.
  // Для CSRF same-origin проверки используем публичный origin из forwarded headers.
  const forwardedProto = request.headers
    .get('x-forwarded-proto')
    ?.split(',')[0]
    ?.trim();

  const forwardedHost = request.headers
    .get('x-forwarded-host')
    ?.split(',')[0]
    ?.trim();

  const host = request.headers
    .get('host')
    ?.split(',')[0]
    ?.trim();

  let publicOrigin = browserUrl.origin;

  if (forwardedProto && forwardedHost) {
    publicOrigin = `${forwardedProto}://${forwardedHost}`;
  } else if (forwardedProto && host) {
    publicOrigin = `${forwardedProto}://${host}`;
  }

  const requestOrigin = request.headers.get('origin');

  if (unsafe && requestOrigin !== publicOrigin) {
    return Response.json(
      {
        code: 'CSRF_ORIGIN_FAILED',
        detail: 'Invalid request origin.',
      },
      { status: 403 },
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
        return Response.json(
          { detail: 'Unsupported upstream redirect.' },
          { status: 502 },
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
    return Response.json(
      {
        code: 'API_UNAVAILABLE',
        detail:
          'The API did not respond. Retry the same request; its result may already be recorded.',
      },
      { status: 502 },
    );
  }
}