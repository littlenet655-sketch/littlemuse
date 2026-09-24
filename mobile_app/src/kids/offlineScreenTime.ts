import AsyncStorage from '@react-native-async-storage/async-storage';
import type { HeartbeatResult } from '../api/kidsFeed';

export type OfflineGate = 'screen_time' | 'quiet_hours' | null;

export const OFFLINE_POLICY_MAX_AGE_MS = 24 * 60 * 60 * 1000;

export interface OfflineTimeSnapshot {
  version: 2;
  child_id: number;
  remaining_minutes: number | null;
  daily_limit_minutes: number;
  strict_mode: boolean;
  quiet_hours_enabled: boolean;
  quiet_start: string;
  quiet_end: string;
  /** Last local persistence/accounting write. */
  saved_at_ms: number;
  /** Last time the policy itself was confirmed by the server. */
  server_synced_at_ms: number;
}

const keyFor = (childId: number) => `littlenet:offline-time:v2:${childId}`;

function clockMinutes(value: string): number | null {
  const match = /^(\d{1,2}):(\d{2})/.exec(String(value || ''));
  if (!match) return null;
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (!Number.isInteger(hour) || !Number.isInteger(minute) || hour < 0 || hour > 23 || minute < 0 || minute > 59) return null;
  return hour * 60 + minute;
}

export function quietHoursActive(snapshot: OfflineTimeSnapshot, now = new Date()): boolean {
  if (!snapshot.quiet_hours_enabled) return false;
  const start = clockMinutes(snapshot.quiet_start);
  const end = clockMinutes(snapshot.quiet_end);
  if (start == null || end == null) return true; // fail closed on malformed cached policy
  const current = now.getHours() * 60 + now.getMinutes();
  if (start === end) return true;
  return start < end ? current >= start && current < end : current >= start || current < end;
}

export function gateForSnapshot(snapshot: OfflineTimeSnapshot | null, now = new Date()): OfflineGate {
  // No authoritative policy means offline Kids Mode cannot prove it is allowed.
  if (!snapshot) return 'screen_time';
  const nowMs = now.getTime();
  const syncedAt = Number(snapshot.server_synced_at_ms);
  // Local foreground accounting must never make an old parent policy look
  // fresh. If the policy is older than 24h (or malformed/far in the future),
  // fail closed until the device reconnects and receives a fresh heartbeat.
  if (!Number.isFinite(syncedAt) || syncedAt <= 0 || nowMs - syncedAt > OFFLINE_POLICY_MAX_AGE_MS || syncedAt - nowMs > 5 * 60 * 1000) {
    return 'screen_time';
  }
  if (quietHoursActive(snapshot, now)) return 'quiet_hours';
  if (snapshot.strict_mode && snapshot.remaining_minutes != null && snapshot.remaining_minutes <= 0) return 'screen_time';
  return null;
}

export function snapshotFromHeartbeat(childId: number, value: HeartbeatResult): OfflineTimeSnapshot {
  const trustedServerTime = value.server_time ? Date.parse(value.server_time) : NaN;
  const confirmedAt = Number.isFinite(trustedServerTime) ? trustedServerTime : Date.now();
  return {
    version: 2,
    child_id: childId,
    remaining_minutes: value.remaining_minutes ?? null,
    daily_limit_minutes: value.daily_limit_minutes ?? 60,
    strict_mode: value.strict_mode ?? true,
    quiet_hours_enabled: Boolean(value.quiet_hours?.enabled),
    quiet_start: value.quiet_hours?.start ?? '21:00',
    quiet_end: value.quiet_hours?.end ?? '07:00',
    saved_at_ms: Date.now(),
    server_synced_at_ms: confirmedAt,
  };
}

export async function loadOfflineTimeSnapshot(childId: number): Promise<OfflineTimeSnapshot | null> {
  try {
    const raw = await AsyncStorage.getItem(keyFor(childId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as OfflineTimeSnapshot;
    if (parsed?.version !== 2 || Number(parsed.child_id) !== childId) return null;
    return parsed;
  } catch {
    return null;
  }
}

export async function saveOfflineTimeSnapshot(snapshot: OfflineTimeSnapshot): Promise<void> {
  await AsyncStorage.setItem(keyFor(snapshot.child_id), JSON.stringify(snapshot));
}

export function consumeForegroundTime(snapshot: OfflineTimeSnapshot, elapsedMs: number): OfflineTimeSnapshot {
  if (snapshot.remaining_minutes == null || elapsedMs <= 0) return { ...snapshot, saved_at_ms: Date.now() };
  const consumedMinutes = elapsedMs / 60000;
  return {
    ...snapshot,
    remaining_minutes: Math.max(0, snapshot.remaining_minutes - consumedMinutes),
    saved_at_ms: Date.now(),
  };
}
