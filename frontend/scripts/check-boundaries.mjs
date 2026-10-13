import assert from 'node:assert/strict';
import { ApiError, request, safeSource } from '../src/api.ts';

for (const value of ['javascript:alert(1)', 'data:text/html,<script>1</script>', 'file:///C:/secret.txt', 'ftp://example.org/a', 'http://user:password@example.org/', '/relative-path', 'not a url']) {
  assert.equal(safeSource(value), null, `reject unsafe or incomplete source: ${value}`);
}
assert.equal(safeSource('https://example.org/trace/123'), 'https://example.org/trace/123');
assert.equal(safeSource('http://127.0.0.1:16686/trace/123'), 'http://127.0.0.1:16686/trace/123');
console.log('Source-link boundaries: 9 cases passed.');

const previousFetch = globalThis.fetch;
try {
  globalThis.fetch = async () => new Response(JSON.stringify({ error: 'The investigation snapshot changed.' }), { status: 409, headers: { 'Content-Type': 'application/json' } });
  await assert.rejects(request('/api', '/cases/test/compare', undefined, {}), (error) => error instanceof ApiError && error.status === 409 && error.message === 'The investigation snapshot changed.');
  console.log('API stale-state boundary: HTTP 409 and message retained; no network request made.');
} finally { globalThis.fetch = previousFetch; }
