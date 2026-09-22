/// <reference types="node" />
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

process.env.EXPO_PUBLIC_API_BASE_URL = 'https://backend.test.invalid';

import { ApiError, setUnauthorizedHandler } from '../src/api/client';
import {
  enrollChildFaceByParent,
  extendChildScreenTime,
  fetchAdminAudit,
  fetchAdminDashboard,
  fetchAdminReview,
  fetchAdminReviews,
  fetchAdminUsers,
  fetchFollowRequests,
  fetchParentActivity,
  fetchParentInsights,
  fetchParentControls,
  fetchParentDashboard,
  fetchParentNotifications,
  fetchParentSafety,
  markParentNotificationsRead,
  resetChildFace,
  resetChildPassword,
  resetChildScreenTime,
  resolveAdminReview,
  resolveFollowRequest,
  resolveParentReview,
  unlinkChild,
  updateAdminUserStatus,
  updateParentControls,
  updateTimeLimit,
} from '../src/api/parentAdmin';

interface SeenRequest {
  url: string;
  init: RequestInit;
}

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

function method(index = 0): string {
  return String(seen[index]?.init.method ?? 'GET').toUpperCase();
}

function authz(index = 0): string | null {
  return (seen[index]?.init.headers as Headers)?.get('Authorization') ?? null;
}

describe('parent dashboard and controls contracts', () => {
  it('fetches the dashboard and child controls with the parent bearer <redacted>', async () => {
    stubFetch();
    setUnauthorizedHandler(null);
    nextStatus = 200;
    nextPayload = { ok: true, children: [], unread: 0, pending: [] };
    await fetchParentDashboard('parent-tok');
    assert.equal(seen[0]?.url, 'https://backend.test.invalid/api/mobile/v1/parent/dashboard');
    assert.equal(authz(), 'Bearer parent-tok');

    nextPayload = { ok: true, controls: { allow_reels: true }, time_limit: null, categories: ['STEM'] };
    const controls = await fetchParentControls('parent-tok', 7);
    assert.equal(seen[1]?.url, 'https://backend.test.invalid/api/mobile/v1/parent/controls/7');
    assert.deepEqual(controls.categories, ['STEM']);
  });

  it('saves controls with a PUT of the full controls payload', async () => {
    stubFetch();
    nextStatus = 200;
    nextPayload = { ok: true, controls: { allow_reels: false }, time_limit: null, categories: [] };
    await updateParentControls('parent-tok', 7, {
      allow_reels: false,
      allow_stories: true,
      allow_messaging: false,
      allow_posting: true,
      allow_discover: true,
      quiet_hours_enabled: true,
      quiet_start: '21:00',
      quiet_end: '07:00',
      educational_only_feed: false,
      allowed_categories: ['STEM'],
    });
    assert.equal(seen[0]?.url, 'https://backend.test.invalid/api/mobile/v1/parent/controls/7');
    assert.equal(method(), 'PUT');
    const sent = bodyJson();
    assert.equal(sent.quiet_start, '21:00');
    assert.equal(sent.allow_messaging, false);
    assert.deepEqual(sent.allowed_categories, ['STEM']);
  });

  it('sets, resets, and extends screen-time limits with the documented shapes', async () => {
    stubFetch();
    nextStatus = 200;
    nextPayload = { ok: true, limit: { child_id: 7, daily_limit_minutes: 90, strict_mode: true } };
    await updateTimeLimit('parent-tok', 7, 90, true);
    assert.equal(seen[0]?.url, 'https://backend.test.invalid/api/mobile/v1/parent/time-limit/7');
    assert.equal(method(), 'PUT');
    assert.deepEqual(bodyJson(), { daily_limit_minutes: 90, strict_mode: true });

    nextPayload = { ok: true, message: 'Screen time reset successfully.', minutes_today: 0 };
    const reset = await resetChildScreenTime('parent-tok', 7);
    assert.equal(seen[1]?.url, 'https://backend.test.invalid/api/mobile/v1/parent/time-limit/7/reset');
    assert.equal(method(1), 'POST');
    assert.equal(reset.minutes_today, 0);

    nextPayload = { ok: true, message: 'Added 30 minutes.', daily_limit_minutes: 120 };
    const extended = await extendChildScreenTime('parent-tok', 7, 30);
    assert.equal(seen[2]?.url, 'https://backend.test.invalid/api/mobile/v1/parent/time-limit/7/extend');
    assert.equal(method(2), 'POST');
    assert.deepEqual(bodyJson(2), { additional_minutes: 30 });
    assert.equal(extended.daily_limit_minutes, 120);
  });

  it('reviews safety events with APPROVE/BLOCK actions', async () => {
    stubFetch();
    nextStatus = 200;
    nextPayload = { ok: true, events: [{ event_id: 11, child_id: 7, content_type: 'TEXT', decision: 'REVIEW', status: 'OPEN' }] };
    await fetchParentSafety('parent-tok');
    assert.equal(seen[0]?.url, 'https://backend.test.invalid/api/mobile/v1/parent/safety');

    nextPayload = { ok: true, result: 'APPROVE' };
    await resolveParentReview('parent-tok', 11, 'APPROVE');
    assert.equal(seen[1]?.url, 'https://backend.test.invalid/api/mobile/v1/parent/safety/11');
    assert.equal(method(1), 'POST');
    assert.deepEqual(bodyJson(1), { action: 'APPROVE' });
  });

  it('approves and rejects follow requests with child/target/action ids', async () => {
    stubFetch();
    nextStatus = 200;
    nextPayload = { ok: true, pending: [] };
    await fetchFollowRequests('parent-tok');
    assert.equal(seen[0]?.url, 'https://backend.test.invalid/api/mobile/v1/parent/follow-requests');

    nextPayload = { ok: true, action: 'approve' };
    await resolveFollowRequest('parent-tok', 7, 9, 'approve');
    assert.equal(seen[1]?.url, 'https://backend.test.invalid/api/mobile/v1/parent/follow-requests/action');
    assert.deepEqual(bodyJson(1), { child_id: 7, target_id: 9, action: 'approve' });
  });

  it('reads and marks notifications, and fetches child activity', async () => {
    stubFetch();
    nextStatus = 200;
    nextPayload = { ok: true, notifications: [] };
    await fetchParentNotifications('parent-tok');
    assert.equal(seen[0]?.url, 'https://backend.test.invalid/api/mobile/v1/parent/notifications');
    assert.equal(method(), 'GET');

    await markParentNotificationsRead('parent-tok');
    assert.equal(seen[1]?.url, 'https://backend.test.invalid/api/mobile/v1/parent/notifications');
    assert.equal(method(1), 'POST');

    nextPayload = { ok: true, events: [] };
    await fetchParentActivity('parent-tok', 7);
    assert.equal(seen[2]?.url, 'https://backend.test.invalid/api/mobile/v1/parent/activity/7');

    nextPayload = { ok: true, range_days: 7, summary: { impressions: 4, reel_impressions: 3, watched_ms: 90000, completions: 2, replays: 1, avg_reel_watch_ms: 30000 }, categories: [{ category: 'STEM', views: 3, watched_ms: 60000 }], signals: [] };
    const insights = await fetchParentInsights('parent-tok', 7);
    assert.equal(seen[3]?.url, 'https://backend.test.invalid/api/mobile/v1/parent/insights/7');
    assert.equal(insights.summary.reel_impressions, 3);
  });

  it('propagates parent 403/404 with user-safe messages', async () => {
    stubFetch();
    nextStatus = 403;
    nextPayload = { error: 'forbidden' };
    const err = await resolveFollowRequest('parent-tok', 7, 9, 'approve').catch((error: unknown) => error);
    assert.ok(err instanceof ApiError);
    assert.equal((err as ApiError).status, 403);

    nextStatus = 404;
    nextPayload = { error: 'child_not_found' };
    const missing = await fetchParentControls('parent-tok', 999).catch((error: unknown) => error);
    assert.ok(missing instanceof ApiError);
    assert.match((missing as ApiError).message, /not found/i);
  });

  it('resets the child password with an 8+ char new_password payload', async () => {
    stubFetch();
    nextStatus = 200;
    nextPayload = { ok: true, message: "Child's password updated successfully." };
    const result = await resetChildPassword('parent-tok', 7, 'new-secret-9');
    assert.equal(seen[0]?.url, 'https://backend.test.invalid/api/mobile/v1/parent/child/7/reset-password');
    assert.equal(method(), 'POST');
    assert.equal(authz(), 'Bearer parent-tok');
    assert.deepEqual(bodyJson(), { new_password: 'new-secret-9' });
    assert.match(result.message, /password updated/i);
  });

  it('resets the child face profile with a plain POST', async () => {
    stubFetch();
    nextStatus = 200;
    nextPayload = { ok: true, message: 'Face profile reset successfully' };
    const result = await resetChildFace('parent-tok', 7);
    assert.equal(seen[0]?.url, 'https://backend.test.invalid/api/mobile/v1/parent/child/7/reset-face');
    assert.equal(method(), 'POST');
    assert.ok(result.ok);
  });

  it('enrolls the child face from the parent session with a live photo', async () => {
    stubFetch();
    nextStatus = 200;
    nextPayload = { ok: true, child_id: 7, face_enrolled: true, quiz_required: true };
    const result = await enrollChildFaceByParent('parent-tok', 7, 'aGVsbG8=');
    assert.equal(seen[0]?.url, 'https://backend.test.invalid/api/mobile/v1/parent/children/7/face/enroll');
    assert.equal(method(), 'POST');
    assert.deepEqual(bodyJson(), { photo_b64: 'aGVsbG8=' });
    assert.equal(result.face_enrolled, true);
  });

  it('unlinks the child with a DELETE on the parent child resource', async () => {
    stubFetch();
    nextStatus = 200;
    nextPayload = { ok: true, message: 'child_unlinked' };
    const result = await unlinkChild('parent-tok', 7);
    assert.equal(seen[0]?.url, 'https://backend.test.invalid/api/mobile/v1/parent/child/7');
    assert.equal(method(), 'DELETE');
    assert.equal(result.message, 'child_unlinked');
  });
});

describe('admin client contracts', () => {
  it('fetches dashboard counts, review queue, review detail, audit trail', async () => {
    stubFetch();
    setUnauthorizedHandler(null);
    nextStatus = 200;
    nextPayload = { ok: true, counts: { users: 10, children: 6, parents: 4, open_reviews: 2 } };
    const dash = await fetchAdminDashboard('admin-tok');
    assert.equal(seen[0]?.url, 'https://backend.test.invalid/api/mobile/v1/admin/dashboard');
    assert.equal(authz(), 'Bearer admin-tok');
    assert.equal(dash.counts.open_reviews, 2);

    nextPayload = { ok: true, events: [] };
    await fetchAdminReviews('admin-tok');
    assert.equal(seen[1]?.url, 'https://backend.test.invalid/api/mobile/v1/admin/reviews');

    nextPayload = { ok: true, event: { event_id: 11 }, preview: null };
    await fetchAdminReview('admin-tok', 11);
    assert.equal(seen[2]?.url, 'https://backend.test.invalid/api/mobile/v1/admin/reviews/11');

    nextPayload = { ok: true, events: [] };
    await fetchAdminAudit('admin-tok');
    assert.equal(seen[3]?.url, 'https://backend.test.invalid/api/mobile/v1/admin/audit');
  });

  it('resolves reviews with approve/block/escalate and optional notes', async () => {
    stubFetch();
    nextStatus = 200;
    nextPayload = { ok: true, action: 'APPROVE', status: 'RESOLVED' };
    const approved = await resolveAdminReview('admin-tok', 11, 'APPROVE');
    assert.equal(seen[0]?.url, 'https://backend.test.invalid/api/mobile/v1/admin/reviews/11');
    assert.equal(method(), 'POST');
    assert.deepEqual(bodyJson(), { action: 'APPROVE' });
    assert.equal(approved.status, 'RESOLVED');

    nextPayload = { ok: true, action: 'ESCALATE', status: 'OPEN' };
    const escalated = await resolveAdminReview('admin-tok', 11, 'ESCALATE', 'needs second look');
    assert.deepEqual(bodyJson(1), { action: 'ESCALATE', notes: 'needs second look' });
    assert.equal(escalated.status, 'OPEN');
  });

  it('searches users with q and changes account status', async () => {
    stubFetch();
    nextStatus = 200;
    nextPayload = { ok: true, users: [] };
    await fetchAdminUsers('admin-tok', ' rio ');
    assert.equal(seen[0]?.url, 'https://backend.test.invalid/api/mobile/v1/admin/users?q=rio');

    nextPayload = { ok: true, user_id: 5, status: 'SUSPENDED' };
    const updated = await updateAdminUserStatus('admin-tok', 5, 'SUSPENDED');
    assert.equal(seen[1]?.url, 'https://backend.test.invalid/api/mobile/v1/admin/users/5/status');
    assert.deepEqual(bodyJson(1), { status: 'SUSPENDED' });
    assert.equal(updated.status, 'SUSPENDED');
  });

  it('triggers centralized 401 handling so the session is invalidated locally', async () => {
    stubFetch();
    let handlerCalls = 0;
    setUnauthorizedHandler(() => {
      handlerCalls += 1;
    });
    nextStatus = 401;
    nextPayload = { error: 'mobile_auth_required' };
    const err = await fetchAdminDashboard('stale-tok').catch((error: unknown) => error);
    assert.ok(err instanceof ApiError);
    assert.equal(handlerCalls, 1);
    setUnauthorizedHandler(null);
  });
});
