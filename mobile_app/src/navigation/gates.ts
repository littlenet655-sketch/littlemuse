import { ApiError } from '../api/errors';
import type { GateKind } from '../api/errors';
import type { OnboardingState } from '../api/auth';

export type ChildRoute =
  | 'Quiz' | 'KidsTabs'
  | 'FeedTab' | 'DiscoverTab' | 'CreateTab' | 'ReelsTab' | 'ProfileTab'
  | 'Stories' | 'NotificationsTab' | 'Conversations' | 'Chat'
  | 'ChatDetails' | 'NewMessage' | 'SavedContent' | 'EditProfile' | 'Connections'
  | 'PostDetail' | 'OtherProfile' | 'ProcessingStatus';

/**
 * Quiz never gates routing at the navigator level: the compulsory Reel quiz is
 * enforced inside the Reels flow itself (pause + hand off to the Quiz screen,
 * no dismiss path while the server latch is active), not by redirecting the
 * child away from wherever they are. A child with a due quiz always keeps
 * full access to Home and other tabs, so this always resolves to home.
 */
export function childNextRoute(_quizRequired: boolean): ChildRoute {
  return 'KidsTabs';
}

/** Map a backend gate to the screen that resolves it, if any. */
export function screenForGate(gate: GateKind): 'Quiz' | 'OtpVerify' | null {
  // The compulsory Reel quiz is enforced inside the Reels flow (pause + Quiz
  // screen hand-off), never as a navigator-level gate: no backend gate routes
  // to Quiz from here.
  if (gate === 'quiz') return null;
  if (gate === 'parent_verification' || gate === 'email_verification') return 'OtpVerify';
  return null;
}

/**
 * Should a 428 onboarding gate from the server trigger an authoritative
 * onboarding refresh (which used to route the child to Quiz)?
 * The compulsory Reel quiz is enforced inside the Reels flow, never by
 * navigator redirects, so a 428 quiz refreshes nothing. Only kept for
 * non-quiz gates (currently none re-gate).
 */
export function shouldRefreshOnboardingForGate(
  error: unknown,
  _onboarding: OnboardingState | null | undefined,
): boolean {
  if (!(error instanceof ApiError)) return false;
  if (error.status !== 428) return false;
  // Quiz 428s are no longer emitted by the server; even a stale one must not
  // re-gate the child to Quiz.
  return false;
}

/**
 * Server-authoritative display state for the kid self-reset card. Until the
 * server confirms the count, the client must never guess "2 left".
 */
export type ResetsDisplay = 'unknown' | 'available' | 'exhausted';

export function resetsDisplayState(resetsRemaining: number | null): ResetsDisplay {
  if (resetsRemaining === null) return 'unknown';
  return resetsRemaining > 0 ? 'available' : 'exhausted';
}

/**
 * Reactive child route from authoritative gates.
 * The compulsory Reel quiz is enforced inside the Reels flow (pause + Quiz
 * screen hand-off with no dismiss path), never by redirecting the child away
 * from what they are doing: quiz_required only drives the Reels handoff, so
 * the child is never routed away from other surfaces. Unknown/missing
 * onboarding FAILS OPEN to the current route (defect C1/C2): no quiz may
 * block app launch or Home entry.
 */
export function resolveChildRoute(
  onboarding: OnboardingState | null | undefined,
  _fallbackQuizRequired: boolean,
  current: ChildRoute = 'KidsTabs',
): ChildRoute {
  if (!onboarding) return current;
  return current;
}

/**
 * Offline fail-open for the gate sync (defect C1/C2 follow-up). With no
 * connectivity there is no authoritative gate, so a stale cached
 * quiz_required must not strand the child on Quiz. Returns the route to
 * reset to, or null when no reset is needed. The server re-signals quiz_due
 * on reconnect (/me + impression responses) and the Reels flow hands off to
 * the compulsory Quiz again — the latch never re-gates other routing.
 */
export function offlineGateReset(current: ChildRoute, online: boolean): ChildRoute | null {
  if (online) return null;
  return current === 'Quiz' ? 'KidsTabs' : null;
}
