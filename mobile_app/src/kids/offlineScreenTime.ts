import AsyncStorage from '@react-native-async-storage/async-storage';
import type { HeartbeatResult } from '../api/kidsFeed';
import {
  OFFLINE_POLICY_MAX_AGE_MS,
  cachedQuietHoursActive,
  gateForOfflinePolicy,
} from './offlinePolicyCore';

export type OfflineGate = 'screen_time' | 'quiet_hours' | null;
export { OFFLINE_POLICY_MAX_AGE_MS };

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

export function quietHoursActive(snapshot: OfflineTimeSnapshot, now = new Date()): boolean {
  return cachedQuietHoursActive(snapshot, now);
}

export function gateForSnapshot(snapshot: OfflineTimeSnapshot | null, now = new Date()): OfflineGate {
  return gateForOfflinePolicy(snapshot, now);
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
