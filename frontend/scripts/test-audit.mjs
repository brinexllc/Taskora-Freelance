import assert from 'node:assert/strict';
import { validateEnvironment } from '../lib/environment.mjs';
import {
  beginOperation,
  readOperation,
  completeOperation,
} from '../lib/pending-operation.js';

assert.throws(() => validateEnvironment({}), /TASKORA_ENV/);
assert.throws(
  () =>
    validateEnvironment({
      TASKORA_ENV: 'production',
      API_URL: 'https://api.example.test/api',
    }),
  /NEXT_PUBLIC_API_URL/,
);
assert.throws(
  () =>
    validateEnvironment({
      TASKORA_ENV: 'production',
      NEXT_PUBLIC_API_URL: 'http://127.0.0.1:8000/api',
    }),
  /HTTPS/,
);
assert.throws(
  () =>
    validateEnvironment({
      TASKORA_ENV: 'staging',
      NEXT_PUBLIC_API_URL: 'https://localhost/api',
    }),
  /HTTPS/,
);
assert.equal(
  validateEnvironment({
    TASKORA_ENV: 'local',
    API_URL: 'http://127.0.0.1:8000/api/',
  }).apiUrl,
  'http://127.0.0.1:8000/api',
);

const stored = new Map();
globalThis.window = {};
globalThis.localStorage = {
  getItem: (key) => stored.get(key) ?? null,
  setItem: (key, value) => stored.set(key, value),
  removeItem: (key) => stored.delete(key),
};
const original = beginOperation(10, 'wallet/withdraw', {
  amount: '1000.00',
  recipient: 4,
  confirmed: true,
});
// A lost response plus module/page reload must not change either amount or key.
const freshModule = await import('../lib/pending-operation.js?reloaded');
assert.deepEqual(
  freshModule.beginOperation(10, 'wallet/withdraw', {
    amount: '2000.00',
    recipient: 5,
  }),
  original,
);
assert.deepEqual(readOperation(10, 'wallet/withdraw'), original);
assert.equal(readOperation(11, 'wallet/withdraw'), null);
assert.equal(readOperation(10, 'payments/checkout'), null);
completeOperation(10, 'wallet/withdraw');
assert.equal(readOperation(10, 'wallet/withdraw'), null);
localStorage.setItem = () => {
  throw new Error('Storage denied');
};
assert.throws(
  () => beginOperation(10, 'wallet/withdraw', { amount: '1000' }),
  /Storage denied/,
);
console.log(
  'PASS: environment guards and reload-safe financial request intent (11 assertions).',
);
