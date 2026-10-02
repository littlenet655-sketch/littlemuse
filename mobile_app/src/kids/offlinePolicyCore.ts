export type OfflinePolicyGate = 'screen_time' | 'quiet_hours' | null;

export const OFFLINE_POLICY_MAX_AGE_MS = 24 * 60 * 60 * 1000;

export interface OfflinePolicySnapshot {
  strict_mode: boolean;
  remaining_minutes: number | null;
  quiet_hours_enabled: boolean;
  quiet_start: string;
  quiet_end: string;
  server_synced_at_ms: number;
}

function clockMinutes(value: string): number | null {
  const match = /^(\d{1,2}):(\d{2})/.exec(String(value || ''));
  if (!match) return null;
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (!Number.isInteger(hour) || !Number.isInteger(minute) || hour < 0 || hour > 23 || minute < 0 || minute > 59) return null;
  return hour * 60 + minute;
}

export function cachedQuietHoursActive(snapshot: OfflinePolicySnapshot, now = new Date()): boolean {
  if (!snapshot.quiet_hours_enabled) return false;
  const start = clockMinutes(snapshot.quiet_start);
  const end = clockMinutes(snapshot.quiet_end);
  if (start == null || end == null) return true;
  const current = now.getHours() * 60 + now.getMinutes();
  if (start === end) return true;
  return start < end ? current >= start && current < end : current >= start || current < end;
}

export function gateForOfflinePolicy(snapshot: OfflinePolicySnapshot | null, now = new Date()): OfflinePolicyGate {
  if (!snapshot) return 'screen_time';
  const nowMs = now.getTime();
  const syncedAt = Number(snapshot.server_synced_at_ms);
  if (!Number.isFinite(syncedAt) || syncedAt <= 0 || nowMs - syncedAt > OFFLINE_POLICY_MAX_AGE_MS || syncedAt - nowMs > 5 * 60 * 1000) {
    return 'screen_time';
  }
  if (cachedQuietHoursActive(snapshot, now)) return 'quiet_hours';
  if (snapshot.strict_mode && snapshot.remaining_minutes != null && snapshot.remaining_minutes <= 0) return 'screen_time';
  return null;
}
