/// <reference types="node" />
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

process.env.EXPO_PUBLIC_API_BASE_URL = 'https://backend.test.invalid';

import { ApiError, setUnauthorizedHandler } from '../src/api/client';
import { retryDelayMs, shouldRetryRequest } from '../src/api/errors';
import { fetchReelsV2, refreshCuratedReelPlayback, refreshReelPlayback } from '../src/api/kidsFeed';
import { isQuizRequiredError } from '../src/video/quizGate';

let calls: string[] = [];
let queue: Array<{ status: number; body: unknown }> = [];

function stubFetch(responses: Array<{ status: number; body: unknown }>): void {
  calls = [];
  queue = [...responses];
  (globalThis as unknown as Record<string, unknown>).fetch = async (url: unknown) => {
    calls.push(String(url));
    // Keep serving the last scripted response so an accidental retry loop is
    // counted rather than crashing the stub.
    const next = queue.length > 1 ? queue.shift()! : queue[0]!;
    return { ok: next.status >= 200 && next.status < 300, status: next.status, json: async () => next.body };
  };
}

const QUIZ_428 = { status: 428, body: { ok: false, error: 'quiz_required' } };

describe('HTTP 428 quiz latch is a domain state, never a retryable failure', () => {
  it('shouldRetryRequest never retries 428 for any method or attempt', () => {
    for (const method of ['GET', 'POST', 'PUT', 'DELETE']) {
      for (const attempt of [0, 1, 2, 3]) {
        assert.equal(shouldRetryRequest(method, attempt, 428), false, `${method}#${attempt}`);
      }
    }
  });

  it('retry policy stays bounded for genuinely transient errors', () => {
    assert.equal(shouldRetryRequest('GET', 0, 503), true);
    assert.equal(shouldRetryRequest('GET', 1, 503), true);
    assert.equal(shouldRetryRequest('GET', 2, 503), false);
    assert.equal(shouldRetryRequest('POST', 0, 503), false);
    assert.ok(retryDelayMs(0) <= 4000 && retryDelayMs(9) <= 4000);
  });

  it('reel playback 428 costs exactly one network request and is recognised as quiz-required', async () => {
    stubFetch([QUIZ_428]);
    const err = await refreshReelPlayback('tok', 41).catch((e: unknown) => e);
    assert.equal(calls.length, 1, 'a 428 must not be retried');
    assert.ok(err instanceof ApiError);
    assert.equal((err as ApiError).status, 428);
    assert.equal(isQuizRequiredError(err), true);
  });

  it('curated reel playback 428 costs exactly one network request', async () => {
    stubFetch([QUIZ_428]);
    const err = await refreshCuratedReelPlayback('tok', 9).catch((e: unknown) => e);
    assert.equal(calls.length, 1);
    assert.equal(isQuizRequiredError(err), true);
  });

  it('a latched reels list (200 + quiz_required) is surfaced as a quiz error, not an empty feed', async () => {
    stubFetch([{ status: 200, body: { ok: true, items: [], quiz_required: true } }]);
    const err = await fetchReelsV2('tok', 0, 8).catch((e: unknown) => e);
    assert.equal(calls.length, 1);
    assert.equal(isQuizRequiredError(err), true);
  });

  it('latch OFF: the same endpoints return normally and are not flagged', async () => {
    stubFetch([{ status: 200, body: { ok: true, playback_url: 'https://cdn.test/v.mp4', playback_expires_at: 1 } }]);
    const res = await refreshReelPlayback('tok', 41);
    assert.equal(res.ok, true);
    assert.equal(calls.length, 1);

    stubFetch([{ status: 200, body: { ok: true, items: [], quiz_required: false, next_cursor: null } }]);
    const page = await fetchReelsV2('tok', 0, 8);
    assert.ok(page);
    assert.equal(isQuizRequiredError(null), false);
    assert.equal(isQuizRequiredError(new Error('boom')), false);
    assert.equal(isQuizRequiredError(new ApiError(503, 'server_unavailable', 'x')), false);
  });

  it('after the quiz is cleared the very next playback request succeeds (resume)', async () => {
    stubFetch([QUIZ_428]);
    assert.equal(isQuizRequiredError(await refreshReelPlayback('tok', 41).catch((e: unknown) => e)), true);
    stubFetch([{ status: 200, body: { ok: true, playback_url: 'https://cdn.test/v.mp4' } }]);
    const resumed = await refreshReelPlayback('tok', 41);
    assert.equal(resumed.playback_url, 'https://cdn.test/v.mp4');
    assert.equal(calls.length, 1);
  });

  it('a 428 does not trigger the 401/logout handler', async () => {
    let unauthorized = 0;
    setUnauthorizedHandler(() => { unauthorized += 1; });
    stubFetch([QUIZ_428]);
    await refreshReelPlayback('tok', 41).catch(() => undefined);
    setUnauthorizedHandler(null);
    assert.equal(unauthorized, 0);
  });
});
