import { ApiError } from '../api/errors';
import type { GateKind } from '../api/errors';
import type { OnboardingState } from '../api/auth';

export type ChildRoute =
  | 'Quiz' | 'KidsTabs'
  | 'FeedTab' | 'DiscoverTab' | 'CreateTab' | 'ReelsTab' | 'ProfileTab'
  | 'Stories' | 'NotificationsTab' | 'Conversations' | 'Chat'
  | 'ChatDetails' | 'NewMessage' | 'SavedContent' | 'EditProfile' | 'Connections'
  | 'PostDetail' | 'OtherProfile' | 'ProcessingStatus' | 'SafetyCentre' | 'ReportHistory';

/** Quiz gate wins: a child with a pending quiz must never reach home. */
export function childNextRoute(quizRequired: boolean): ChildRoute {
  if (quizRequired) return 'Quiz';
  return 'KidsTabs';
}

/** Map a backend gate to the screen that resolves it, if any. */
export function screenForGate(gate: GateKind): 'Quiz' | 'OtpVerify' | null {
  if (gate === 'quiz') return 'Quiz';
  if (gate === 'parent_verification' || gate === 'email_verification') return 'OtpVerify';
  return null;
}

/**
 * Should a 428 onboarding gate from the server trigger an authoritative
 * onboarding refresh (which routes the child to Quiz)?
 * Only when the gate is NEW relative to the last known session gates, so a
 * stably gated session never re-fetches in a loop.
 */
export function shouldRefreshOnboardingForGate(
  error: unknown,
  onboarding: OnboardingState | null | undefined,
): boolean {
  if (!(error instanceof ApiError)) return false;
  if (error.status !== 428) return false;
  if (error.gate === 'quiz') return onboarding?.quiz_required !== true;
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
 * Order: quiz -> home. Unknown/missing onboarding ALWAYS fails closed to
 * Quiz: a stale cached flag must never bypass unknown onboarding state.
 */
export function resolveChildRoute(
  onboarding: OnboardingState | null | undefined,
  _fallbackQuizRequired: boolean,
  current: ChildRoute = 'KidsTabs',
): ChildRoute {
  if (!onboarding) return 'Quiz';
  if (onboarding.quiz_required) return 'Quiz';
  return current === 'Quiz' ? 'KidsTabs' : current;
}
