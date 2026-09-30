import { withoutUnauthorizedHandler } from '../api/client';
import { clearSession } from './session';
import type { StorageBackend } from './backends';

export interface SessionControllerDeps {
  storage: StorageBackend;
  serverLogout: (token: string) => Promise<unknown>;
  clearQueries: () => Promise<void> | void;
}

/**
 * A. Local-only invalidation. Clears SecureStore, user, onboarding, quiz
 * state, and query caches. Performs NO network I/O, so it can never recurse
 * no matter how it was triggered (including a 401 handler).
 */
export async function invalidateLocalSession(deps: Pick<SessionControllerDeps, 'storage' | 'clearQueries'>): Promise<void> {
  // Stop query observers/network work first so no stale request can race the
  // token removal and trigger another unauthorized cascade during sign-out.
  // Cache cleanup is best-effort; a cache failure must never preserve auth.
  try {
    await deps.clearQueries();
  } catch {
    // Query-cache cleanup is advisory; auth cleanup below is authoritative.
  }
  await clearSession(deps.storage);
}

/**
 * B. User-initiated sign-out. Attempts the server logout exactly once with
 * the centralized 401 handler suppressed, then always invalidates locally.
 * A 401 from the expired token on /logout therefore cannot invoke itself.
 */
export async function userInitiatedSignOut(deps: SessionControllerDeps, token: string | null): Promise<void> {
  // Stop observers/network work before the logout request itself. Otherwise a
  // background query can race sign-out, receive a 401, and enter the local
  // invalidation path while the explicit logout is still in flight.
  try {
    await deps.clearQueries();
  } catch {
    // Query-cache cleanup is advisory; auth cleanup below is authoritative.
  }
  if (token) {
    try {
      await withoutUnauthorizedHandler(() => deps.serverLogout(token));
    } catch {
      // Best-effort: local state clears regardless of server outcome.
    }
  }
  await clearSession(deps.storage);
}
