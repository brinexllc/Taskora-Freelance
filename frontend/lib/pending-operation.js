// Deliberately stores only request intent, never an authentication credential.
// The account-scoped record survives reloads and must exist before POST begins.
const storageKey = (userId, action) => `taskora-operation:${userId}:${action}`;
export function readOperation(userId, action) {
  if (typeof window === 'undefined') return null;
  try {
    return JSON.parse(
      localStorage.getItem(storageKey(userId, action)) || 'null',
    );
  } catch {
    return null;
  }
}
export function beginOperation(userId, action, body) {
  const previous = readOperation(userId, action);
  if (previous) return previous;
  const operation = { ...body, idempotency_key: crypto.randomUUID() };
  // If storage fails, abort before sending: a reload-safe retry is mandatory.
  localStorage.setItem(storageKey(userId, action), JSON.stringify(operation));
  return operation;
}
export function completeOperation(userId, action) {
  localStorage.removeItem(storageKey(userId, action));
}
