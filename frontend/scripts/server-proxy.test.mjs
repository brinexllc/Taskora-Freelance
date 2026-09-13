import assert from 'node:assert/strict';
import { afterEach, beforeEach, test } from 'node:test';
import { proxyUpstream } from '../lib/server-proxy.js';

let originalFetch;
let originalEnv;
let forwarded;
beforeEach(() => {
  originalFetch = globalThis.fetch;
  originalEnv = { ...process.env };
  process.env.TASKORA_ENV = 'production';
  process.env.API_URL = 'https://backend.example.test/api';
  process.env.NEXT_PUBLIC_API_URL = 'https://backend.example.test/api';
  process.env.CSRF_TRUSTED_ORIGINS = 'https://taskora.example.test';
  forwarded = null;
  globalThis.fetch = async (url, options) => {
    forwarded = { url, options };
    return new Response('{"ok":true}', { headers: { 'content-type': 'application/json', 'x-request-id': 'server-request-42' } });
  };
});
afterEach(() => { globalThis.fetch = originalFetch; process.env = originalEnv; });

await test('spoofed forwarded host cannot authorize a cross-origin admin mutation', async () => {
  const response = await proxyUpstream(new Request('http://internal:3000/admin/control/action/', {
    method: 'POST', headers: { origin: 'https://attacker.test', 'x-forwarded-host': 'attacker.test', 'x-forwarded-proto': 'https' }, body: 'x=1',
  }), ['admin', 'control', 'action'], { api: false });
  assert.equal(response.status, 403);
  assert.equal(forwarded, null);
  assert.equal(response.headers.get('cache-control'), 'no-store');
});

await test('configured public origin works behind Railway and preserves CSRF and request intent', async () => {
  const response = await proxyUpstream(new Request('http://internal:3000/api/admin/action/?kind=block', {
    method: 'POST', headers: { origin: 'https://taskora.example.test', cookie: 'taskora_session=synthetic',
      'x-csrftoken': 'csrf-value', 'idempotency-key': 'request-intent-01', 'x-request-id': 'client-request-01', 'x-access-reason': 'Complaint evidence review' }, body: 'body',
  }), ['admin', 'action']);
  assert.equal(response.status, 200);
  assert.equal(forwarded.url.href, 'https://backend.example.test/api/admin/action/?kind=block');
  for (const [header, value] of Object.entries({ 'idempotency-key': 'request-intent-01', 'x-request-id': 'client-request-01', 'x-csrftoken': 'csrf-value', 'x-access-reason': 'Complaint evidence review' })) {
    assert.equal(forwarded.options.headers.get(header), value);
  }
  assert.equal(response.headers.get('x-request-id'), 'server-request-42');
  assert.equal(response.headers.get('cache-control'), 'no-store');
});

await test('a null origin and internal origin are rejected in configured production', async () => {
  for (const origin of ['null', 'http://internal:3000']) {
    const response = await proxyUpstream(new Request('http://internal:3000/admin/', { method: 'POST', headers: { origin } }), ['admin'], { api: false });
    assert.equal(response.status, 403);
  }
  assert.equal(forwarded, null);
});

await test('dot segments cannot escape the permitted upstream root', async () => {
  for (const segment of ['.', '..', '%2e%2e', 'slash/escape']) {
    const response = await proxyUpstream(new Request('https://taskora.example.test/api/test/'), [segment]);
    assert.equal(response.status, 400);
  }
  assert.equal(forwarded, null);
});

await test('external redirects are rejected while admin redirects remain same-origin', async () => {
  globalThis.fetch = async () => new Response(null, { status: 302, headers: { location: 'https://attacker.test/login' } });
  let response = await proxyUpstream(new Request('https://taskora.example.test/admin/'), ['admin'], { api: false });
  assert.equal(response.status, 502);
  globalThis.fetch = async () => new Response(null, { status: 302, headers: { location: '/admin/login/?next=/admin/' } });
  response = await proxyUpstream(new Request('https://taskora.example.test/admin/'), ['admin'], { api: false });
  assert.equal(response.headers.get('location'), '/admin/login/?next=/admin/');
});

await test('upstream failure cannot be cached and never retries a mutation automatically', async () => {
  let calls = 0;
  globalThis.fetch = async () => { calls += 1; throw new Error('temporary upstream failure'); };
  const response = await proxyUpstream(new Request('https://taskora.example.test/api/admin/action/', {
    method: 'POST', headers: { origin: 'https://taskora.example.test' }, body: 'intent',
  }), ['admin', 'action']);
  assert.equal(response.status, 502);
  assert.equal(response.headers.get('cache-control'), 'no-store');
  assert.equal(calls, 1);
});
