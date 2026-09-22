import type { LoginResponse, OnboardingState, SessionUser } from '../api/auth';
import type { StorageBackend } from './backends';

const TOKEN_KEY = 'littlenet.auth.token';
const USER_KEY = 'littlenet.auth.user';
const ONBOARDING_KEY = 'littlenet.auth.onboarding';
const PENDING_DEST_KEY = 'littlenet.quiz.pending_destination';

export interface PersistedSession {
  token: string;
  user: SessionUser;
  /** Last-known authoritative gates. Server state overrides this whenever reachable. */
  onboarding: OnboardingState | null;
}

export type InitialRoute = 'auth' | 'child' | 'child_quiz' | 'parent' | 'admin';

/** Where the child wanted to go before a mandatory quiz interrupted them. */
export async function savePendingDestination(storage: StorageBackend, destination: string): Promise<void> {
  await storage.setItem(PENDING_DEST_KEY, destination);
}

export async function loadPendingDestination(storage: StorageBackend): Promise<string | null> {
  return storage.getItem(PENDING_DEST_KEY);
}

export async function clearPendingDestination(storage: StorageBackend): Promise<void> {
  await storage.removeItem(PENDING_DEST_KEY);
}

function parseOnboarding(raw: string | null): OnboardingState | null {
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Partial<OnboardingState>;
    if (typeof value.quiz_required !== 'boolean') return null;
    return { quiz_required: value.quiz_required };
  } catch {
    return null;
  }
}

export async function persistSession(
  storage: StorageBackend,
  session: { token: string; user: SessionUser; onboarding?: OnboardingState | null },
): Promise<PersistedSession> {
  const next: PersistedSession = { token: session.token, user: session.user, onboarding: session.onboarding ?? null };
  await storage.setItem(TOKEN_KEY, next.token);
  await storage.setItem(USER_KEY, JSON.stringify(next.user));
  if (next.onboarding) {
    await storage.setItem(ONBOARDING_KEY, JSON.stringify(next.onboarding));
  } else {
    await storage.removeItem(ONBOARDING_KEY);
  }
  return next;
}

/** Accepts the login payload shape directly. */
export async function persistLoginResponse(storage: StorageBackend, response: LoginResponse): Promise<PersistedSession> {
  return persistSession(storage, { token: response.token, user: response.user, onboarding: response.onboarding ?? null });
}

export async function restoreSession(storage: StorageBackend): Promise<PersistedSession | null> {
  const [token, rawUser, rawOnboarding] = await Promise.all([
    storage.getItem(TOKEN_KEY),
    storage.getItem(USER_KEY),
    storage.getItem(ONBOARDING_KEY),
  ]);
  if (!token || !rawUser) return null;
  try {
    const user = JSON.parse(rawUser) as SessionUser;
    if (typeof user.user_id !== 'number' || typeof user.role !== 'string') return null;
    return { token, user, onboarding: parseOnboarding(rawOnboarding) };
  } catch {
    return null;
  }
}

export async function clearSession(storage: StorageBackend): Promise<void> {
  await Promise.all([
    storage.removeItem(TOKEN_KEY),
    storage.removeItem(USER_KEY),
    storage.removeItem(ONBOARDING_KEY),
    storage.removeItem(PENDING_DEST_KEY),
  ]);
}

/**
 * Cold-start routing from a restored session plus authoritative gates.
 * For CHILD, unknown/missing onboarding ALWAYS fails closed to child_quiz:
 * a stale cached flag must never bypass unknown onboarding state.
 */
export function decideInitialRoute(session: PersistedSession | null, onboarding?: { quiz_required: boolean } | null): InitialRoute {
  if (!session) return 'auth';
  if (session.user.role === 'PARENT') return 'parent';
  if (session.user.role === 'ADMIN') return 'admin';
  if (!onboarding) return 'child_quiz';
  if (onboarding.quiz_required) return 'child_quiz';
  return 'child';
}
