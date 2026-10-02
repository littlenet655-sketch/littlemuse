import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { routes, ApiError } from '../src/api/client';
import { childNextRoute, resetsDisplayState, screenForGate, shouldRefreshOnboardingForGate } from '../src/navigation/gates';

describe('onboarding navigation', () => {
  it('never routes a due quiz: quiz latch is a nudge, not a route gate', () => {
    assert.equal(childNextRoute(true), 'KidsTabs');
    assert.equal(childNextRoute(false), 'KidsTabs');
  });

  it('routes backend gates to their resolving screens', () => {
    assert.equal(screenForGate('quiz'), null);
    assert.equal(screenForGate('parent_verification'), 'OtpVerify');
    assert.equal(screenForGate('email_verification'), 'OtpVerify');
    assert.equal(screenForGate('quiet_hours'), null);
    assert.equal(screenForGate('screen_time'), null);
  });

  it('prefers v2 routes where a v2 contract exists', () => {
    assert.ok(routes.feedV2.startsWith('/api/mobile/v2/'));
    assert.ok(routes.reelsV2.startsWith('/api/mobile/v2/'));
    assert.ok(routes.discoverV2.startsWith('/api/mobile/v2/'));
    assert.ok(routes.uploadSession.startsWith('/api/mobile/v2/uploads/'));
    assert.equal(routes.processingStatus(42), '/api/mobile/v2/posts/42/processing-status');
    assert.equal(routes.uploadComplete('up 1/2'), '/api/mobile/v2/uploads/up%201%2F2/complete');
  });

  it('never refreshes onboarding into a quiz gate: quiz 428s re-route nothing', () => {
    const quizGate = new ApiError(428, 'quiz_required', 'quiz required', 'quiz');
    const other = new ApiError(403, 'disabled_by_parent', 'disabled', null);

    // A stale 428 quiz gate must not re-gate the child to Quiz, no matter
    // what the onboarding snapshot says.
    assert.equal(shouldRefreshOnboardingForGate(quizGate, undefined), false);
    assert.equal(shouldRefreshOnboardingForGate(quizGate, { quiz_required: false }), false);
    assert.equal(shouldRefreshOnboardingForGate(quizGate, { quiz_required: true }), false);
    // Non-428 errors never trigger the onboarding redirect.
    assert.equal(shouldRefreshOnboardingForGate(other, null), false);
    assert.equal(shouldRefreshOnboardingForGate(new Error('boom'), null), false);
  });

  it('never guesses a server reset count: unknown stays unknown', () => {
    assert.equal(resetsDisplayState(null), 'unknown');
    assert.equal(resetsDisplayState(2), 'available');
    assert.equal(resetsDisplayState(1), 'available');
    assert.equal(resetsDisplayState(0), 'exhausted');
  });
});
