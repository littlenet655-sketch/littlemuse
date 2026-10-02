import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

process.env.EXPO_PUBLIC_API_BASE_URL = 'https://backend.test.invalid';

import { ApiError, apiRequest, setUnauthorizedHandler, withoutUnauthorizedHandler } from '../src/api/client';

function stubFetch(impl: (url: string, init: RequestInit) => Promise<unknown>): { calls: () => number } {
  let calls = 0;
  (globalThis as unknown as Record<string, unknown>).fetch = async (url: unknown, init?: RequestInit) => {
    calls += 1;
    return impl(String(url), init ?? {});
  };
  return { calls: () => calls };
}

function jsonResponse(status: number, payload: unknown): unknown {
  return { ok: status >= 200 && status < 300, status, json: async () => payload };
}

describe('caller cancellation combined with timeout', () => {
  it('caller abort rejects as cancelled with no retry', async () => {
    const stub = stubFetch((_url, init) => new Promise((_resolve, reject) => {
      init.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
    }));
    setUnauthorizedHandler(null);
    const controller = new AbortController();
    const pending = apiRequest('/api/mobile/v1/me', { signal: controller.signal });
    controller.abort();
    const err = await pending.then(() => null, (error: unknown) => error);
    assert.ok(err instanceof ApiError);
    assert.equal((err as ApiError).code, 'request_cancelled');
    assert.equal(stub.calls(), 1);
  });

  it('pre-aborted signal never reaches the network', async () => {
    const stub = stubFetch(async () => jsonResponse(200, { ok: true }));
    setUnauthorizedHandler(null);
    const controller = new AbortController();
    controller.abort();
    const err = await apiRequest('/api/mobile/v1/me', { signal: controller.signal }).then(() => null, (error: unknown) => error);
    assert.ok(err instanceof ApiError);
    assert.equal((err as ApiError).code, 'request_cancelled');
    assert.equal(stub.calls(), 0);
  });

  it('timeout without caller abort keeps the timeout error', async () => {
    // A fetch implementation that honors abort, like the real one.
    stubFetch((_url, init) => new Promise((_resolve, reject) => {
      init.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
    }));
    setUnauthorizedHandler(null);
    const err = await apiRequest('/api/mobile/v1/auth/login', { method: 'POST', timeoutMs: 20 }).then(() => null, (error: unknown) => error);
    assert.ok(err instanceof ApiError);
    assert.equal((err as ApiError).code, 'request_timeout');
  });

  it('forwards the abort to the underlying fetch signal', async () => {
    let seenAborted: boolean | null = null;
    stubFetch((_url, init) => {
      seenAborted = init.signal?.aborted ?? null;
      return Promise.resolve(jsonResponse(200, { ok: true }));
    });
    setUnauthorizedHandler(null);
    const result = await apiRequest<{ ok: boolean }>('/api/mobile/v1/me', { signal: new AbortController().signal });
    assert.equal(result.ok, true);
    assert.equal(seenAborted, false);
  });
});

describe('401 handler suppression for server logout', () => {
  it('fires the handler on 401, but not inside suppression', async () => {
    stubFetch(async () => jsonResponse(401, { error: 'mobile_auth_required' }));
    let handlerCalls = 0;
    setUnauthorizedHandler(() => { handlerCalls += 1; });
    await apiRequest('/api/mobile/v1/me').then(() => null, () => null);
    assert.equal(handlerCalls, 1);
    await withoutUnauthorizedHandler(() => apiRequest('/api/mobile/v1/auth/logout', { method: 'POST' })).then(() => null, () => null);
    assert.equal(handlerCalls, 1);
    setUnauthorizedHandler(null);
  });
});

describe('401 handler receives the rejected request token', () => {
  it('passes the bearer token of the failed request to the handler exactly once, without retrying', async () => {
    let seenTokens: Array<string | undefined> = [];
    let fetchCalls = 0;
    (globalThis as unknown as Record<string, unknown>).fetch = async () => {
      fetchCalls += 1;
      return { ok: false, status: 401, json: async () => ({ error: 'mobile_auth_required' }) };
    };
    setUnauthorizedHandler((failedToken) => { seenTokens.push(failedToken); });
    await apiRequest('/api/mobile/v1/me', {}, 'old-token').then(() => null, () => null);
    setUnauthorizedHandler(null);
    assert.deepEqual(seenTokens, ['old-token']);
    assert.equal(fetchCalls, 1, '401 must never be retried');
  });
});
