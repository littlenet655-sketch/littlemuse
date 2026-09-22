import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { childNextRoute, resolveChildRoute, screenForGate } from '../src/navigation/gates';
import { quizLoadStatus, shouldProceedAfterRefresh } from '../src/quiz/decision';
import { validateResetInput } from '../src/auth/resetValidation';
import { captureLivePhotoCore, CameraBlockedError, CameraCancelledError, CameraPermissionError } from '../src/camera/capture';

describe('reactive child gate routing (quiz -> home)', () => {
  it('orders gates quiz first, then home', () => {
    assert.equal(childNextRoute(true), 'Quiz');
    assert.equal(childNextRoute(false), 'KidsTabs');
  });

  it('cold restore with quiz_required stays on Quiz', () => {
    assert.equal(resolveChildRoute({ quiz_required: true }, false), 'Quiz');
  });

  it('preserves ungated product routes', () => {
    const clear = { quiz_required: false };
    assert.equal(resolveChildRoute(clear, false, 'KidsTabs'), 'KidsTabs');
    assert.equal(resolveChildRoute(clear, false, 'FeedTab'), 'FeedTab');
    assert.equal(resolveChildRoute(clear, false, 'ReelsTab'), 'ReelsTab');
    assert.equal(resolveChildRoute(clear, false, 'Chat'), 'Chat');
  });

  it('forces active gates from every product route', () => {
    for (const route of ['KidsTabs', 'FeedTab', 'ReelsTab', 'Chat'] as const) {
      assert.equal(resolveChildRoute({ quiz_required: true }, false, route), 'Quiz');
    }
  });

  it('enters the product once after a gate clears', () => {
    const clear = { quiz_required: false };
    assert.equal(resolveChildRoute(clear, false, 'Quiz'), 'KidsTabs');
  });

  it('restart never bypasses an unknown gate (fails closed)', () => {
    assert.equal(resolveChildRoute(null, false), 'Quiz');
    assert.equal(resolveChildRoute(null, true), 'Quiz');
    assert.equal(resolveChildRoute(undefined, false), 'Quiz');
    assert.equal(resolveChildRoute(undefined, true), 'Quiz');
  });

  it('routes backend gates to their resolving screens', () => {
    assert.equal(screenForGate('quiz'), 'Quiz');
    assert.equal(screenForGate('parent_verification'), 'OtpVerify');
    assert.equal(screenForGate('email_verification'), 'OtpVerify');
    assert.equal(screenForGate('quiet_hours'), null);
    assert.equal(screenForGate('screen_time'), null);
  });
});

describe('quiz completion gating (authoritative refresh)', () => {
  it('proceeds only when the refresh confirms every gate clear', () => {
    assert.equal(shouldProceedAfterRefresh({ quiz_required: false }), true);
    assert.equal(shouldProceedAfterRefresh({ quiz_required: true }), false);
  });

  it('never proceeds on unknown/failed refresh (stays gated with retry)', () => {
    assert.equal(shouldProceedAfterRefresh(null), false);
    assert.equal(shouldProceedAfterRefresh(undefined), false);
  });

  it('required quiz with empty bank stays gated, never shows All done', () => {
    assert.equal(quizLoadStatus(0), 'unavailable');
    assert.equal(quizLoadStatus(3), 'ready');
  });
});

describe('password reset input rules', () => {
  it('accepts a complete valid reset', () => {
    assert.equal(validateResetInput('123456', 'newpass123', 'newpass123'), null);
  });

  it('rejects short codes, short passwords, and mismatches', () => {
    assert.ok(validateResetInput('123', 'newpass123', 'newpass123'));
    assert.ok(validateResetInput('123456', 'short', 'short'));
    assert.ok(validateResetInput('123456', 'newpass123', 'otherpass1'));
  });
});

describe('camera permission UX states', () => {
  const photo = { cancelled: false as const, base64: 'abc', width: 100, height: 100 };

  it('captures when permission is already granted (camera only)', async () => {
    let launched = 0;
    const result = await captureLivePhotoCore({
      getPermissions: async () => ({ granted: true, canAskAgain: true }),
      requestPermissions: async () => { throw new Error('should not ask again'); },
      launchCamera: async () => { launched += 1; return photo; },
    });
    assert.equal(result.base64, 'abc');
    assert.equal(launched, 1);
  });

  it('asks once then captures when the user allows', async () => {
    const result = await captureLivePhotoCore({
      getPermissions: async () => ({ granted: false, canAskAgain: true }),
      requestPermissions: async () => ({ granted: true, canAskAgain: true }),
      launchCamera: async () => photo,
    });
    assert.equal(result.base64, 'abc');
  });

  it('denied-but-askable raises a retryable permission error', async () => {
    await assert.rejects(
      captureLivePhotoCore({
        getPermissions: async () => ({ granted: false, canAskAgain: true }),
        requestPermissions: async () => ({ granted: false, canAskAgain: true }),
        launchCamera: async () => photo,
      }),
      (err: unknown) => err instanceof CameraPermissionError,
    );
  });

  it('permanently denied raises a blocked error for the Open Settings path', async () => {
    await assert.rejects(
      captureLivePhotoCore({
        getPermissions: async () => ({ granted: false, canAskAgain: false }),
        requestPermissions: async () => ({ granted: false, canAskAgain: false }),
        launchCamera: async () => photo,
      }),
      (err: unknown) => err instanceof CameraBlockedError,
    );
  });

  it('cancelled camera stays in place without an error state', async () => {
    await assert.rejects(
      captureLivePhotoCore({
        getPermissions: async () => ({ granted: true, canAskAgain: true }),
        requestPermissions: async () => ({ granted: true, canAskAgain: true }),
        launchCamera: async () => ({ cancelled: true as const }),
      }),
      (err: unknown) => err instanceof CameraCancelledError,
    );
  });

  it('camera launch failure surfaces a retryable error', async () => {
    await assert.rejects(
      captureLivePhotoCore({
        getPermissions: async () => ({ granted: true, canAskAgain: true }),
        requestPermissions: async () => ({ granted: true, canAskAgain: true }),
        launchCamera: async () => { throw new Error('camera busy'); },
      }),
      (err: unknown) => err instanceof Error && !(err instanceof CameraCancelledError),
    );
  });
});
