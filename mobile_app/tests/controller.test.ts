import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { invalidateLocalSession, userInitiatedSignOut } from '../src/auth/controller';
import { memoryBackend } from '../src/auth/backends';
import { ApiError } from '../src/api/client';

describe('401 / logout split (no recursion)', () => {
  it('expired-token 401 path clears locally without any server call', async () => {
    const storage = memoryBackend({ 'littlenet.auth.token': 'expired', 'littlenet.auth.user': '{"user_id":1,"role":"CHILD"}' });
    let serverCalls = 0;
    let queriesCleared = 0;
    // Simulates the centralized 401 handler: local invalidation only.
    await invalidateLocalSession({ storage, clearQueries: async () => { queriesCleared += 1; } });
    assert.equal(serverCalls, 0);
    assert.equal(queriesCleared, 1);
    assert.equal(storage.data['littlenet.auth.token'], undefined);
    assert.equal(storage.data['littlenet.auth.user'], undefined);
    assert.equal(storage.data['littlenet.auth.onboarding'], undefined);
  });

  it('user logout calls the server exactly once even when it 401s', async () => {
    const storage = memoryBackend({ 'littlenet.auth.token': 't' });
    let serverCalls = 0;
    await userInitiatedSignOut(
      {
        storage,
        serverLogout: async () => {
          serverCalls += 1;
          throw new ApiError(401, 'mobile_auth_required', 'expired');
        },
        clearQueries: async () => undefined,
      },
      't',
    );
    assert.equal(serverCalls, 1);
    assert.equal(storage.data['littlenet.auth.token'], undefined);
  });

  it('local state clears even if server logout fails with 500', async () => {
    const storage = memoryBackend({ 'littlenet.auth.token': 't', 'littlenet.auth.user': '{}' });
    await userInitiatedSignOut(
      {
        storage,
        serverLogout: async () => {
          throw new ApiError(500, 'server_unavailable', 'busy');
        },
        clearQueries: async () => undefined,
      },
      't',
    );
    assert.equal(storage.data['littlenet.auth.token'], undefined);
  });

  it('sign-out with no token performs local invalidation only', async () => {
    const storage = memoryBackend({ 'littlenet.auth.token': 't' });
    let serverCalls = 0;
    await userInitiatedSignOut(
      { storage, serverLogout: async () => { serverCalls += 1; }, clearQueries: async () => undefined },
      null,
    );
    assert.equal(serverCalls, 0);
    assert.equal(storage.data['littlenet.auth.token'], undefined);
  });
});

import { shouldInvalidateOnUnauthorized } from '../src/auth/session';

describe('logout ordering and 401 gating (no 401 storm)', () => {
  it('sign-out stops user-scoped queries BEFORE the server round-trip and clears again after', async () => {
    const order: string[] = [];
    const storage = memoryBackend({ 'littlenet.auth.token': 't' });
    await userInitiatedSignOut(
      {
        storage,
        serverLogout: async () => { order.push('serverLogout'); },
        clearQueries: async () => { order.push('clearQueries'); },
      },
      't',
    );
    assert.deepEqual(order, ['clearQueries', 'serverLogout', 'clearQueries']);
    assert.equal(storage.data['littlenet.auth.token'], undefined);
  });

  it('a failing cache teardown can never block sign-out', async () => {
    const storage = memoryBackend({ 'littlenet.auth.token': 't' });
    let serverCalls = 0;
    let firstCall = true;
    await userInitiatedSignOut(
      {
        storage,
        serverLogout: async () => { serverCalls += 1; },
        clearQueries: async () => {
          if (firstCall) { firstCall = false; throw new Error('cache boom'); }
        },
      },
      't',
    );
    assert.equal(serverCalls, 1);
    assert.equal(storage.data['littlenet.auth.token'], undefined);
  });

  it('a 401 for the current session invalidates it', () => {
    assert.equal(shouldInvalidateOnUnauthorized('tok-A', 'tok-A'), true);
    assert.equal(shouldInvalidateOnUnauthorized('tok-A', undefined), true);
  });

  it('a late 401 from a previous session must not sign out the new login', () => {
    assert.equal(shouldInvalidateOnUnauthorized('tok-B', 'tok-A'), false);
  });

  it('duplicate/unauthenticated 401s after sign-out are ignored (dedupes the storm)', () => {
    assert.equal(shouldInvalidateOnUnauthorized(null, 'tok-A'), false);
    assert.equal(shouldInvalidateOnUnauthorized(undefined, undefined), false);
  });
});
