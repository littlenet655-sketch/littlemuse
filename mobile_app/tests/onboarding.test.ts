import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { routes, ApiError } from '../src/api/client';
import { childNextRoute, resetsDisplayState, screenForGate, shouldRefreshOnboardingForGate } from '../src/navigation/gates';

describe('onboarding navigation', () => {
  it('orders child gates face -> quiz -> home', () => {
    assert.equal(childNextRoute(true, true), 'FaceEnroll');
    assert.equal(childNextRoute(false, true), 'Quiz');
    assert.equal(childNextRoute(false, false), 'KidsTabs');
  });

  it('routes backend gates to their resolving screens', () => {
    assert.equal(screenForGate('face'), 'FaceEnroll');
    assert.equal(screenForGate('quiz'), 'Quiz');
    assert.equal(screenForGate('parent_verification'), 'OtpVerify');
    assert.equal(screenForGate('email_verification'), 'OtpVerify');
    assert.equal(screenForGate('quiet_hours'), null);
    assert.equal(screenForGate('screen_time'), null);
  });

  it('prefers v2 routes where a v2 contract exists', () => {
    assert.ok(routes.feedV2.startsWith('/api/mobile/v2/'));
    assert.ok(routes.reelsV2.startsWith('/api/mobile/v2/'));
    assert.ok(routes.discoverV2.startsWith('/api/mobile/v2/'));
    assert.ok(routes.uploadSession.startsWith('/api/mobile/v2/'));
    assert.equal(routes.processingStatus(42), '/api/mobile/v2/posts/42/processing-status');
    assert.equal(routes.uploadComplete('up 1/2'), '/api/mobile/v2/uploads/up%201%2F2/complete');
  });

  it('refreshes onboarding only on a NEW 428 face/quiz gate', () => {
    const faceGate = new ApiError(428, 'face_enrollment_required', 'Face enrollment is required', 'face');
    const quizGate = new ApiError(428, 'quiz_required', 'quiz required', 'quiz');
    const other = new ApiError(403, 'disabled_by_parent', 'disabled', null);

    // Unknown onboarding: always refresh so the child is routed to enrollment/quiz.
    assert.equal(shouldRefreshOnboardingForGate(faceGate, null), true);
    assert.equal(shouldRefreshOnboardingForGate(quizGate, undefined), true);
    // Changed gates refresh; already-known gates do not (no refresh loop).
    assert.equal(shouldRefreshOnboardingForGate(faceGate, { face_required: false, quiz_required: true }), true);
    assert.equal(shouldRefreshOnboardingForGate(faceGate, { face_required: true, quiz_required: false }), false);
    assert.equal(shouldRefreshOnboardingForGate(quizGate, { face_required: false, quiz_required: true }), false);
    // Non-428 errors never trigger the enrollment redirect.
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


describe('entry and OTP UX contracts', () => {
  it('offers explicit child, parent, and moderator/admin entry roles', () => {
    const source = readFileSync('src/screens/WelcomeLogin.tsx', 'utf8');
    assert.ok(source.includes("navigation.navigate('Login', { role: item.value })"));
    assert.ok(source.includes("Moderator / Admin"));
    assert.ok(source.includes("Kids Mode"));
    assert.ok(source.includes("Parent Mode"));
  });

  it('renders a six-cell OTP with a centered active cursor and numeric sanitization', () => {
    const source = readFileSync('src/screens/ParentOnboarding.tsx', 'utf8');
    assert.ok(source.includes("Array.from({ length: 6 }"));
    assert.ok(source.includes("styles.otpCursor"));
    assert.ok(source.includes("value.replace(/\\D/g, '').slice(0, 6)"));
    assert.ok(source.includes('textContentType="oneTimeCode"'));
  });
});
