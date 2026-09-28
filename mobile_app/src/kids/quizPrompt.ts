/**
 * Pure helpers for the non-blocking periodic quiz nudge.
 *
 * The periodic latch is a NUDGE, never a session lock: when the server signals
 * quiz_due, the reels feed inserts one dismissible prompt card between reels.
 * A child who ignores or dismisses the card keeps full access. Tapping the
 * card opens the Quiz screen voluntarily.
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

/** True when the prompt card should be in the feed right now. */
export function shouldShowQuizPrompt(quizDue: boolean, dismissed: boolean): boolean {
  return quizDue && !dismissed;
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
