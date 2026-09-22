/**
 * In-memory Parent authorization window for sensitive parent actions.
 *
 * Rules (per architecture spec):
 * - After a successful system authentication, the parent is authorized for
 *   PARENT_AUTH_WINDOW_MS (5 minutes). In-memory only: never persisted to
 *   disk, never stored as a permanent boolean.
 * - The window is invalidated on: timeout, app backgrounding, logout /
 *   session invalidation.
 * - Device authentication is an additional local gate; every action still
 *   requires the backend session/RBAC check server-side.
 */
import { AppState, type AppStateStatus } from 'react-native';
import {
  authenticateParentDevice,
  checkParentDeviceAuth,
  type ParentAuthErrorCode,
  type ParentDeviceAuthStatus,
} from './parentDeviceAuth';

export const PARENT_AUTH_WINDOW_MS = 5 * 60 * 1000;

export type ParentGateOutcome =
  | { ok: true }
  | { ok: false; reason: 'no_credential' }
  | { ok: false; reason: 'cancelled' }
  | { ok: false; reason: 'failed'; error?: ParentAuthErrorCode | string; message?: string };

interface GateState {
  /** Epoch ms until which the parent authorization window is valid. 0 = none. */
  authorizedUntil: number;
  /** Clock override for tests. */
  now: () => number;
  appStateSub: { remove: () => void } | null;
  listeners: Set<() => void>;
}

const state: GateState = {
  authorizedUntil: 0,
  now: () => Date.now(),
  appStateSub: null,
  listeners: new Set(),
};

/** Test seam: override the clock. */
export function __setParentGateClock(now: () => number): void {
  state.now = now;
}

/** Test seam: reset all gate state. */
export function __resetParentGate(): void {
  state.authorizedUntil = 0;
  state.now = () => Date.now();
}

function notify(): void {
  for (const listener of state.listeners) listener();
}

/** Subscribe to authorization-window changes (for UI re-render). */
export function subscribeParentGate(listener: () => void): () => void {
  state.listeners.add(listener);
  return () => {
    state.listeners.delete(listener);
  };
}

export function isParentAuthorized(now: number = state.now()): boolean {
  return now < state.authorizedUntil;
}

/** Milliseconds remaining in the current window, or 0. */
export function parentAuthRemainingMs(now: number = state.now()): number {
  return Math.max(0, state.authorizedUntil - now);
}

/** Invalidate the window: call on logout, session invalidation, timeout. */
export function invalidateParentAuth(): void {
  if (state.authorizedUntil !== 0) {
    state.authorizedUntil = 0;
    notify();
  }
}

function markParentAuthorized(now: number = state.now()): void {
  state.authorizedUntil = now + PARENT_AUTH_WINDOW_MS;
  notify();
}

/** AppState change handler: backgrounding invalidates the window. */
export function handleParentGateAppState(next: AppStateStatus): void {
  if (next === 'background' || next === 'inactive') {
    invalidateParentAuth();
  }
}

/**
 * Install the app-background invalidation listener. Idempotent; call once
 * from the parent-mode entry gate.
 */
export function installParentGateInvalidation(): () => void {
  if (state.appStateSub) {
    return () => undefined;
  }
  const sub = AppState.addEventListener('change', handleParentGateAppState);
  state.appStateSub = sub;
  return () => {
    sub.remove();
    state.appStateSub = null;
  };
}

/**
 * Ensure a fresh parent authorization for a sensitive action.
 *
 * - Returns { ok: true } when the in-memory window is still valid, or after
 *   a successful system authentication.
 * - Returns { ok: false, reason: 'no_credential' } when the device has
 *   neither an enrolled strong biometric nor a secure screen lock; the
 *   caller must show the "set up a screen lock" guidance.
 * - Returns { ok: false, reason: 'cancelled' } when the user dismisses the
 *   system prompt.
 * - Returns { ok: false, reason: 'failed', ... } on authentication failure.
 */
export async function requireParentAuth(): Promise<ParentGateOutcome> {
  const prep = await prepareParentAuth();
  if (prep.state === 'already_authorized') {
    return { ok: true };
  }
  if (prep.state === 'no_credential') {
    return { ok: false, reason: 'no_credential' };
  }
  if (prep.state === 'query_failed') {
    return { ok: false, reason: 'failed', error: 'failure', message: 'Could not query device authentication.' };
  }

  const result = await authenticateParentDevice();
  if (result.success) {
    markParentAuthorized(state.now());
    return { ok: true };
  }
  if (result.error === 'user_cancel') {
    return { ok: false, reason: 'cancelled' };
  }
  return {
    ok: false,
    reason: 'failed',
    error: result.error,
    message: friendlyParentAuthMessage(result.error, result.message),
  };
}

/**
 * Friendly, non-technical copy for each authentication error code.
 * Used as the message fallback when the native module returns no message,
 * so users get actionable guidance (e.g. lockout waits) instead of a
 * generic "could not verify" string. Never weakens the gate: the outcome
 * reasons and the fail-closed behavior are unchanged.
 */
export const PARENT_AUTH_ERROR_COPY: Record<ParentAuthErrorCode, string> = {
  user_cancel: 'Authentication was cancelled.',
  not_enrolled:
    'No fingerprint or face is set up on this phone. You can still verify with your phone PIN, pattern, or password.',
  lockout: 'Too many attempts. Wait a moment, then try again.',
  failure: 'Could not verify it is you. Please try again.',
  unavailable: 'Device authentication is not available on this device.',
  in_progress: 'Authentication is already in progress. Please wait.',
};

function friendlyParentAuthMessage(
  error: ParentAuthErrorCode | string | undefined,
  nativeMessage: string | undefined,
): string {
  if (nativeMessage) return nativeMessage;
  const code = String(error ?? '').toLowerCase() as ParentAuthErrorCode;
  return PARENT_AUTH_ERROR_COPY[code] ?? PARENT_AUTH_ERROR_COPY.failure;
}

export type ParentAuthPreparation =
  | { state: 'already_authorized' }
  | { state: 'ready'; status: ParentDeviceAuthStatus }
  | { state: 'no_credential'; status: ParentDeviceAuthStatus }
  | { state: 'query_failed' };

/**
 * Check whether parent authentication is possible WITHOUT showing the
 * system prompt.
 *
 * Intended for a pre-prompt explanation screen: call this first, explain
 * what will happen, and only then call requireParentAuth() to fire the system prompt. The window check and the
 * device-capability check are identical to requireParentAuth's, so the
 * two-step flow cannot skip the gate.
 */
export async function prepareParentAuth(): Promise<ParentAuthPreparation> {
  if (isParentAuthorized(state.now())) {
    return { state: 'already_authorized' };
  }
  let status: ParentDeviceAuthStatus;
  try {
    status = await checkParentDeviceAuth();
  } catch {
    // Fail closed: a query failure never skips the gate.
    return { state: 'query_failed' };
  }
  if (!status.canAuthenticate) {
    return { state: 'no_credential', status };
  }
  return { state: 'ready', status };
}
