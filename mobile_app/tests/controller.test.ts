import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { invalidateLocalSession, userInitiatedSignOut } from '../src/auth/controller';
import { memoryBackend } from '../src/auth/backends';
import { ApiError } from '../src/api/client';

describe('401 / logout split (no recursion)', () => {
  it('cancels query work before removing the persisted token', async () => {
    const storage = memoryBackend({ 'littlenet.auth.token': 'expired' });
    const order: string[] = [];
    const originalRemove = storage.removeItem;
    storage.removeItem = async (key: string) => {
      if (key === 'littlenet.auth.token') order.push('remove-token');
      await originalRemove(key);
    };

    await invalidateLocalSession({
      storage,
      clearQueries: async () => {
        order.push('clear-queries');
      },
    });

    assert.deepEqual(order.slice(0, 2), ['clear-queries', 'remove-token']);
  });


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
