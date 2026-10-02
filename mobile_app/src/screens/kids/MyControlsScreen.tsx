import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { fetchMyControls, type KidFeatureFlags } from '../../api/kidsFeed';
import { useAuth } from '../../auth/AuthProvider';
import type { ChildScreenProps } from '../../navigation/types';
import { kidsKeys } from '../../query/keys';
import { Card, ErrorState, GateNotice, LoadingState, Notice, Screen } from '../../ui/components';
import { colors, radius, spacing, type } from '../../ui/tokens';

const FEATURE_LABELS: Array<[keyof KidFeatureFlags, string]> = [
  ['reels', 'Reels'],
  ['stories', 'Stories'],
  ['messaging', 'Messaging'],
  ['posting', 'Posting'],
  ['discover', 'Discover'],
  ['comments', 'Comments'],
];

function safetyCopy(level: string): string {
  switch ((level || '').toUpperCase()) {
    case 'STRICT':
      return 'Strict — the strongest protections are on for your account.';
    case 'MODERATE':
      return 'Moderate — balanced protections chosen for you.';
    case 'LENIENT':
      return 'Lenient — lighter protections chosen for you.';
    default:
      return 'Your safety level is set and enforced for your account.';
  }
}

/**
 * Read-only "My Controls" for the child: their own safety level, screen-time
 * limit, quiet hours, and enabled features. Nothing here can be changed —
 * everything stays parent-managed and server-enforced.
 */
export function MyControlsScreen({ navigation }: ChildScreenProps<'MyControls'>) {
  const { session } = useAuth();
  const query = useQuery({
    queryKey: [...kidsKeys.myControls, session?.token ?? 'signed-out'],
    enabled: Boolean(session),
    queryFn: () => fetchMyControls(session!.token),
    staleTime: 60_000,
  });

  if (query.isPending) return <Screen><LoadingState message="Loading your controls…" /></Screen>;
  if (query.isError)
    return (
      <Screen>
        <GateNotice error={query.error} />
        <ErrorState message="Could not load your controls." onRetry={() => void query.refetch()} />
      </Screen>
    );
  const data = query.data;

  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.kicker}>READ ONLY</Text>
        <Text style={styles.title}>My Controls</Text>
        <Text style={styles.lead}>These are your parent's rules for your account. They are enforced by LittleNet — you can't change them here.</Text>

        <Card>
          <Text style={styles.cardTitle}>Safety level</Text>
          <Text style={styles.bigValue}>{data.safety_level}</Text>
          <Text style={styles.body}>{safetyCopy(data.safety_level)}</Text>
        </Card>

        <Card>
          <Text style={styles.cardTitle}>Screen time</Text>
          <Text style={styles.row}>Daily limit: <Text style={styles.bold}>{data.daily_limit_minutes} min</Text></Text>
          <Text style={styles.row}>Strict mode: <Text style={styles.bold}>{data.strict_mode ? 'On' : 'Off'}</Text></Text>
          {data.educational_only_feed ? (
            <View style={styles.noteBox}>
              <Text style={styles.noteText}>Educational-only feed is on — your feed shows learning content.</Text>
            </View>
          ) : null}
        </Card>

        <Card>
          <Text style={styles.cardTitle}>Quiet hours</Text>
          {data.quiet_hours.enabled ? (
            <>
              <Text style={styles.row}>
                {data.quiet_hours.start} – {data.quiet_hours.end}
                {data.quiet_hours.active ? ' · active now' : ''}
              </Text>
              <Text style={styles.body}>During quiet hours the app rests — new sessions stay locked until morning.</Text>
            </>
          ) : (
            <Text style={styles.body}>Quiet hours are off.</Text>
          )}
        </Card>

        <Card>
          <Text style={styles.cardTitle}>Features allowed for you</Text>
          {FEATURE_LABELS.map(([key, label]) => {
            const on = data.features[key];
            return (
              <View key={key} style={styles.featureRow}>
                <Text style={[styles.dot, { backgroundColor: on ? colors.ok : colors.muted }]} />
                <Text style={styles.row}>{label}</Text>
                <Text style={[styles.row, styles.featureState]}>{on ? 'On' : 'Off'}</Text>
              </View>
            );
          })}
        </Card>

        <Notice tone="info" message="Want a rule changed? Ask your parent — only they can update these." />
        <View style={{ height: spacing.md }} />
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { padding: spacing.lg, gap: spacing.md },
  kicker: { color: colors.muted, fontSize: type.caption, letterSpacing: 1.5 },
  title: { color: colors.ink, fontSize: type.title, fontWeight: '700' },
  lead: { color: colors.muted, fontSize: type.body },
  cardTitle: { color: colors.ink, fontWeight: '700', fontSize: type.subtitle, marginBottom: spacing.xs },
  bigValue: { color: colors.brand, fontWeight: '700', fontSize: type.hero, marginBottom: spacing.xs },
  body: { color: colors.muted, fontSize: type.body },
  row: { color: colors.ink, fontSize: type.body, marginBottom: 2 },
  bold: { fontWeight: '700' },
  featureRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, paddingVertical: 6 },
  dot: { width: 10, height: 10, borderRadius: 5 },
  featureState: { marginLeft: 'auto', color: colors.muted },
  noteBox: { marginTop: spacing.sm, backgroundColor: '#F0F9FF', borderRadius: radius.md, padding: spacing.sm },
  noteText: { color: '#0369A1', fontSize: type.body },
});
