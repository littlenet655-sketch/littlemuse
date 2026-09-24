import { useEffect, useRef } from 'react';
import { AppState, type AppStateStatus } from 'react-native';
import { useQueryClient } from '@tanstack/react-query';
import { sendHeartbeat } from '../api/kidsFeed';
import { ApiError } from '../api/client';
import { useAuth } from '../auth/AuthProvider';
import { useIsOnline } from '../query/client';
import { kidsKeys } from '../query/keys';
import { shouldRefreshOnboardingForGate } from '../navigation/gates';
import {
  consumeForegroundTime,
  gateForSnapshot,
  loadOfflineTimeSnapshot,
  saveOfflineTimeSnapshot,
  snapshotFromHeartbeat,
  type OfflineTimeSnapshot,
} from './offlineScreenTime';

const HEARTBEAT_INTERVAL_MS = 60000;
const OFFLINE_ACCOUNTING_INTERVAL_MS = 15000;

export function useScreenTimeHeartbeat(onGateChange?: (gate: string | null) => void): void {
  const { session, refreshMe } = useAuth();
  const online = useIsOnline();
  const queryClient = useQueryClient();
  const token = session?.token;
  const childId = session?.user?.user_id;
  const isChild = session?.user?.role === 'CHILD';
  const appStateRef = useRef<AppStateStatus>(AppState.currentState);
  const snapshotRef = useRef<OfflineTimeSnapshot | null>(null);
  const offlineAnchorRef = useRef<number | null>(null);
  const onboardingRef = useRef(session?.onboarding);
  onboardingRef.current = session?.onboarding;
  const refreshMeRef = useRef(refreshMe);
  refreshMeRef.current = refreshMe;

  // Restore the last server-authoritative policy before an offline session can
  // continue. With no trustworthy snapshot, fail closed instead of letting
  // airplane mode become a screen-time bypass.
  useEffect(() => {
    if (!isChild || !childId) return;
    let cancelled = false;
    void loadOfflineTimeSnapshot(childId).then((snapshot) => {
      if (cancelled) return;
      snapshotRef.current = snapshot;
      if (!online) onGateChange?.(gateForSnapshot(snapshot));
    });
    return () => { cancelled = true; };
  }, [childId, isChild, online, onGateChange]);

  // Online path: the backend remains authoritative and every successful
  // heartbeat refreshes the offline policy snapshot.
  useEffect(() => {
    if (!token || !childId || !isChild || !online) return;

    let timer: ReturnType<typeof setInterval> | null = null;
    let abortController: AbortController | null = null;

    async function tick() {
      if (appStateRef.current !== 'active') return;
      abortController = new AbortController();
      try {
        const res = await sendHeartbeat(token!, abortController.signal);
        const snapshot = snapshotFromHeartbeat(childId!, res);
        snapshotRef.current = snapshot;
        await saveOfflineTimeSnapshot(snapshot);
        if (res.locked) {
          onGateChange?.('screen_time');
          void queryClient.invalidateQueries({ queryKey: kidsKeys.home });
        } else {
          onGateChange?.(null);
        }
      } catch (err) {
        if (err instanceof ApiError) {
          if (err.status === 423 || err.gate === 'screen_time' || err.gate === 'quiet_hours') {
            onGateChange?.(err.gate ?? 'screen_time');
            void queryClient.invalidateQueries({ queryKey: kidsKeys.home });
            return;
          }
          if (shouldRefreshOnboardingForGate(err, onboardingRef.current)) {
            try {
              await refreshMeRef.current();
            } catch {
              // Central 401 handling owns re-authentication.
            }
          }
        }
      }
    }

    void tick();
    timer = setInterval(() => { void tick(); }, HEARTBEAT_INTERVAL_MS);

    const subscription = AppState.addEventListener('change', (nextState: AppStateStatus) => {
      const prev = appStateRef.current;
      appStateRef.current = nextState;
      if (prev !== 'active' && nextState === 'active') void tick();
    });

    return () => {
      if (timer) clearInterval(timer);
      abortController?.abort();
      subscription.remove();
    };
  }, [token, childId, isChild, online, queryClient, onGateChange]);

  // Offline path: consume only foreground time from the last authoritative
  // remaining budget and keep quiet-hours enforcement active locally.
  useEffect(() => {
    if (!childId || !isChild || online) {
      offlineAnchorRef.current = null;
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | null = null;

    async function accountNow() {
      if (cancelled || appStateRef.current !== 'active') return;
      let snapshot = snapshotRef.current;
      if (!snapshot) {
        snapshot = await loadOfflineTimeSnapshot(childId!);
        if (cancelled) return;
        snapshotRef.current = snapshot;
      }
      if (!snapshot) {
        onGateChange?.('screen_time');
        return;
      }

      const now = Date.now();
      const anchor = offlineAnchorRef.current ?? now;
      offlineAnchorRef.current = now;
      const next = consumeForegroundTime(snapshot, Math.max(0, now - anchor));
      snapshotRef.current = next;
      await saveOfflineTimeSnapshot(next);
      onGateChange?.(gateForSnapshot(next));
    }

    offlineAnchorRef.current = Date.now();
    void accountNow();
    timer = setInterval(() => { void accountNow(); }, OFFLINE_ACCOUNTING_INTERVAL_MS);

    const subscription = AppState.addEventListener('change', (nextState: AppStateStatus) => {
      const prev = appStateRef.current;
      appStateRef.current = nextState;
      if (prev === 'active' && nextState !== 'active') {
        void accountNow();
        offlineAnchorRef.current = null;
      } else if (prev !== 'active' && nextState === 'active') {
        offlineAnchorRef.current = Date.now();
        void accountNow();
      }
    });

    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
      subscription.remove();
      offlineAnchorRef.current = null;
    };
  }, [childId, isChild, online, onGateChange]);
}
