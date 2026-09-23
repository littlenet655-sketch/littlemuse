import { useEffect, useRef } from 'react';
import { AppState, type AppStateStatus } from 'react-native';
import { useQueryClient } from '@tanstack/react-query';
import { sendHeartbeat } from '../api/kidsFeed';
import { ApiError } from '../api/client';
import { useAuth } from '../auth/AuthProvider';
import { useIsOnline } from '../query/client';
import { kidsKeys } from '../query/keys';
import { shouldRefreshOnboardingForGate } from '../navigation/gates';

const HEARTBEAT_INTERVAL_MS = 60000;

export function useScreenTimeHeartbeat(onGateChange?: (gate: string | null) => void): void {
  const { session, refreshMe } = useAuth();
  const online = useIsOnline();
  const queryClient = useQueryClient();
  const token = session?.token;
  const isChild = session?.user?.role === 'CHILD';
  const appStateRef = useRef<AppStateStatus>(AppState.currentState);
  // Refs keep the 30s interval from re-subscribing on every session refresh
  // while still seeing the latest gates.
  const onboardingRef = useRef(session?.onboarding);
  onboardingRef.current = session?.onboarding;
  const refreshMeRef = useRef(refreshMe);
  refreshMeRef.current = refreshMe;

  useEffect(() => {
    if (!token || !isChild || !online) return;

    let timer: ReturnType<typeof setInterval> | null = null;
    let abortController: AbortController | null = null;

    async function tick() {
      if (appStateRef.current !== 'active') return;
      abortController = new AbortController();
      try {
        const res = await sendHeartbeat(token!, abortController.signal);
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
            // 428 quiz gate: pull authoritative gates from /me so the
            // child is routed to Quiz instead of staying stuck.
            try {
              await refreshMeRef.current();
            } catch {
              // A 401 here is handled centrally (local invalidation + re-login).
            }
          }
        }
      }
    }

    // Initial heartbeat on active
    void tick();

    timer = setInterval(() => {
      void tick();
    }, HEARTBEAT_INTERVAL_MS);

    const subscription = AppState.addEventListener('change', (nextState: AppStateStatus) => {
      const prev = appStateRef.current;
      appStateRef.current = nextState;
      if (prev !== 'active' && nextState === 'active') {
        void tick();
      }
    });

    return () => {
      if (timer) clearInterval(timer);
      if (abortController) abortController.abort();
      subscription.remove();
    };
  }, [token, isChild, online, queryClient, onGateChange]);
}
