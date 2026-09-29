/**
 * Pure helpers for the compulsory periodic Reel quiz.
 *
 * The server latches quiz_due after a randomized 2-5 Reel interval. The feed
 * inserts one full-height prompt and the Reels screen immediately hands off to
 * Quiz; there is no dismiss/skip path while the latch is active.
 */

/** Sentinel row rendered as the prompt card inside the reels FlatList. */
export interface QuizPromptRow {
  kind: 'quiz-prompt';
  key: string;
}

export const QUIZ_PROMPT_KEY = 'quiz-prompt';

export function isQuizPromptRow(row: unknown): row is QuizPromptRow {
  return (
    typeof row === 'object' &&
    row !== null &&
    (row as { kind?: unknown }).kind === 'quiz-prompt'
  );
}

/**
 * Where the prompt card lands: after the 2nd reel so the child sees content
 * first, or at the end when the feed is shorter.
 */
export function quizPromptInsertAt(itemCount: number): number {
  if (itemCount <= 0) return 0;
  return Math.min(2, itemCount);
}

/** True when the compulsory prompt should be in the feed right now. */
export function shouldShowQuizPrompt(quizDue: boolean, _dismissed = false): boolean {
  return quizDue;
}

/**
 * Insert the prompt sentinel into a feed snapshot. Pure and idempotent: an
 * existing prompt row is removed first so repeated calls never duplicate it.
 */
export function withQuizPromptRow<T>(items: readonly T[], show: boolean): Array<T | QuizPromptRow> {
  const without = (items as Array<T | QuizPromptRow>).filter((it) => !isQuizPromptRow(it));
  if (!show) return without;
  const at = quizPromptInsertAt(without.length);
  const next = [...without];
  next.splice(at, 0, { kind: 'quiz-prompt', key: QUIZ_PROMPT_KEY });
  return next;
}
