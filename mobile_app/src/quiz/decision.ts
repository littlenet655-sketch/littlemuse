import { ApiError } from '../api/errors';
import type { OnboardingState } from '../api/auth';

/**
 * Pure quiz-nudge decisions so the rules are behavior-tested:
 * navigation onward happens only after an authoritative refresh confirms the
 * quiz was counted and the quiz-due signal cleared.
 */

export type QuizLoadStatus = 'ready' | 'unavailable';

export function quizAnswerAction(practice: boolean, correct: boolean, required: boolean, lastItem: boolean) {
  if (practice) return lastItem ? 'refill' : 'next';
  if (!correct && required) return 'retry';
  return correct && (!required || lastItem) ? 'complete' : 'next';
}

/** A required quiz with an empty bank must stay gated, never show "All done". */
export function quizLoadStatus(itemCount: number): QuizLoadStatus {
  return itemCount > 0 ? 'ready' : 'unavailable';
}

export function shouldProceedAfterRefresh(onboarding: OnboardingState | null | undefined): boolean {
  if (!onboarding) return false;
  return !onboarding.quiz_required;
}

/**
 * True when a quiz fetch failed because the device could not reach the
 * server at all (offline / timed out), as opposed to the server refusing.
 * Only a proven-unreachable server may fail the quiz fetch open (defect
 * C1/C2 follow-up): a 4xx/5xx keeps the Retry state, and the periodic latch
 * signal stays server-owned.
 */
export function isConnectivityFailure(error: unknown): boolean {
  if (!(error instanceof ApiError) || error.status !== 0) return false;
  return error.code === 'network_unreachable' || error.code === 'request_timeout';
}
