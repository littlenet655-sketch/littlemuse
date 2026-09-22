/// <reference types="node" />
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

process.env.EXPO_PUBLIC_API_BASE_URL = 'https://backend.test.invalid';

import {
  fetchAdminAudit,
  fetchAdminReview,
  fetchAdminReviews,
  fetchAdminUsers,
  fetchParentActivity,
  fetchParentInsights,
  fetchParentControls,
  fetchParentDashboard,
  fetchParentNotifications,
  fetchParentSafety,
  markParentNotificationsRead,
  resolveAdminReview,
  resolveFollowRequest,
  resolveParentReview,
  updateAdminUserStatus,
  updateParentControls,
  updateTimeLimit,
  type ParentControls,
} from '../src/api/parentAdmin';

let seen: Array<{ url: string; init: RequestInit }> = [];
let response: unknown = { ok: true };

function stubFetch(payload: unknown = { ok: true }) {
  response = payload;
  seen = [];
  (globalThis as unknown as Record<string, unknown>).fetch = async (url: unknown, init?: RequestInit) => {
    seen.push({ url: String(url), init: init ?? {} });
    return { ok: true, status: 200, json: async () => response };
  };
}

const controls: ParentControls = {
  allow_reels: true,
  allow_stories: true,
  allow_messaging: false,
  allow_posting: true,
  allow_discover: true,
  quiet_hours_enabled: true,
  quiet_start: '21:00',
  quiet_end: '07:00',
  educational_only_feed: false,
  allowed_categories: ['Science', 'Books'],
};

function sentBody(index = 0): Record<string, unknown> {
  return JSON.parse(String(seen[index]?.init.body ?? '{}')) as Record<string, unknown>;
}

describe('Agent D Parent contracts', () => {
  it('loads every bounded Parent collection from its bearer route', async () => {
    stubFetch({ ok: true, children: [], unread: 0, pending: [] });
    await fetchParentDashboard('tok');
    response = { ok: true, events: [] };
    await fetchParentSafety('tok');
    await fetchParentActivity('tok', 22);
    response = { ok: true, range_days: 7, summary: { impressions: 0, reel_impressions: 0, watched_ms: 0, completions: 0, replays: 0, avg_reel_watch_ms: 0 }, categories: [], signals: [] };
    await fetchParentInsights('tok', 22);
    response = { ok: true, notifications: [] };
    await fetchParentNotifications('tok');
    assert.deepEqual(seen.map((call) => new URL(call.url).pathname), [
      '/api/mobile/v1/parent/dashboard',
      '/api/mobile/v1/parent/safety',
      '/api/mobile/v1/parent/activity/22',
      '/api/mobile/v1/parent/insights/22',
      '/api/mobile/v1/parent/notifications',
    ]);
    assert.ok(seen.every((call) => new Headers(call.init.headers).get('Authorization') === 'Bearer tok'));
  });

  it('updates exact feature/category and quiet-hour control names', async () => {
    stubFetch({ ok: true, controls, time_limit: null, categories: [] });
    await fetchParentControls('tok', 22);
    await updateParentControls('tok', 22, controls);
    assert.equal(seen[1]?.init.method, 'PUT');
    assert.deepEqual(sentBody(1), controls);
  });

  it('updates server screen-time enforcement with a strict boolean', async () => {
    stubFetch({ ok: true, limit: { child_id: 22, daily_limit_minutes: 75, strict_mode: true } });
    await updateTimeLimit('tok', 22, 75, true);
    assert.equal(seen[0]?.init.method, 'PUT');
    assert.deepEqual(sentBody(), { daily_limit_minutes: 75, strict_mode: true });
  });

  it('uses authoritative Parent review and two-parent follow actions', async () => {
    stubFetch({ ok: true, result: 'APPROVE' });
    await resolveParentReview('tok', 9, 'APPROVE');
    response = { ok: true, action: 'reject' };
    await resolveFollowRequest('tok', 22, 33, 'reject');
    assert.deepEqual(sentBody(0), { action: 'APPROVE' });
    assert.deepEqual(sentBody(1), { child_id: 22, target_id: 33, action: 'reject' });
  });

  it('marks Parent notifications read through the authenticated POST contract', async () => {
    stubFetch({ ok: true, notifications: [] });
    await markParentNotificationsRead('tok');
    assert.equal(seen[0]?.init.method, 'POST');
    assert.deepEqual(sentBody(), {});
  });
});

describe('Agent D Admin contracts', () => {
  it('loads queue, detail, bounded user search and dedicated audit history', async () => {
    stubFetch({ ok: true, events: [] });
    await fetchAdminReviews('tok');
    response = { ok: true, event: {}, preview: null };
    await fetchAdminReview('tok', 4);
    response = { ok: true, users: [] };
    await fetchAdminUsers('tok', 'A Parent+Child');
    response = { ok: true, events: [] };
    await fetchAdminAudit('tok');
    assert.equal(seen[0]?.url.endsWith('/api/mobile/v1/admin/reviews'), true);
    assert.equal(seen[1]?.url.endsWith('/api/mobile/v1/admin/reviews/4'), true);
    assert.equal(seen[2]?.url.endsWith('/api/mobile/v1/admin/users?q=A%20Parent%2BChild'), true);
    assert.equal(seen[3]?.url.endsWith('/api/mobile/v1/admin/audit'), true);
  });

  it('sends exact approve, block and escalation semantics', async () => {
    stubFetch({ ok: true, action: 'ESCALATE', status: 'OPEN' });
    await resolveAdminReview('tok', 4, 'ESCALATE', 'Needs specialist');
    assert.deepEqual(sentBody(), { action: 'ESCALATE', notes: 'Needs specialist' });
  });

  it('changes only supported account statuses', async () => {
    stubFetch({ ok: true, user_id: 7, status: 'SUSPENDED' });
    await updateAdminUserStatus('tok', 7, 'SUSPENDED');
    assert.deepEqual(sentBody(), { status: 'SUSPENDED' });
    assert.equal(seen[0]?.url.endsWith('/api/mobile/v1/admin/users/7/status'), true);
  });
});
