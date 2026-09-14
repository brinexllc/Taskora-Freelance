// Dependency-free browser-event tests for the shared admin script.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import test from 'node:test';

const source = readFileSync(new URL('../backend/marketplace/static/admin/taskora/panel.js', import.meta.url), 'utf8');

function harness({sensitive = true, until = 0, rejectConfirmation = false} = {}) {
  const listeners = new Map(), requests = [], tasks = [], navigations = [];
  let now = 1_800_000_000_000;
  const status = () => ({textContent: '', classList: {add() {}, remove() {}}});
  function form(kind, fields) {
    const node = {kind, fields: Object.fromEntries(Object.entries(fields).map(([k, value]) => [k, {value}])),
      dataset: {confirmationUntil: String(until)}, button: {disabled: false}, status: status(),
      isConnected: true, action: '/admin/control/settings/reserves_paused/toggle/',
      matches(selector) { return kind === 'security' ? selector === '.ta-security-form' : selector.startsWith('.ta-operation-form'); },
      hasAttribute(name) { return name === 'data-confirmation-required' && sensitive; },
      querySelector(selector) {
        if (selector.startsWith('button')) return this.button;
        if (selector.includes('status')) return this.status;
        return this.fields[selector.match(/name=([^\]]+)/)?.[1]];
      },
      requestSubmit() { tasks.push(submit(this)); },
    };
    return node;
  }
  const operation = form('operation', {csrfmiddlewaretoken: 'old-token', value: 'false', idempotency_key: 'stable-operation-key'});
  const security = form('security', {csrfmiddlewaretoken: 'old-token', password: 'synthetic-password', code: '123456'});
  const dialog = {id: 'ta-security-dialog', open: false,
    showModal() { this.open = true; },
    close() { this.open = false; (listeners.get('close') || []).forEach(fn => fn({target: this})); },
  };
  class FormData {
    constructor(node) { this.values = Object.entries(node.fields).map(([key, input]) => [key, input.value]); }
    [Symbol.iterator]() { return this.values[Symbol.iterator](); }
  }
  const document = {
    addEventListener(type, fn) { listeners.set(type, [...(listeners.get(type) || []), fn]); },
    querySelector() { return operation.fields.csrfmiddlewaretoken; },
    querySelectorAll() { return [operation.fields.csrfmiddlewaretoken, security.fields.csrfmiddlewaretoken]; },
    getElementById(id) { return id === dialog.id ? dialog : null; },
  };
  runInNewContext(source, {
    document, FormData, Date: class extends Date {static now() {return now;}},
    sessionStorage: {getItem() {return null;}, removeItem() {}, setItem() {}},
    window: {location: {href: operation.action, assign(url) {navigations.push(url);}}},
    crypto: {randomUUID() {return 'synthetic-request';}}, setTimeout,
    DOMParser: class {parseFromString() {return {querySelectorAll() {return [];}};}},
    async fetch(url, options) {
      requests.push({url, options});
      if (url.includes('confirm-sensitive')) return {
        ok: !rejectConfirmation,
        async json() {return rejectConfirmation ? {detail: 'Неверный код.'} : {csrf_token: 'rotated-token', expires_in: 300};},
      };
      return {redirected: true, url: '/admin/control/settings/', async text() {return '<html></html>';}};
    },
  });
  async function submit(node) {
    for (const listener of listeners.get('submit') || []) await listener({target: node, preventDefault() {}});
  }
  return {operation, security, dialog, requests, navigations, submit,
    advance(seconds) {now += seconds * 1000;},
    async drain() {while (tasks.length) await tasks.shift();},
  };
}

test('routine switch posts immediately without a confirmation dialog', async () => {
  const h = harness({sensitive: false});
  await h.submit(h.operation);
  assert.equal(h.requests.length, 1);
  assert.equal(h.dialog.open, false);
  assert.equal(h.navigations.length, 1);
});

test('confirmation resumes the exact pending form with rotated CSRF and the same operation key', async () => {
  const h = harness();
  await h.submit(h.operation);
  assert.equal(h.requests.length, 0);
  assert.equal(h.dialog.open, true);
  await h.submit(h.security);
  await h.drain();
  assert.equal(h.requests.length, 2);
  const body = Object.fromEntries(h.requests[1].options.body);
  assert.equal(body.csrfmiddlewaretoken, 'rotated-token');
  assert.equal(body.idempotency_key, 'stable-operation-key');
  assert.equal(body.value, 'false');
  assert.equal(h.security.fields.password.value, '');
  assert.equal(h.security.fields.code.value, '');
  assert.equal(h.dialog.open, false);
});

test('existing server confirmation is reused until it expires', async () => {
  const h = harness({until: 1_800_000_300});
  await h.submit(h.operation);
  assert.equal(h.requests.length, 1);
  h.advance(301);
  await h.submit(h.operation);
  assert.equal(h.requests.length, 1);
  assert.equal(h.dialog.open, true);
});

test('cancel does not leave a pending action for a later manual confirmation', async () => {
  const h = harness();
  await h.submit(h.operation);
  h.dialog.close();
  await h.submit(h.security);
  await h.drain();
  assert.equal(h.requests.length, 1);
  assert.equal(h.navigations.length, 0);
});

test('rejected confirmation never submits the setting', async () => {
  const h = harness({rejectConfirmation: true});
  await h.submit(h.operation);
  await h.submit(h.security);
  await h.drain();
  assert.equal(h.requests.length, 1);
  assert.equal(h.security.status.textContent, 'Неверный код.');
  assert.equal(h.dialog.open, true);
  assert.equal(h.operation.fields.idempotency_key.value, 'stable-operation-key');
});
