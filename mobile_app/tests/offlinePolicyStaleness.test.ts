import assert from 'node:assert/strict';
import test from 'node:test';
import { gateForOfflinePolicy, OFFLINE_POLICY_MAX_AGE_MS, type OfflinePolicySnapshot } from '../src/kids/offlinePolicyCore';

function snapshot(overrides: Partial<OfflinePolicySnapshot> = {}): OfflinePolicySnapshot {
  const now = Date.now();
  return {
    remaining_minutes: 30,
    strict_mode: true,
    quiet_hours_enabled: false,
    quiet_start: '21:00',
    quiet_end: '07:00',
    server_synced_at_ms: now,
    ...overrides,
  };
}

test('fresh cached parent policy may authorize offline Kids Mode', () => {
  const now = new Date('2026-09-24T10:00:00+05:30');
  const s = snapshot({ server_synced_at_ms: now.getTime() - 60_000 });
  assert.equal(gateForOfflinePolicy(s, now), null);
});

test('stale cached policy fails closed even if local accounting recently saved it', () => {
  const now = new Date('2026-09-24T10:00:00+05:30');
  const s = snapshot({
    server_synced_at_ms: now.getTime() - OFFLINE_POLICY_MAX_AGE_MS - 1,
  });
  assert.equal(gateForOfflinePolicy(s, now), 'screen_time');
});

test('quiet hours remain authoritative while cached policy is fresh', () => {
  const now = new Date('2026-09-24T22:00:00+05:30');
  const s = snapshot({
    quiet_hours_enabled: true,
    quiet_start: '21:00',
    quiet_end: '07:00',
    server_synced_at_ms: now.getTime() - 60_000,
  });
  assert.equal(gateForOfflinePolicy(s, now), 'quiet_hours');
});
