import { useEffect, useState } from 'react';
import { ActivityIndicator, Alert, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Feather } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { fetchKidsTimeLimitStatus, sendHeartbeat } from '../../api/kidsFeed';
import { useAuth } from '../../auth/AuthProvider';
import { colors, radius, spacing } from '../../ui/tokens';

interface ScreenTimeLockedProps {
  lockType: 'screen_time' | 'quiet_hours';
  onUnlock: () => void;
  onSignOut: () => void;
}

const OFFLINE_ACTIVITIES = [
  { icon: 'edit-3' as const, title: 'Draw or Paint', desc: 'Create a colorful comic or sketch.' },
  { icon: 'book-open' as const, title: 'Read a Book', desc: 'Dive into an exciting chapter or story.' },
  { icon: 'sun' as const, title: 'Play Outside', desc: 'Get fresh air, ride a bike, or play ball.' },
  { icon: 'box' as const, title: 'Build Something', desc: 'Make an epic LEGO or puzzle creation.' },
];

export function ScreenTimeLockedScreen({ lockType, onUnlock, onSignOut }: ScreenTimeLockedProps) {
  const insets = useSafeAreaInsets();
  const { session } = useAuth();
  const [checking, setChecking] = useState(false);
  const isQuiet = lockType === 'quiet_hours';

  useEffect(() => {
    if (!session?.token || isQuiet) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await fetchKidsTimeLimitStatus(session.token);
        if (cancelled) return;
        if (!res.locked) {
          onUnlock();
        }
      } catch {
        // Server is authoritative: a failed status check leaves the lock screen up.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [session?.token, isQuiet, onUnlock]);

  async function handleCheckForTime() {
    if (!session?.token) return;
    setChecking(true);
    try {
      const res = await sendHeartbeat(session.token);
      if (!res.locked) {
        Alert.alert('Unlocked! 🎉', 'Your parent granted more time or quiet hours ended. Welcome back!', [
          { text: 'Let’s Go!', onPress: onUnlock },
        ]);
        return;
      }
      Alert.alert(
        'Still Resting ⏳',
        isQuiet
          ? 'Quiet hours are still active for bedtime. Check back tomorrow morning!'
          : 'Your daily screen-time limit is still reached. Ask your parent in Parent Controls for more time.',
        [{ text: 'OK' }],
      );
    } catch {
      Alert.alert('Notice', 'Could not check time status. Please verify your internet connection.');
    } finally {
      setChecking(false);
    }
  }

  function handleAskParent() {
    Alert.alert(
      'Ask Your Parent 👨‍👩‍👧',
      'Your parent can reset your daily screen time or add bonus minutes instantly from their Parent Controls dashboard.',
      [
        { text: 'Check Status Now', onPress: () => void handleCheckForTime() },
        { text: 'Got It', style: 'cancel' },
      ],
    );
  }

  return (
    <View style={[styles.container, isQuiet ? styles.quietBg : styles.screenTimeBg]}>
      <ScrollView
        contentContainerStyle={[
          styles.scrollContent,
          {
            paddingTop: insets.top + 20,
            paddingBottom: insets.bottom + 24,
          },
        ]}
        showsVerticalScrollIndicator={false}
      >
        {/* Visual Badge / Icon */}
        <View style={styles.badgeShell}>
          <View style={[styles.iconCircle, isQuiet ? styles.quietCircle : styles.screenTimeCircle]}>
            <Feather
              name={isQuiet ? 'moon' : 'clock'}
              size={44}
              color={isQuiet ? '#A78BFA' : '#F59E0B'}
            />
          </View>
          <View style={[styles.statusTag, isQuiet ? styles.quietTag : styles.screenTimeTag]}>
            <Text style={[styles.statusTagText, isQuiet ? styles.quietTagText : styles.screenTimeTagText]}>
              {isQuiet ? 'QUIET HOURS BEDTIME' : 'DAILY TIME LIMIT REACHED'}
            </Text>
          </View>
        </View>

        {/* Hero Title & Encouragement */}
        <Text style={styles.title}>
          {isQuiet ? 'Time for Bedtime! 🌙' : 'Great Job Today! 🌟'}
        </Text>
        <Text style={styles.subtitle}>
          {isQuiet
            ? 'LittleNet is resting for the night so you can get deep, healthy sleep. See you tomorrow!'
            : "You've reached your daily screen-time limit. Taking breaks keeps our eyes and minds healthy and fresh."}
        </Text>

        {/* Offline Activities Suggestions */}
        <View style={styles.offlineSection}>
          <Text style={styles.offlineHeader}>FUN THINGS TO DO OFFLINE 🎨</Text>
          <View style={styles.activityGrid}>
            {OFFLINE_ACTIVITIES.map((act) => (
              <View key={act.title} style={styles.activityCard}>
                <View style={styles.activityIconBox}>
                  <Feather name={act.icon} size={20} color={isQuiet ? '#A78BFA' : '#0284C7'} />
                </View>
                <Text style={styles.activityTitle}>{act.title}</Text>
                <Text style={styles.activityDesc}>{act.desc}</Text>
              </View>
            ))}
          </View>
        </View>

        {/* Actions */}
        <View style={styles.actions}>
          {!isQuiet && (
            <Pressable
              style={({ pressed }) => [
                styles.primaryBtn,
                pressed && styles.btnPressed,
              ]}
              onPress={handleAskParent}
              accessibilityRole="button"
              accessibilityLabel="Ask parent for more time"
            >
              <Feather name="heart" size={18} color="#FFFFFF" />
              <Text style={styles.primaryBtnText}>Ask Parent for More Time</Text>
            </Pressable>
          )}

          <Pressable
            style={({ pressed }) => [styles.secondaryBtn, pressed && styles.btnPressed]}
            onPress={() => void handleCheckForTime()}
            disabled={checking}
            accessibilityRole="button"
            accessibilityLabel="Check for extra time"
          >
            {checking ? (
              <ActivityIndicator color={isQuiet ? '#E2E8F0' : colors.ink} size="small" />
            ) : (
              <>
                <Feather name="refresh-cw" size={16} color={isQuiet ? '#E2E8F0' : colors.ink} />
                <Text style={[styles.secondaryBtnText, isQuiet && styles.quietBtnText]}>
                  Check if Parent Added Time
                </Text>
              </>
            )}
          </Pressable>

          <Pressable
            style={({ pressed }) => [styles.textBtn, pressed && styles.btnPressed]}
            onPress={onSignOut}
            accessibilityRole="button"
            accessibilityLabel="Log out"
          >
            <Feather name="log-out" size={15} color={isQuiet ? '#94A3B8' : '#64748B'} />
            <Text style={[styles.textBtnLabel, isQuiet && styles.quietMuted]}>Log out for now</Text>
          </Pressable>
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  screenTimeBg: {
    backgroundColor: '#F8FAFC',
  },
  quietBg: {
    backgroundColor: '#0F172A',
  },
  scrollContent: {
    paddingHorizontal: 20,
    paddingTop: 44,
    paddingBottom: 36,
    alignItems: 'center',
  },
  badgeShell: {
    alignItems: 'center',
    marginBottom: 16,
  },
  iconCircle: {
    width: 84,
    height: 84,
    borderRadius: 42,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 10,
  },
  screenTimeCircle: {
    backgroundColor: '#FEF3C7',
    borderWidth: 3,
    borderColor: '#FDE68A',
  },
  quietCircle: {
    backgroundColor: '#1E1B4B',
    borderWidth: 3,
    borderColor: '#312E81',
  },
  statusTag: {
    paddingHorizontal: 12,
    paddingVertical: 5,
    borderRadius: 20,
  },
  screenTimeTag: {
    backgroundColor: '#FDE68A',
  },
  quietTag: {
    backgroundColor: '#312E81',
  },
  statusTagText: {
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 0.5,
  },
  screenTimeTagText: {
    color: '#92400E',
  },
  quietTagText: {
    color: '#C4B5FD',
  },
  title: {
    fontSize: 25,
    fontWeight: '900',
    textAlign: 'center',
    color: colors.ink,
    marginBottom: 6,
  },
  subtitle: {
    fontSize: 13,
    lineHeight: 19,
    textAlign: 'center',
    color: '#64748B',
    maxWidth: 320,
    marginBottom: 20,
  },
  selfResetCard: {
    width: '100%',
    backgroundColor: '#FFFBEB',
    borderWidth: 1.5,
    borderColor: '#FDE68A',
    borderRadius: 16,
    padding: 16,
    marginBottom: 20,
  },
  selfResetTopRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  selfResetBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: '#FEF3C7',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 8,
  },
  selfResetBadgeText: {
    color: '#B45309',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 0.5,
  },
  selfResetCountText: {
    color: '#92400E',
    fontSize: 13,
    fontWeight: '800',
  },
  selfResetDescription: {
    fontSize: 12,
    lineHeight: 17,
    color: '#78350F',
    marginBottom: 12,
  },
  selfResetBtn: {
    backgroundColor: '#D97706',
    borderRadius: 12,
    paddingVertical: 12,
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 8,
  },
  selfResetBtnText: {
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: '800',
  },
  exhaustedBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: '#FEF2F2',
    borderWidth: 1,
    borderColor: '#FECACA',
    borderRadius: 10,
    padding: 10,
    marginTop: 4,
  },
  exhaustedText: {
    flex: 1,
    fontSize: 12,
    color: '#991B1B',
    lineHeight: 16,
    fontWeight: '600',
  },
  offlineSection: {
    width: '100%',
    marginBottom: 24,
  },
  offlineHeader: {
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 0.5,
    color: '#94A3B8',
    marginBottom: 10,
    textAlign: 'center',
  },
  activityGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  activityCard: {
    width: '48%',
    backgroundColor: '#FFFFFF',
    borderRadius: 14,
    padding: 12,
    borderWidth: 1,
    borderColor: '#E2E8F0',
  },
  activityIconBox: {
    width: 32,
    height: 32,
    borderRadius: 8,
    backgroundColor: '#F1F5F9',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 8,
  },
  activityTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.ink,
    marginBottom: 2,
  },
  activityDesc: {
    fontSize: 11,
    color: '#64748B',
    lineHeight: 15,
  },
  actions: {
    width: '100%',
    gap: 10,
    alignItems: 'center',
  },
  primaryBtn: {
    width: '100%',
    height: 48,
    borderRadius: radius.md,
    backgroundColor: colors.brand,
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 8,
  },
  primaryBtnHighlight: {
    backgroundColor: '#2563EB',
  },
  primaryBtnText: {
    color: '#FFFFFF',
    fontSize: 15,
    fontWeight: '800',
  },
  secondaryBtn: {
    width: '100%',
    height: 46,
    borderRadius: radius.md,
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#CBD5E1',
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 8,
  },
  secondaryBtnText: {
    color: colors.ink,
    fontSize: 14,
    fontWeight: '700',
  },
  quietBtnText: {
    color: '#0F172A',
  },
  textBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingVertical: 8,
    paddingHorizontal: 12,
  },
  textBtnLabel: {
    fontSize: 13,
    fontWeight: '600',
    color: '#64748B',
  },
  quietMuted: {
    color: '#94A3B8',
  },
  btnPressed: {
    opacity: 0.8,
  },
});
