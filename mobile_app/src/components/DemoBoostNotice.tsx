import { useEffect, useRef, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { Feather } from '@expo/vector-icons';
import { useQuery } from '@tanstack/react-query';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { fetchDemoBoostStatus } from '../api/demoBoost';
import { useAuth } from '../auth/AuthProvider';
import { adminKeys } from '../query/keys';

export function DemoBoostNotice() {
  const { session } = useAuth();
  const insets = useSafeAreaInsets();
  const isAdmin = session?.user.role === 'ADMIN';
  const [message, setMessage] = useState<string | null>(null);
  const wasActive = useRef(false);
  const warnedFive = useRef(false);
  const warnedOne = useRef(false);
  const clearTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const query = useQuery({
    queryKey: adminKeys.demoBoost,
    queryFn: () => fetchDemoBoostStatus(session?.token ?? ''),
    enabled: Boolean(session?.token) && isAdmin,
    // Demo Boost is an admin-only infrastructure control/status. Child and
    // parent sessions must never poll it or see operational boost notices.
    // Boost is normally OFF. Poll slowly while inactive, then tighten the
    // cadence only for the short active window so clients can show expiry
    // warnings without turning this status endpoint into background traffic.
    refetchInterval: (q) => q.state.data?.demo_boost?.active ? 30_000 : 5 * 60_000,
    staleTime: 30_000,
  });

  function show(text: string) {
    setMessage(text);
    if (clearTimer.current) clearTimeout(clearTimer.current);
    clearTimer.current = setTimeout(() => setMessage(null), 8_000);
  }

  useEffect(() => {
    return () => {
      if (clearTimer.current) clearTimeout(clearTimer.current);
    };
  }, []);

  useEffect(() => {
    const boost = query.data?.demo_boost;
    if (!boost) return;

    if (boost.active) {
      wasActive.current = true;
      if (boost.remaining_seconds > 300) {
        warnedFive.current = false;
        warnedOne.current = false;
        return;
      }
      if (boost.remaining_seconds <= 60) {
        if (!warnedOne.current) {
          warnedOne.current = true;
          show('Demo Boost ends in about 1 minute.');
        }
        return;
      }
      if (!warnedFive.current) {
        warnedFive.current = true;
        show('Demo Boost ends in about 5 minutes.');
      }
      return;
    }

    if (wasActive.current) {
      wasActive.current = false;
      warnedFive.current = false;
      warnedOne.current = false;
      show('Demo Boost ended. LittleNet returned to normal low-cost mode.');
    }
  }, [query.data?.demo_boost]);

  if (!isAdmin || !message || !session) return null;

  return (
    <View pointerEvents="none" style={[styles.banner, { top: insets.top + 8 }]}>
      <Feather name="zap" size={15} color="#1D4ED8" />
      <Text style={styles.text}>{message}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    position: 'absolute',
    left: 14,
    right: 14,
    zIndex: 9999,
    elevation: 20,
    minHeight: 42,
    borderRadius: 14,
    backgroundColor: '#EFF6FF',
    borderWidth: 1,
    borderColor: '#BFDBFE',
    paddingHorizontal: 14,
    paddingVertical: 10,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  text: {
    flex: 1,
    color: '#1E3A8A',
    fontSize: 13,
    lineHeight: 18,
    fontWeight: '700',
  },
});
