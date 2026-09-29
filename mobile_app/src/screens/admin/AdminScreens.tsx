import { useState } from 'react';
import { Alert, FlatList, Image, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Feather } from '@expo/vector-icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  deactivateAdminUser,
  fetchAdminAudit,
  fetchAdminDashboard,
  fetchAdminReview,
  fetchAdminReviews,
  fetchAdminUsers,
  resolveAdminReview,
  updateAdminUserStatus,
} from '../../api/parentAdmin';
import {
  extendDemoBoost,
  fetchDemoBoostStatus,
  startDemoBoost,
  stopDemoBoost,
} from '../../api/demoBoost';
import { useAuth } from '../../auth/AuthProvider';
import { VideoMedia } from '../../kids/VideoMedia';
import type { AdminScreenProps } from '../../navigation/types';
import { useIsOnline } from '../../query/client';
import { adminKeys } from '../../query/keys';
import { BrandHeader, Button, Card, EmptyState, ErrorState, Field, LoadingState, Notice, OfflineBanner, Screen, errorText } from '../../ui/components';
import { CategoryBadge, TimeAgo } from '../../ui/social';
import { colors, radius, spacing, type } from '../../ui/tokens';

function Metric({ value, label, alert = false }: { value: number; label: string; alert?: boolean }) {
  return <View style={[styles.metric, alert && styles.alertMetric]}><Text style={styles.metricValue}>{value}</Text><Text style={styles.muted}>{label}</Text></View>;
}

function DemoBoostCard() {
  const { session } = useAuth();
  const client = useQueryClient();
  const query = useQuery({
    queryKey: adminKeys.demoBoost,
    queryFn: () => fetchDemoBoostStatus(session?.token ?? ''),
    enabled: Boolean(session),
    refetchInterval: 15_000,
  });
  const refresh = async () => {
    await client.invalidateQueries({ queryKey: adminKeys.demoBoost });
  };
  const startBoost = useMutation({
    mutationFn: (minutes: 15 | 30 | 60) => startDemoBoost(session?.token ?? '', minutes),
    onSuccess: refresh,
  });
  const extendBoost = useMutation({
    mutationFn: (minutes: 5 | 15 | 30) => extendDemoBoost(session?.token ?? '', minutes),
    onSuccess: refresh,
  });
  const stopBoost = useMutation({
    mutationFn: () => stopDemoBoost(session?.token ?? ''),
    onSuccess: refresh,
  });
  const boost = query.data?.demo_boost;
  const busy = startBoost.isPending || extendBoost.isPending || stopBoost.isPending;
  const remainingMinutes = Math.max(0, Math.ceil((boost?.remaining_seconds ?? 0) / 60));
  const actionError = startBoost.error || extendBoost.error || stopBoost.error;

  return (
    <Card>
      <View style={styles.rowBetween}>
        <View style={styles.flex}>
          <Text style={styles.title}>Demo Boost</Text>
          <Text style={styles.muted}>Temporarily warms one capped AI worker for a smoother college demo.</Text>
        </View>
        <View style={[styles.boostBadge, boost?.active && styles.boostBadgeActive]}>
          <Text style={[styles.boostBadgeText, boost?.active && styles.boostBadgeTextActive]}>
            {boost?.status ?? 'OFF'}
          </Text>
        </View>
      </View>

      {query.isPending ? <LoadingState message="Checking Demo Boost…" /> : null}
      {query.isError ? <Notice message={errorText(query.error, 'Demo Boost status unavailable.')} /> : null}

      {boost?.active ? (
        <>
          <Text style={styles.boostTime}>{remainingMinutes} min remaining</Text>
          <Text style={styles.muted}>
            {boost.status === 'READY' ? 'AI warmup is ready.' : 'AI models are warming in the background.'}
          </Text>
          {boost.last_error ? <Notice message="Warmup is still retryable. Normal LittleNet remains available." /> : null}
          {boost.remaining_seconds <= 300 ? (
            <>
              <Text style={styles.boostSectionLabel}>EXTEND DEMO</Text>
              <View style={styles.boostActionRow}>
                {([5, 15, 30] as const).map((minutes) => (
                  <Pressable
                    key={minutes}
                    style={styles.boostMiniButton}
                    disabled={busy}
                    onPress={() => extendBoost.mutate(minutes)}
                    accessibilityRole="button"
                    accessibilityLabel={`Extend Demo Boost by ${minutes} minutes`}
                  >
                    <Text style={styles.boostMiniButtonText}>+{minutes}m</Text>
                  </Pressable>
                ))}
              </View>
            </>
          ) : null}
          <Button label="Stop Demo Boost" variant="secondary" disabled={busy} onPress={() => stopBoost.mutate()} />
        </>
      ) : (
        <>
          <Text style={styles.boostSectionLabel}>START FOR</Text>
          <View style={styles.boostActionRow}>
            {([15, 30, 60] as const).map((minutes) => (
              <Pressable
                key={minutes}
                style={styles.boostMiniButton}
                disabled={busy || !session}
                onPress={() => startBoost.mutate(minutes)}
                accessibilityRole="button"
                accessibilityLabel={`Start Demo Boost for ${minutes} minutes`}
              >
                <Text style={styles.boostMiniButtonText}>{minutes}m</Text>
              </Pressable>
            ))}
          </View>
        </>
      )}
      {actionError ? <Notice message={errorText(actionError, 'Could not change Demo Boost.')} /> : null}
    </Card>
  );
}

export function AdminHomeScreen({ navigation }: AdminScreenProps<'AdminHome'>) {
  const { session, signOut } = useAuth();
  const online = useIsOnline();
  const query = useQuery({
    queryKey: adminKeys.dashboard,
    queryFn: () => fetchAdminDashboard(session?.token ?? ''),
    enabled: Boolean(session),
  });
  const counts = query.data?.counts;

  return (
    <Screen>
      <ScrollView
        refreshControl={
          <RefreshControl
            refreshing={query.isRefetching}
            onRefresh={() => void Promise.all([query.refetch()])}
          />
        }
      >
        <OfflineBanner online={online} />
        <BrandHeader
          title="Admin dashboard"
          subtitle="Lightweight account overview and demo controls."
        />
        {query.isPending ? (
          <LoadingState message="Loading account totals…" />
        ) : query.isError ? (
          <ErrorState message={errorText(query.error)} onRetry={() => void query.refetch()} />
        ) : (
          <View style={styles.metrics}>
            <Metric value={counts?.signups_today ?? 0} label="Signups today" />
            <Metric value={counts?.children ?? 0} label="Children" />
            <Metric value={counts?.parents ?? 0} label="Parents" />
          </View>
        )}

        <DemoBoostCard />
        <Menu label="Manage accounts" body="Search, pause or reactivate accounts" onPress={() => navigation.navigate('AdminUsers')} />
        <Menu label="Admin activity" body="See recent account actions" onPress={() => navigation.navigate('AdminAudit')} />
        <Button label="Log out" variant="secondary" onPress={() => void signOut()} />
      </ScrollView>
    </Screen>
  );
}

function Menu({ label, body, onPress }: { label: string; body: string; onPress: () => void }) {
  return <Pressable accessibilityRole="button" style={styles.menu} onPress={onPress}><Text style={styles.title}>{label}</Text><Text style={styles.muted}>{body}</Text></Pressable>;
}

export function AdminReviewsScreen({ navigation }: AdminScreenProps<'AdminReviews'>) {
  const { session } = useAuth();
  const query = useQuery({ queryKey: adminKeys.reviews, queryFn: () => fetchAdminReviews(session?.token ?? ''), enabled: Boolean(session) });
  const events = query.data?.events ?? [];
  return <Screen><FlatList data={events} keyExtractor={(event) => String(event.event_id)} refreshControl={<RefreshControl refreshing={query.isRefetching} onRefresh={() => void query.refetch()} />} ListHeaderComponent={<BrandHeader title="Moderation queue" subtitle="The server returns at most 100 open REVIEW events, newest first." />} ListEmptyComponent={query.isPending ? <LoadingState message="Loading review queue…" /> : query.isError ? <ErrorState message={errorText(query.error)} onRetry={() => void query.refetch()} /> : <EmptyState title="Moderation queue clear" body="Open review events will appear here." />} renderItem={({ item: event }) => <Pressable accessibilityRole="button" style={[styles.menu, Number(event.risk_score) >= 0.7 && styles.highRiskMenu]} onPress={() => navigation.navigate('AdminReview', { eventId: event.event_id })}><View style={styles.rowBetween}><CategoryBadge label={event.content_type} /><TimeAgo value={event.created_at} /></View><Text style={styles.title}>{event.full_name ?? event.username ?? `Child ${event.child_id}`}</Text><Text style={styles.body}>{event.reason || 'Requires moderator review'}</Text><Text style={styles.muted}>Risk evidence: {String(event.risk_score ?? 'not provided')} · {event.preview?.media_type ? humanize(event.preview.media_type) : 'text summary'}</Text></Pressable>} /></Screen>;
}

export function AdminReviewScreen({ navigation, route }: AdminScreenProps<'AdminReview'>) {
  const { session } = useAuth();
  const client = useQueryClient();
  const [notes, setNotes] = useState('');
  const query = useQuery({ queryKey: adminKeys.review(route.params.eventId), queryFn: () => fetchAdminReview(session?.token ?? '', route.params.eventId), enabled: Boolean(session) });
  const mutation = useMutation({
    mutationFn: (action: 'APPROVE' | 'BLOCK' | 'ESCALATE') => resolveAdminReview(session?.token ?? '', route.params.eventId, action, notes),
    onSuccess: async (result) => {
      await Promise.all([client.invalidateQueries({ queryKey: adminKeys.reviews }), client.invalidateQueries({ queryKey: adminKeys.dashboard }), client.invalidateQueries({ queryKey: adminKeys.audit }), client.invalidateQueries({ queryKey: adminKeys.review(route.params.eventId) })]);
      if (result.status === 'RESOLVED') navigation.goBack();
    },
  });
  if (query.isPending) return <Screen><LoadingState message="Loading review detail…" /></Screen>;
  if (query.isError || !query.data) return <Screen><ErrorState message={errorText(query.error, 'Review unavailable.')} onRetry={() => void query.refetch()} /></Screen>;
  const { event, preview } = query.data;
  const isVideo = (preview?.media_type ?? '').toUpperCase() === 'VIDEO';
  const previewImage = !isVideo ? preview?.media_url : preview?.poster_url;
  return <Screen><ScrollView><BrandHeader title="Moderation detail" subtitle="Final actions are confirmed by the backend and recorded in the audit history." /><Card><View style={styles.rowBetween}><CategoryBadge label={event.content_type} /><TimeAgo value={event.created_at} /></View><Text style={styles.title}>{event.full_name ?? event.username ?? `Child ${event.child_id}`}</Text>{isVideo && preview?.media_url ? <View style={styles.videoPreviewWrapper}><VideoMedia source={preview.media_url} posterUrl={preview.poster_url} height={300} /><View style={styles.quarantineBadge}><Feather name="shield" size={12} color="#FFFFFF" /><Text style={styles.quarantineBadgeText}>QUARANTINE PREVIEW • LittleNet Safety Review</Text></View></View> : null}{previewImage && !isVideo ? <Image source={{ uri: previewImage, headers: { Authorization: `Bearer ${session?.token ?? ''}` } }} resizeMode="cover" style={styles.preview} /> : null}{preview?.caption ? <Text style={styles.body}>{preview.caption}</Text> : null}{preview?.comment_text ? <Text style={styles.body}>{preview.comment_text}</Text> : null}{preview?.message_text ? <Text style={styles.body}>{preview.message_text}</Text> : null}<Text style={styles.body}>{event.reason || 'No public-facing reason supplied.'}</Text><Text style={styles.muted}>Status: {event.status} · decision: {event.decision} · risk: {String(event.risk_score ?? 'not provided')}</Text><Field label="Moderator notes (optional)" value={notes} onChangeText={setNotes} multiline />{mutation.error ? <Notice message={errorText(mutation.error)} /> : null}{mutation.isSuccess && mutation.data.status === 'OPEN' ? <Notice tone="ok" message="Escalation recorded. This event remains open for a final decision." /> : null}<Button label="Approve" loading={mutation.isPending} onPress={() => mutation.mutate('APPROVE')} /><Button label="Block" variant="secondary" disabled={mutation.isPending} onPress={() => mutation.mutate('BLOCK')} /><Button label="Escalate" variant="secondary" disabled={mutation.isPending} onPress={() => mutation.mutate('ESCALATE')} /></Card></ScrollView></Screen>;
}

export function AdminUsersScreen(_props: AdminScreenProps<'AdminUsers'>) {
  const { session } = useAuth();
  const client = useQueryClient();
  const [input, setInput] = useState('');
  const [queryText, setQueryText] = useState('');
  const query = useQuery({ queryKey: adminKeys.users(queryText), queryFn: () => fetchAdminUsers(session?.token ?? '', queryText), enabled: Boolean(session) });
  const mutation = useMutation({
    mutationFn: ({ userId, status }: { userId: number; status: 'ACTIVE' | 'SUSPENDED' }) =>
      updateAdminUserStatus(session?.token ?? '', userId, status),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ['admin', 'users'] }),
        client.invalidateQueries({ queryKey: adminKeys.dashboard }),
        client.invalidateQueries({ queryKey: adminKeys.audit }),
      ]);
    },
  });
  const deleteMutation = useMutation({
    mutationFn: (userId: number) => deactivateAdminUser(session?.token ?? '', userId),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ['admin', 'users'] }),
        client.invalidateQueries({ queryKey: adminKeys.dashboard }),
        client.invalidateQueries({ queryKey: adminKeys.audit }),
      ]);
    },
  });
  const users = query.data?.users ?? [];
  /** Only ACTIVE/SUSPENDED are togglable from mobile. Activating a pending or
      deactivated account could bypass its verification flow, so those stay read-only. */
  function confirmDelete(user: { user_id: number; full_name?: string }) {
    Alert.alert(
      'Delete account?',
      `This will deactivate ${user.full_name || 'this account'} and sign it out on all devices.`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: () => deleteMutation.mutate(user.user_id),
        },
      ],
    );
  }

  function accountAction(user: { user_id: number; full_name?: string; role: string; account_status: string }) {
    if (user.role === 'ADMIN') return <Notice tone="info" message="Admin accounts cannot be changed from mobile lookup." />;
    if (user.account_status === 'DEACTIVATED') {
      return <Notice tone="info" message="This account is deleted/deactivated." />;
    }
    return (
      <>
        {user.account_status === 'ACTIVE' ? (
          <Button
            label="Pause account"
            variant="secondary"
            disabled={mutation.isPending || deleteMutation.isPending}
            onPress={() => mutation.mutate({ userId: user.user_id, status: 'SUSPENDED' })}
          />
        ) : user.account_status === 'SUSPENDED' ? (
          <Button
            label="Resume account"
            variant="secondary"
            disabled={mutation.isPending || deleteMutation.isPending}
            onPress={() => mutation.mutate({ userId: user.user_id, status: 'ACTIVE' })}
          />
        ) : (
          <Notice tone="info" message="This account is still in verification and cannot be changed here yet." />
        )}
        {(user.account_status === 'ACTIVE' || user.account_status === 'SUSPENDED') ? (
          <Button
            label="Delete account"
            variant="secondary"
            disabled={mutation.isPending || deleteMutation.isPending}
            onPress={() => confirmDelete(user)}
          />
        ) : null}
      </>
    );
  }
  const header = <><BrandHeader title="User lookup" subtitle="Search by name, username or email. Passwords, tokens and biometric data are never returned." /><Card><Field label="Search accounts" value={input} onChangeText={setInput} autoCapitalize="none" autoCorrect={false} /><Button label="Search" onPress={() => setQueryText(input.trim())} /></Card>{mutation.error ? <Notice message={errorText(mutation.error)} /> : null}</>;
  return <Screen><FlatList keyboardShouldPersistTaps="handled" data={users} keyExtractor={(user) => String(user.user_id)} refreshControl={<RefreshControl refreshing={query.isRefetching} onRefresh={() => void query.refetch()} />} ListHeaderComponent={header} ListEmptyComponent={query.isPending ? <LoadingState message="Loading accounts…" /> : query.isError ? <ErrorState message={errorText(query.error)} onRetry={() => void query.refetch()} /> : <EmptyState title="No accounts found" body="Try a different name, username or email." />} renderItem={({ item: user }) => <Card><View style={styles.rowBetween}><CategoryBadge label={user.role} /><Text style={[styles.status, user.account_status !== 'ACTIVE' && styles.statusAlert]}>{user.account_status}</Text></View><Text style={styles.title}>{user.full_name}</Text><Text style={styles.muted}>@{user.username} · {user.email}</Text>{accountAction(user)}</Card>} /></Screen>;
}

export function AdminAuditScreen(_props: AdminScreenProps<'AdminAudit'>) {
  const { session } = useAuth();
  const query = useQuery({ queryKey: adminKeys.audit, queryFn: () => fetchAdminAudit(session?.token ?? ''), enabled: Boolean(session) });
  const rows = query.data?.events ?? [];
  return <Screen><FlatList data={rows} keyExtractor={(event) => String(event.audit_id)} refreshControl={<RefreshControl refreshing={query.isRefetching} onRefresh={() => void query.refetch()} />} ListHeaderComponent={<BrandHeader title="Audit history" subtitle="A bounded, newest-first record of moderator actions." />} ListEmptyComponent={query.isPending ? <LoadingState message="Loading audit history…" /> : query.isError ? <ErrorState message={errorText(query.error)} onRetry={() => void query.refetch()} /> : <EmptyState title="No audit entries" body="Moderator actions will be recorded here." />} renderItem={({ item: event }) => <View style={styles.auditRow}><View style={styles.auditDot} /><View style={styles.flex}><Text style={styles.title}>{humanize(event.action)}</Text><Text style={styles.body}>{event.admin_name} · {event.target_type ?? 'SYSTEM'} {event.target_id ?? ''}</Text><TimeAgo value={event.created_at} /></View></View>} /></Screen>;
}

function humanize(value: string): string {
  return value.toLowerCase().split('_').map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(' ');
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  metrics: { flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.md },
  metric: { flex: 1, minHeight: 72, padding: spacing.sm, borderRadius: radius.md, backgroundColor: '#F0F8FD', borderWidth: 1, borderColor: colors.line, justifyContent: 'center' },
  alertMetric: { backgroundColor: '#FFF1F2' },
  metricValue: { color: colors.ink, fontWeight: '900', fontSize: type.title },
  priority: { backgroundColor: '#F1EAFE', borderWidth: 1, borderColor: '#D9BFF0', borderRadius: radius.md, padding: spacing.md, marginBottom: spacing.md },
  priorityKicker: { color: colors.violet, fontSize: 11, fontWeight: '900', letterSpacing: 1.2 },
  priorityTitle: { color: colors.ink, fontSize: type.title, fontWeight: '900', marginTop: 4 },
  muted: { color: colors.muted, fontSize: type.caption, lineHeight: 19 },
  body: { color: colors.ink, fontSize: type.body, lineHeight: 22, marginTop: spacing.xs },
  title: { color: colors.ink, fontSize: type.subtitle, fontWeight: '800' },
  menu: { minHeight: 64, backgroundColor: colors.surface, borderRadius: radius.md, borderWidth: 1, borderColor: colors.line, padding: spacing.md, marginBottom: spacing.sm, justifyContent: 'center' },
  highRiskMenu: { borderLeftWidth: 4, borderLeftColor: colors.danger },
  rowBetween: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: spacing.sm },
  preview: { width: '100%', height: 300, borderRadius: radius.md, backgroundColor: colors.line, marginVertical: spacing.sm },
  status: { color: colors.ok, fontWeight: '800', fontSize: type.caption },
  statusAlert: { color: colors.danger },
  auditRow: { flexDirection: 'row', gap: spacing.sm, minHeight: 68, paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.line, alignItems: 'center' },
  auditDot: { width: 12, height: 12, borderRadius: 6, backgroundColor: colors.brand },
  videoPreviewWrapper: {
    width: '100%',
    height: 300,
    borderRadius: radius.md,
    overflow: 'hidden',
    backgroundColor: colors.ink,
    marginVertical: spacing.sm,
    position: 'relative',
  },
  quarantineBadge: {
    position: 'absolute',
    top: spacing.sm,
    left: spacing.sm,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: 'rgba(239, 68, 68, 0.88)',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
    zIndex: 10,
  },
  quarantineBadgeText: {
    color: '#FFFFFF',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 0.5,
  },
  boostBadge: {
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: radius.pill,
    backgroundColor: '#F1F5F9',
  },
  boostBadgeActive: { backgroundColor: '#DCFCE7' },
  boostBadgeText: { color: '#64748B', fontWeight: '900', fontSize: 11 },
  boostBadgeTextActive: { color: '#166534' },
  boostTime: { color: colors.ink, fontSize: type.title, fontWeight: '900', marginBottom: 4 },
  boostSectionLabel: {
    color: colors.muted,
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 0.8,
    marginTop: spacing.sm,
    marginBottom: 6,
  },
  boostActionRow: { flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.sm },
  boostMiniButton: {
    flex: 1,
    minHeight: 42,
    borderRadius: radius.md,
    backgroundColor: '#EFF6FF',
    borderWidth: 1,
    borderColor: '#BFDBFE',
    justifyContent: 'center',
    alignItems: 'center',
  },
  boostMiniButtonText: { color: '#1D4ED8', fontWeight: '900' },
});
