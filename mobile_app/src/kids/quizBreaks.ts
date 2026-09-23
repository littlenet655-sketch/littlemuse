export const QUIZ_EVERY_N = 5;

export interface QuizMarker {
  __quizBreak: true;
  markerId: string;
}

export function isQuizMarker(value: unknown): value is QuizMarker {
  return Boolean(
    value &&
      typeof value === 'object' &&
      '__quizBreak' in value &&
      (value as { __quizBreak?: unknown }).__quizBreak === true,
  );
}

export function withQuizBreaks<T>(items: readonly T[], every = QUIZ_EVERY_N): Array<T | QuizMarker> {
  if (!Number.isFinite(every) || every <= 0) return [...items];
  const out: Array<T | QuizMarker> = [];
  items.forEach((item, index) => {
    out.push(item);
    const ordinal = index + 1;
    if (ordinal % every === 0) {
      out.push({ __quizBreak: true, markerId: `quiz-${ordinal}` });
    }
  });
  return out;
}
