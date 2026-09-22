import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { fetchMe, logout as apiLogout } from '../api/auth';
import type { LoginResponse, OnboardingState, SessionUser } from '../api/auth';
import { ApiError, setUnauthorizedHandler } from '../api/client';
import { invalidateLocalSession, userInitiatedSignOut } from './controller';
import { clearSession, persistLoginResponse, persistSession, restoreSession } from './session';
import type { PersistedSession } from './session';
import { secureStoreBackend } from './storage';
import { invalidateParentAuth } from '../deviceAuth/parentAuthGate';
import { invalidateSessionQueries } from '../query/client';

interface AuthState {
  status: 'loading' | 'signedOut' | 'signedIn';
  session: PersistedSession | null;
  onboarding: OnboardingState | null;
  signIn: (response: LoginResponse) => Promise<void>;
  /** User-initiated: one server attempt, then local invalidation. */
  signOut: () => Promise<void>;
  /** Authoritative refresh from /me. Throws on failure so gates never clear optimistically. */
  refreshMe: () => Promise<PersistedSession>;
}

const AuthContext = createContext<AuthState | null>(null);

const controllerDeps = {
  storage: secureStoreBackend,
  serverLogout: apiLogout,
  clearQueries: invalidateSessionQueries,
};

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthState['status']>('loading');
  const [session, setSession] = useState<PersistedSession | null>(null);
  const sessionRef = useRef<PersistedSession | null>(null);

  const applySession = useCallback((next: PersistedSession | null) => {
    sessionRef.current = next;
    setSession(next);
  }, []);

  /** Local-only: no network, safe to call from the centralized 401 handler. */
  const invalidateLocal = useCallback(async () => {
    invalidateParentAuth();
    sessionRef.current = null;
    setSession(null);
    setStatus('signedOut');
    await invalidateLocalSession(controllerDeps);
  }, []);

  const signOut = useCallback(async () => {
    invalidateParentAuth();
    const token = sessionRef.current?.token ?? null;
    if (token) {
      // Best-effort: revoke the push token server-side so this device
      // stops receiving notifications after sign-out.
      void import('../push/notifications').then((m) => m.unregisterPushToken(token));
    }
    sessionRef.current = null;
    setSession(null);
    setStatus('signedOut');
    await userInitiatedSignOut(controllerDeps, token);
  }, []);

  // Centralized 401 -> LOCAL invalidation only. Never a network request.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      void invalidateLocal();
    });
    return () => setUnauthorizedHandler(null);
  }, [invalidateLocal]);

  // Cold-start restoration with authoritative onboarding: server state from
  // /me overrides the cache whenever reachable; the cache only renders offline.
  useEffect(() => {
    let active = true;
    (async () => {
      const restored = await restoreSession(secureStoreBackend);
      if (!active) return;
      if (!restored) {
        setStatus('signedOut');
        return;
      }
      sessionRef.current = restored;
      setSession(restored);
      try {
        const me = await fetchMe(restored.token);
        if (!active) return;
        const next: PersistedSession = {
          token: restored.token,
          user: me.user,
          onboarding: me.onboarding ?? restored.onboarding,
        };
        // The restored session was replaced by authoritative server state:
        // treat it as a session change and drop any parent auth window.
        if (next.user.user_id !== restored.user.user_id || next.token !== restored.token) {
          invalidateParentAuth();
        }
        sessionRef.current = next;
        setSession(next);
        await persistSession(secureStoreBackend, next);
        setStatus('signedIn');
      } catch (error) {
        if (!active) return;
        if (error instanceof ApiError && error.status === 401) {
          invalidateParentAuth();
          await clearSession(secureStoreBackend);
          sessionRef.current = null;
          setSession(null);
          setStatus('signedOut');
          return;
        }
        // Offline/other failure: keep the cached session and cached gates.
        setStatus('signedIn');
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const signIn = useCallback(
    async (response: LoginResponse) => {
      // A new session always drops any previous parent authorization window.
      invalidateParentAuth();
      const next = await persistLoginResponse(secureStoreBackend, response);
      applySession(next);
      setStatus('signedIn');
      // Best-effort push registration: never blocks or breaks sign-in.
      void import('../push/notifications').then((m) => m.registerPushToken(next.token));
    },
    [applySession],
  );

  const refreshMe = useCallback(async (): Promise<PersistedSession> => {
    const current = sessionRef.current;
    if (!current) throw new Error('No session to refresh.');
    // A 401 here triggers local invalidation via the handler, then throws:
    // callers must stay gated and offer retry.
    const me = await fetchMe(current.token);
    const next: PersistedSession = {
      token: current.token,
      user: me.user,
      onboarding: me.onboarding ?? current.onboarding,
    };
    sessionRef.current = next;
    setSession(next);
    await persistSession(secureStoreBackend, next);
    return next;
  }, []);

  const value = useMemo<AuthState>(
    () => ({ status, session, onboarding: session?.onboarding ?? null, signIn, signOut, refreshMe }),
    [status, session, signIn, signOut, refreshMe],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}

export function useSessionUser(): SessionUser | null {
  return useAuth().session?.user ?? null;
}
