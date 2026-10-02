/// <reference types="node" />
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

process.env.EXPO_PUBLIC_API_BASE_URL = 'https://backend.test.invalid';

import { ApiError, productionApiUrlProblem, setUnauthorizedHandler } from '../src/api/client';
import { answerQuiz, createChild, fetchQuiz, registerParent, requestPasswordReset, resendParentEmail, resetPassword, verifyParentEmail } from '../src/api/auth';
import { routes } from '../src/api/client';

interface SeenRequest {
  url: string;
  init: RequestInit;
}

describe('production API destination safety', () => {
  it('accepts public HTTPS and rejects cleartext/private destinations', () => {
    assert.equal(productionApiUrlProblem('https://api.littlenet.example'), null);
    assert.equal(productionApiUrlProblem('http://api.littlenet.example'), 'https_required');
    assert.equal(productionApiUrlProblem('https://192.168.0.8:5000'), 'private_host');
    assert.equal(productionApiUrlProblem('https://10.0.0.2'), 'private_host');
    assert.equal(productionApiUrlProblem('https://172.20.0.2'), 'private_host');
    assert.equal(productionApiUrlProblem('not a url'), 'invalid');
    assert.equal(productionApiUrlProblem(''), 'missing');
  });
});

let seen: SeenRequest[] = [];
let nextPayload: unknown = { ok: true };
let nextStatus = 200;

function stubFetch(): void {
  seen = [];
  (globalThis as unknown as Record<string, unknown>).fetch = async (url: unknown, init?: RequestInit) => {
    seen.push({ url: String(url), init: init ?? {} });
    return { ok: nextStatus >= 200 && nextStatus < 300, status: nextStatus, json: async () => nextPayload };
  };
}

function bodyJson(index = 0): Record<string, unknown> {
  return JSON.parse(String(seen[index]?.init.body ?? '{}')) as Record<string, unknown>;
}

describe('parent OTP contracts', () => {
  it('registers with guardian declaration and dob, then verifies OTP with the pending token', async () => {
    stubFetch();
    setUnauthorizedHandler(null);
    nextStatus = 200;
    nextPayload = { ok: true, pending_token: 'pend-1', email_sent: true };
    await registerParent({ username: 'dad_rio', full_name: 'Dad Rio', email: 'dad@example.com', password: 'secret123', dob: '1990-05-14' });
    assert.equal(seen[0]?.url, 'https://backend.test.invalid/api/mobile/v1/auth/parent/register');
    const regBody = bodyJson();
    assert.equal(regBody.guardian_declaration, '1');
    assert.equal(regBody.dob, '1990-05-14');

    // Email OTP is the final server-side parent activation step: it returns a
    // signed-in LoginResponse directly (no parent selfie/liveness step).
    nextPayload = { ok: true, token: 'tok-1', auth_method: 'PARENT_EMAIL_OTP', user: { user_id: 7, role: 'PARENT' } };
    const verified = await verifyParentEmail('pend-1', '123456');
    assert.equal(seen[1]?.url, 'https://backend.test.invalid/api/mobile/v1/auth/parent/verify-email');
    assert.deepEqual(bodyJson(1), { pending_token: 'pend-1', otp: '123456' });
    assert.equal(verified.ok, true);
    assert.equal(verified.token, 'tok-1');
    assert.equal(verified.auth_method, 'PARENT_EMAIL_OTP');
    assert.equal(verified.user.role, 'PARENT');

    nextPayload = { ok: true, error: null };
    await resendParentEmail('pend-1');
    assert.equal(seen[2]?.url, 'https://backend.test.invalid/api/mobile/v1/auth/parent/resend-email');
  });

  it('no longer exposes a parent liveness endpoint or client call', async () => {
    const authModule = await import('../src/api/auth.js');
    assert.equal('verifyParentLiveness' in authModule, false);
    assert.equal((routes as Record<string, unknown>).parentVerifyLiveness, undefined);
  });

  it('surfaces duplicate username/email backend errors verbatim', async () => {
    stubFetch();
    nextStatus = 400;
    nextPayload = { error: "The username 'dad_rio' already exists. Please choose a different username." };
    await assert.rejects(
      registerParent({ username: 'dad_rio', full_name: 'Dad Rio', email: 'dad@example.com', password: 'secret123', dob: '1990-05-14' }),
      (err: unknown) => err instanceof Error && err.message.includes('already exists'),
    );
  });

  it('creates a child with the verified-parent contract fields', async () => {
    stubFetch();
    nextStatus = 201;
    nextPayload = { ok: true, child_id: 9, next_steps: ['age_quiz'] };
    const created = await createChild('tok', { username: 'kid_rio', full_name: 'Kid Rio', age: 10, password: 'childpass1' });
    assert.equal(seen[0]?.url, 'https://backend.test.invalid/api/mobile/v1/parent/children');
    assert.equal(created.child_id, 9);
    assert.equal((seen[0]?.init.headers as Headers).get('Authorization'), 'Bearer tok');
  });
});

describe('password reset contracts', () => {
  it('requests a code with the identifier and completes with code + new password', async () => {
    stubFetch();
    nextStatus = 200;
    nextPayload = { ok: true, user_id: 11, masked_email: 'd***@example.com', is_parent_proxy: false, message: 'Verification code sent.' };
    const requested = await requestPasswordReset('dad_rio');
    assert.equal(seen[0]?.url, 'https://backend.test.invalid/api/mobile/v1/auth/forgot-password');
    assert.deepEqual(bodyJson(), { identifier: 'dad_rio' });
    assert.equal(requested.user_id, 11);

    nextPayload = { ok: true, message: 'Password reset successfully.' };
    const done = await resetPassword(11, '654321', 'brandnewpass1');
    assert.equal(seen[1]?.url, 'https://backend.test.invalid/api/mobile/v1/auth/reset-password');
    assert.deepEqual(bodyJson(1), { user_id: 11, code: '654321', new_password: 'brandnewpass1' });
    assert.equal(done.ok, true);
  });

  it('surfaces unknown-account and expired-code errors verbatim', async () => {
    stubFetch();
    nextStatus = 400;
    nextPayload = { ok: false, error: 'No LittleNet account found matching that username or email.' };
    await assert.rejects(
      requestPasswordReset('ghost'),
      (err: unknown) => err instanceof Error && err.message.includes('No LittleNet account found'),
    );
    nextPayload = { ok: false, error: 'The verification code has expired. Please request a new one.' };
    await assert.rejects(
      resetPassword(11, '000000', 'brandnewpass1'),
      (err: unknown) => err instanceof Error && err.message.includes('expired'),
    );
  });
});

describe('quiz gate contracts', () => {
  it('fetches the gate state and submits answers with the expected shape', async () => {
    stubFetch();
    nextStatus = 200;
    nextPayload = { ok: true, reason: 'onboarding', required: true, quizzes: [] };
    await fetchQuiz('child-tok');
    assert.equal(seen[0]?.url, 'https://backend.test.invalid/api/mobile/v1/kids/quiz');

    nextPayload = { ok: true, correct: true, correct_answer: 'a', xp: 10, explanation: 'Nice', onboarding_complete: true, required: false };
    const result = await answerQuiz('child-tok', 3, 'a');
    assert.equal(seen[1]?.url, 'https://backend.test.invalid/api/mobile/v1/kids/quiz/3/answer');
    assert.deepEqual(bodyJson(1), { answer: 'a' });
    assert.equal(result.onboarding_complete, true);
  });

  it('propagates quiz-required 428 gates with destination-safe errors', async () => {
    stubFetch();
    nextStatus = 428;
    nextPayload = { error: 'quiz_required', gate: 'quiz' };
    const err = await fetchQuiz('child-tok').catch((error: unknown) => error);
    assert.ok(err instanceof ApiError);
    assert.equal((err as ApiError).gate, 'quiz');
  });
});
