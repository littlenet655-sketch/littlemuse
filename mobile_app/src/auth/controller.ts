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
  await deps.clearQueries();
  await clearSession(deps.storage);
}

/**
 * B. User-initiated sign-out. Attempts the server logout exactly once with
 * the centralized 401 handler suppressed, then always invalidates locally.
 * A 401 from the expired token on /logout therefore cannot invoke itself.
 */
export async function userInitiatedSignOut(deps: SessionControllerDeps, token: string | null): Promise<void> {
  if (token) {
    try {
      await withoutUnauthorizedHandler(() => deps.serverLogout(token));
    } catch {
      // Best-effort: local state clears regardless of server outcome.
    }
  }
  await invalidateLocalSession(deps);
}
