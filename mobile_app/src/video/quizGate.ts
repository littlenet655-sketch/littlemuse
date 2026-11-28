import { ApiError } from '../api/errors';

/**
 * True when a failed Reel/playback call is the server's compulsory-quiz latch
 * (HTTP 428 / `quiz_required`). This is an expected application state, not a
 * transient failure: callers must stop requesting protected media and hand off
 * to the quiz instead of retrying or showing a generic playback error.
 */
export function isQuizRequiredError(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    (error.code === 'quiz_required' || (error.status === 428 && error.gate === 'quiz'))
  );
}
