import type { OnboardingState } from '../api/auth';

/**
 * Pure quiz-gate decisions so the rules are behavior-tested:
 * navigation onward happens only after an authoritative refresh confirms
 * every gate is clear.
 */

export type QuizLoadStatus = 'ready' | 'unavailable';

/** A required quiz with an empty bank must stay gated, never show "All done". */
export function quizLoadStatus(itemCount: number): QuizLoadStatus {
  return itemCount > 0 ? 'ready' : 'unavailable';
}

export function shouldProceedAfterRefresh(onboarding: OnboardingState | null | undefined): boolean {
  if (!onboarding) return false;
  return !onboarding.quiz_required;
}
