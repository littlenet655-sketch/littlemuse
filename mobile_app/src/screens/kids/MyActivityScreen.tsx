import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { fetchMyActivity } from '../../api/kidsFeed';
import { useAuth } from '../../auth/AuthProvider';
import type { ChildScreenProps } from '../../navigation/types';
import { kidsKeys } from '../../query/keys';
import { TimeAgo } from '../../ui/social';
import { Card, EmptyState, ErrorState, GateNotice, LoadingState, Screen } from '../../ui/components';
import { colors, spacing, type } from '../../ui/tokens';

/**
 * Read-only "My Activity" for the child: their own recent likes/saves and
 * quiz attempts. The child already sees all of this content in-app; this
 * aggregates it in one place. No parent or sibling data is shown.
 */
export function MyActivityScreen({ navigation }: ChildScreenProps<'MyActivity'>) {
  const { session } = useAuth();
  const query = useQuery({
    queryKey: [...kidsKeys.myActivity, session?.token ?? 'signed-out'],
    enabled: Boolean(session),
    queryFn: () => fetchMyActivity(session!.token),
    staleTime: 60_000,
  });

  if (query.isPending) return <Screen><LoadingState message="Loading your activity…" /></Screen>;
  if (query.isError)
    return (
      <Screen>
        <GateNotice error={query.error} />
        <ErrorState message="Could not load your activity." onRetry={() => void query.refetch()} />
      </Screen>
    );
  const data = query.data;
  const { attempted, correct } = data.quiz_7d;
  const accuracy = attempted > 0 ? Math.round((correct * 100) / attempted) : 0;
  const items = data.liked_saved ?? [];

  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.kicker}>YOUR ACTIVITY</Text>
        <Text style={styles.title}>My Activity</Text>
        <Text style={styles.lead}>Things you've liked, saved, and learned — just for you.</Text>

        <Card>
          <Text style={styles.cardTitle}>Quizzes — last 7 days</Text>
          <Text style={styles.bigValue}>{correct}/{attempted} correct</Text>
          <Text style={styles.body}>{attempted > 0 ? `${accuracy}% accuracy. Nice going!` : 'No quizzes attempted this week yet.'}</Text>
          {data.recent_quizzes.length > 0 ? (
            <View style={styles.quizList}>
              {data.recent_quizzes.slice(0, 5).map((q, i) => (
                <View key={`${q.quiz_id}-${i}`} style={styles.quizRow}>
                  <Text style={[styles.dot, { backgroundColor: q.is_correct ? colors.ok : colors.muted }]} />
                  <Text style={styles.row}>Quiz #{q.quiz_id} — {q.is_correct ? 'correct' : 'try again'}</Text>
                  {q.attempted_at ? <TimeAgo value={q.attempted_at} /> : null}
                </View>
              ))}
            </View>
          ) : null}
        </Card>

        <Card>
          <Text style={styles.cardTitle}>Liked & saved</Text>
          {items.length === 0 ? (
            <EmptyState title="Nothing here yet" body="Like or save posts and reels and they'll show up here." />
          ) : (
            items.slice(0, 20).map((item) => (
              <View key={item.log_id} style={styles.itemRow}>
                <Text style={[styles.dot, { backgroundColor: item.action === 'liked' ? '#E11D48' : colors.brand }]} />
                <View style={styles.itemText}>
                  <Text style={styles.row}>
                    You {item.action} {item.label ?? 'something'}
                  </Text>
                  {item.created_at ? <TimeAgo value={item.created_at} /> : null}
                </View>
              </View>
            ))
          )}
        </Card>
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
  row: { color: colors.ink, fontSize: type.body },
  time: { color: colors.muted, fontSize: type.caption },
  dot: { width: 10, height: 10, borderRadius: 5 },
  quizList: { marginTop: spacing.sm, gap: 6 },
  quizRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  itemRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, paddingVertical: 6 },
  itemText: { flex: 1, gap: 2 },
});
