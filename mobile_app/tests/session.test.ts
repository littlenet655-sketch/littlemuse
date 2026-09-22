import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import type { LoginResponse } from '../src/api/auth';
import { clearPendingDestination, clearSession, decideInitialRoute, loadPendingDestination, persistSession, restoreSession, savePendingDestination } from '../src/auth/session';
import { memoryBackend } from '../src/auth/backends';

function loginResponse(role: 'CHILD' | 'PARENT' | 'ADMIN', quizRequired = false): LoginResponse {
  return {
    ok: true,
    token: 'token-123',
    auth_method: 'PASSWORD',
    user: {
      user_id: 7,
      username: 'kid_rio',
      full_name: 'Rio',
      email: 'rio@kids.littlenet.internal',
      role,
      age: 10,
      profile: null,
      quiz_required: quizRequired,
      posts_seen: 0,
      quiz_interval: 4,
    },
  };
}

describe('auth restoration and logout', () => {
  it('persists and restores a session across a cold start', async () => {
    const storage = memoryBackend();
    await persistSession(storage, { ...loginResponse('CHILD'), onboarding: { quiz_required: true } });
    const restored = await restoreSession(storage);
    assert.equal(restored?.token, 'token-123');
    assert.equal(restored?.user.username, 'kid_rio');
    assert.deepEqual(restored?.onboarding, { quiz_required: true });
  });

  it('rejects corrupt cached users instead of crashing', async () => {
    const storage = memoryBackend({ 'littlenet.auth.token': 't', 'littlenet.auth.user': '{broken' });
    assert.equal(await restoreSession(storage), null);
  });

  it('rejects corrupt cached gates and fails closed', async () => {
    const storage = memoryBackend();
    await persistSession(storage, { ...loginResponse('CHILD'), onboarding: { quiz_required: false } });
    storage.data['littlenet.auth.onboarding'] = '{broken';
    const restored = await restoreSession(storage);
    assert.equal(restored?.onboarding, null);
  });

  it('logout clears tokens, user, gates, and quiz destinations', async () => {
    const storage = memoryBackend();
    await persistSession(storage, { ...loginResponse('CHILD'), onboarding: { quiz_required: true } });
    await savePendingDestination(storage, 'KidsHome');
    await clearSession(storage);
    assert.equal(await restoreSession(storage), null);
    assert.equal(await loadPendingDestination(storage), null);
  });

  it('preserves the quiz destination across relaunch until completion', async () => {
    const storage = memoryBackend();
    await savePendingDestination(storage, 'KidsHome');
    assert.equal(await loadPendingDestination(storage), 'KidsHome');
    await clearPendingDestination(storage);
    assert.equal(await loadPendingDestination(storage), null);
  });
});

describe('role-aware cold-start routing', () => {
  it('sends signed-out users to auth', () => {
    assert.equal(decideInitialRoute(null), 'auth');
  });

  it('sends parents and admins to their stacks', async () => {
    const storage = memoryBackend();
    const parent = await persistSession(storage, loginResponse('PARENT'));
    assert.equal(decideInitialRoute(parent), 'parent');
    const admin = await persistSession(storage, loginResponse('ADMIN'));
    assert.equal(decideInitialRoute(admin), 'admin');
  });

  it('holds children at the quiz gate, then home', async () => {
    const storage = memoryBackend();
    const session = await persistSession(storage, loginResponse('CHILD', true));
    assert.equal(decideInitialRoute(session, { quiz_required: true }), 'child_quiz');
    assert.equal(decideInitialRoute(session, { quiz_required: false }), 'child');
  });

  it('unknown child onboarding fails closed to child_quiz regardless of cached quiz flag', async () => {
    const storage = memoryBackend();
    const staleQuiz = await persistSession(storage, loginResponse('CHILD', true));
    assert.equal(decideInitialRoute(staleQuiz, null), 'child_quiz');
    assert.equal(decideInitialRoute(staleQuiz, undefined), 'child_quiz');
    const staleClear = await persistSession(storage, loginResponse('CHILD', false));
    assert.equal(decideInitialRoute(staleClear, null), 'child_quiz');
    assert.equal(decideInitialRoute(staleClear, undefined), 'child_quiz');
  });
});
