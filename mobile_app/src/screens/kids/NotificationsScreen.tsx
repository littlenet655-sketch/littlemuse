import { useMemo, useState } from 'react';
import { Image, Pressable, RefreshControl, SectionList, StyleSheet, Text, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { fetchNotifications, markNotificationsRead, type NotificationItem } from '../../api/kidsChat';
import { ApiError } from '../../api/client';
import { useAuth } from '../../auth/AuthProvider';
import { notificationDestination } from '../../kids/social';
import type { ChildScreenProps } from '../../navigation/types';
import { queryClient, useIsForeground, useIsOnline } from '../../query/client';
import { kidsKeys } from '../../query/keys';
import { Avatar, shortAgo } from '../../ui/social';
import { BrandHeader, DisabledFeature, EmptyState, ErrorState, GateNotice, LoadingState, OfflineBanner, Screen } from '../../ui/components';
import { colors, radius } from '../../ui/tokens';

/**
 * Maps a server target_url to an app destination. The backend only ever
 * creates /chat/<id>/ and /child/dashboard/ style URLs for kids (plus parent
 * control alerts); anything unrecognized is ignored instead of crashing.
 * (Implementation lives in src/kids/social.ts so it stays unit-testable.)
 */

/** Defensively read an inline thumbnail when the payload carries one. */
function readThumbnail(item: NotificationItem): string | null {
  const t = (item as unknown as { thumbnail_url?: unknown }).thumbnail_url;
  return typeof t === 'string' && t ? t : null;
}

/** Action text without a duplicated leading actor name. */
function actionText(item: NotificationItem): string {
  const msg = String(item.message ?? item.notification_type ?? '');
  const actor = (item.actor_name ?? '').trim();
  // Only strip the actor prefix when it is a whole leading token ("Alex liked"
  // -> "liked"); without the word-boundary check, actor "Al" would turn
  // "Alex liked your photo" into "ex liked your photo".
  if (actor && msg.startsWith(actor)) {
    const rest = msg.slice(actor.length);
    if (rest === '' || /^\s/.test(rest)) return rest.trim();
  }
  return msg;
}

function timeLabel(createdAt?: string): string {
  if (!createdAt) return '';
  const t = Date.parse(createdAt);
  if (Number.isNaN(t)) return '';
  return shortAgo(Date.now() - t);
}

/** Instagram-style time bucket for section grouping: Today / This week / Earlier. */
function timeBucket(createdAt?: string): 'Today' | 'This week' | 'Earlier' {
  if (!createdAt) return 'Earlier';
  const t = Date.parse(createdAt);
  if (Number.isNaN(t)) return 'Earlier';
  const ageMs = Date.now() - t;
  if (ageMs < 0) return 'Today'; // clock skew: treat future timestamps as today
  const DAY = 24 * 60 * 60 * 1000;
  if (ageMs < DAY) return 'Today';
  if (ageMs < 7 * DAY) return 'This week';
  return 'Earlier';
}

/** Compact inline action label for a notification destination. */
function actionLabel(item: NotificationItem): string | null {
  const dest = notificationDestination(item.target_url);
  if (!dest) return null;
  if (dest.route === 'Chat') return 'Message';
  if (dest.route === 'PostDetail' || dest.route === 'OtherProfile') return 'View';
  return null;
}

export function NotificationsScreen({ navigation }: ChildScreenProps<'KidsTabs'>) {
  const { session } = useAuth();
  const online = useIsOnline();
  const foreground = useIsForeground();
  const [markingAll, setMarkingAll] = useState(false);
  const nav = navigation as unknown as { navigate: (r: string, p: object) => void };
  const token = session?.token ?? 'signed-out';
  const queryKey = [...kidsKeys.notifications, token];

  const query = useQuery({
    queryKey,
    enabled: Boolean(session) && foreground,
    staleTime: 30_000,
    queryFn: () => fetchNotifications(session!.token),
  });
  const items = query.data?.notifications ?? [];
  const unread = items.filter((n) => !n.is_read).length;

  const sections = useMemo(() => {
    // Instagram-style grouping: Today / This week / Earlier. Unread state is
    // conveyed per-row (highlighted background), not by section, so a read
    // notification from today stays under "Today" instead of jumping sections.
    const buckets: Record<'Today' | 'This week' | 'Earlier', NotificationItem[]> = {
      Today: [],
      'This week': [],
      Earlier: [],
    };
    const sorted = [...items].sort((a, b) => {
      const ta = Date.parse(a.created_at ?? '');
      const tb = Date.parse(b.created_at ?? '');
      return (Number.isNaN(tb) ? 0 : tb) - (Number.isNaN(ta) ? 0 : ta);
    });
    for (const n of sorted) buckets[timeBucket(n.created_at)].push(n);
    const out: { title: string; data: NotificationItem[] }[] = [];
    for (const title of ['Today', 'This week', 'Earlier'] as const) {
      if (buckets[title].length) out.push({ title, data: buckets[title] });
    }
    return out;
  }, [items]);

  async function markRead(ids?: number[]) {
    if (!session) return;
    try {
      await markNotificationsRead(session.token, ids);
      const markedIds = new Set(ids);
      queryClient.setQueryData<{ ok: boolean; notifications: NotificationItem[] }>(queryKey, (old) =>
        old
          ? {
              ...old,
              notifications: old.notifications.map((n) =>
                ids === undefined || markedIds.has(n.notification_id) ? { ...n, is_read: true } : n,
              ),
            }
          : old,
      );
    } catch {
      // Mark-read is best-effort; the server stays authoritative.
    }
  }

  function openTarget(item: NotificationItem) {
    const dest = notificationDestination(item.target_url);
    if (dest) nav.navigate(dest.route, dest.params);
    if (session && !item.is_read) void markRead([item.notification_id]);
  }

  if (query.isPending) return <Screen hasNativeHeader={false}><LoadingState message="Loading notifications…" /></Screen>;
  if (query.error instanceof ApiError && query.error.code === 'disabled_by_parent') return <Screen hasNativeHeader={false}><DisabledFeature feature="Notifications" /></Screen>;
  if (query.error && !items.length) {
    return (
      <Screen hasNativeHeader={false}>
        <GateNotice error={query.error} />
        <ErrorState message="Could not load notifications." onRetry={() => void query.refetch()} />
      </Screen>
    );
  }

  return (
    <Screen hasNativeHeader={false}>
      <SectionList
        sections={sections}
        keyExtractor={(n) => `n:${n.notification_id}`}
        refreshControl={<RefreshControl refreshing={query.isRefetching} onRefresh={() => void query.refetch()} />}
        ListHeaderComponent={
          <>
            <BrandHeader title="Notifications" subtitle={unread > 0 ? `${unread} unread` : undefined}  onBack={() => navigation.goBack()} />
            <OfflineBanner online={online} />
            {query.error ? <GateNotice error={query.error} /> : null}
            <View style={styles.headerActions}>
              {unread > 0 ? (
                <Pressable
                  style={[styles.smallBtn, (markingAll || !online) && styles.btnDisabled]}
                  disabled={markingAll || !online}
                  onPress={() => {
                    setMarkingAll(true);
                    markRead().finally(() => setMarkingAll(false));
                  }}
                >
                  <Text style={styles.smallBtnText}>{markingAll ? 'Marking…' : 'Mark all read'}</Text>
                </Pressable>
              ) : null}
              <Pressable style={styles.smallBtn} onPress={() => nav.navigate('SafetyCentre', {})}>
                <Text style={styles.smallBtnText}>Safety Centre</Text>
              </Pressable>
            </View>
          </>
        }
        ListEmptyComponent={<EmptyState title="No notifications" body="Messages, parent alerts and safety updates will appear here." />}
        renderSectionHeader={({ section: { title } }) => (
          <Text style={styles.sectionHeader}>{title}</Text>
        )}
        renderItem={({ item }) => {
          const thumb = readThumbnail(item);
          const inlineAction = actionLabel(item);
          return (
            <Pressable
              style={[styles.row, !item.is_read && styles.unread]}
              onPress={() => openTarget(item)}
            >
              <Avatar uri={item.actor_avatar_url} name={item.actor_name} size={44} />
              <Text style={[styles.msg, !item.is_read && styles.unreadText]} numberOfLines={3}>
                {item.actor_name ? <Text style={styles.actor}>{item.actor_name} </Text> : null}
                <Text>{actionText(item)}</Text>
                {timeLabel(item.created_at) ? (
                  <Text style={styles.time}>{`  · ${timeLabel(item.created_at)}`}</Text>
                ) : null}
              </Text>
              {thumb ? (
                <Image source={{ uri: thumb }} style={styles.thumbnail} resizeMode="cover" />
              ) : inlineAction ? (
                <Pressable style={styles.inlineBtn} onPress={() => openTarget(item)}>
                  <Text style={styles.inlineBtnText}>{inlineAction}</Text>
                </Pressable>
              ) : null}
            </Pressable>
          );
        }}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  headerActions: {
    flexDirection: 'row',
    gap: 8,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  smallBtn: {
    backgroundColor: '#EFEFEF',
    borderRadius: radius.pill,
    paddingHorizontal: 14,
    minHeight: 36,
    alignItems: 'center',
    justifyContent: 'center',
  },
  smallBtnText: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.ink,
  },
  btnDisabled: {
    opacity: 0.5,
  },
  sectionHeader: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.muted,
    textTransform: 'uppercase',
    letterSpacing: 0.6,
    paddingHorizontal: 12,
    paddingTop: 14,
    paddingBottom: 6,
    backgroundColor: colors.background,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: 12,
    paddingVertical: 13,
    borderBottomWidth: 1,
    borderBottomColor: colors.line,
    backgroundColor: colors.surface,
  },
  unread: { backgroundColor: '#F0F8FD' },
  msg: { flex: 1, color: colors.ink, fontSize: 14, lineHeight: 20 },
  actor: { fontWeight: '700' },
  time: { color: colors.muted },
  unreadText: { fontWeight: '400' },
  thumbnail: {
    width: 44,
    height: 44,
    borderRadius: 6,
    backgroundColor: '#F5F5F5',
  },
  inlineBtn: {
    backgroundColor: colors.brand,
    borderRadius: radius.pill,
    paddingHorizontal: 16,
    minHeight: 36,
    alignItems: 'center',
    justifyContent: 'center',
  },
  inlineBtnText: {
    fontSize: 13,
    fontWeight: '700',
    color: '#FFFFFF',
  },
});
