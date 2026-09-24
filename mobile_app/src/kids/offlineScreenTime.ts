import AsyncStorage from '@react-native-async-storage/async-storage';
import type { HeartbeatResult } from '../api/kidsFeed';

export type OfflineGate = 'screen_time' | 'quiet_hours' | null;

export interface OfflineTimeSnapshot {
  version: 1;
  child_id: number;
  remaining_minutes: number | null;
  daily_limit_minutes: number;
  strict_mode: boolean;
  quiet_hours_enabled: boolean;
  quiet_start: string;
  quiet_end: string;
  saved_at_ms: number;
}

const keyFor = (childId: number) => `littlenet:offline-time:v1:${childId}`;

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
  if (quietHoursActive(snapshot, now)) return 'quiet_hours';
  if (snapshot.strict_mode && snapshot.remaining_minutes != null && snapshot.remaining_minutes <= 0) return 'screen_time';
  return null;
}

export function snapshotFromHeartbeat(childId: number, value: HeartbeatResult): OfflineTimeSnapshot {
  return {
    version: 1,
    child_id: childId,
    remaining_minutes: value.remaining_minutes ?? null,
    daily_limit_minutes: value.daily_limit_minutes ?? 60,
    strict_mode: value.strict_mode ?? true,
    quiet_hours_enabled: Boolean(value.quiet_hours?.enabled),
    quiet_start: value.quiet_hours?.start ?? '21:00',
    quiet_end: value.quiet_hours?.end ?? '07:00',
    saved_at_ms: Date.now(),
  };
}

export async function loadOfflineTimeSnapshot(childId: number): Promise<OfflineTimeSnapshot | null> {
  try {
    const raw = await AsyncStorage.getItem(keyFor(childId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as OfflineTimeSnapshot;
    if (parsed?.version !== 1 || Number(parsed.child_id) !== childId) return null;
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
