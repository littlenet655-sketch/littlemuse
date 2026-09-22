import { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, FlatList, Pressable, RefreshControl, StyleSheet, Text, TextInput, View } from 'react-native';
import { useIsFocused } from '@react-navigation/native';
import { fetchConversations, type ConversationItem } from '../../api/kidsChat';
import { useAuth } from '../../auth/AuthProvider';
import { dedupeConversations, isConversationUnread } from '../../kids/social';
import type { ChildScreenProps } from '../../navigation/types';
import { useIsForeground } from '../../query/client';
import { Avatar, TimeAgo } from '../../ui/social';
import { BrandHeader, Button, DisabledFeature, EmptyState, ErrorState, GateNotice, LoadingState, Screen } from '../../ui/components';
import { ApiError } from '../../api/client';
import { colors } from '../../ui/tokens';

/**
 * Server-side page size. The backend conversations endpoint supports
 * limit/offset paging (limit clamped to 1..50 server-side) and returns
 * has_more. Pages are fetched on demand as the user scrolls; each page is
 * appended and deduped. Search still filters locally over loaded pages.
 */
const PAGE_SIZE = 20;

function sentAtMs(c: ConversationItem): number {
  const raw = c.last_message?.sent_at;
  if (!raw) return 0;
  const ms = Date.parse(raw);
  return Number.isNaN(ms) ? 0 : ms;
}

export function ConversationsScreen({ navigation }: ChildScreenProps<'KidsTabs'>) {
  const { session } = useAuth();
  const foreground = useIsForeground();
  const focused = useIsFocused();
  const [items, setItems] = useState<ConversationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [query, setQuery] = useState('');
  const nav = navigation as unknown as { navigate: (r: string, p: object) => void };
  const myId = session?.user.user_id;
  const q = query.trim().toLowerCase();

  async function load(mode: 'first' | 'refresh') {
    if (!session || !foreground) return;
    if (mode === 'first') setLoading(true);
    else setRefreshing(true);
    try {
      // First server page (offset 0); has_more drives onEndReached paging.
      const res = await fetchConversations(session.token, { limit: PAGE_SIZE, offset: 0 });
      setItems(dedupeConversations(res.conversations ?? []));
      setHasMore(res.has_more === true);
      setError(null);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  /** Append the next server page. Offset paging keys off loaded rows; the
      server orders deterministically (last_sent_at DESC, conversation_id
      DESC) so pages are stable while idle. */
  async function loadMore() {
    if (!session || !foreground || loading || loadingMore || !hasMore || q) return;
    setLoadingMore(true);
    try {
      const res = await fetchConversations(session.token, { limit: PAGE_SIZE, offset: items.length });
      // Dedupe defensively so repeats (or a new message shifting rows between
      // pages) never render twice.
      setItems((prev) => dedupeConversations([...prev, ...(res.conversations ?? [])]));
      setHasMore(res.has_more === true);
    } catch {
      // Keep the loaded pages; the footer stays as a manual retry.
    } finally {
      setLoadingMore(false);
    }
  }

  useEffect(() => {
    if (focused && foreground) void load(loading ? 'first' : 'refresh');
  }, [session?.token, focused, foreground]);

  // Most-recent-first, like Instagram's inbox. The server pages in this
  // order already; the local sort keeps it stable across appended pages.
  const sorted = useMemo(() => {
    return [...items].sort((a, b) => sentAtMs(b) - sentAtMs(a));
  }, [items]);

  const filtered = useMemo(() => {
    if (!q) return sorted;
    return sorted.filter((c) => (c.peer_name ?? '').toLowerCase().includes(q));
  }, [sorted, q]);

  // Search scopes to already-loaded pages (no server search param); paging
  // pauses while a query is active and resumes when it is cleared.
  const showMore = !q && hasMore;

  if (loading) return <Screen><LoadingState message="Loading messages…" /></Screen>;
  if (error instanceof ApiError && error.code === 'disabled_by_parent') return <Screen><DisabledFeature feature="Messages" /></Screen>;
  if (error && !items.length) return <Screen><GateNotice error={error} /><ErrorState message="Could not load messages." onRetry={() => void load('first')} /></Screen>;

  return (
    <Screen>
      <FlatList
        data={filtered}
        keyExtractor={(c) => `c:${c.conversation_id}`}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void load('refresh')} />}
        initialNumToRender={PAGE_SIZE}
        maxToRenderPerBatch={PAGE_SIZE}
        onEndReachedThreshold={0.5}
        onEndReached={() => {
          if (showMore && !loadingMore) void loadMore();
        }}
        ListHeaderComponent={(
          <>
            <BrandHeader title="Messages" subtitle="Only approved friends can message." />
            <View style={styles.searchWrap}>
              <TextInput
                style={styles.search}
                placeholder="Search"
                placeholderTextColor={colors.muted}
                value={query}
                onChangeText={(t) => { setQuery(t); }}
                returnKeyType="search"
                autoCorrect={false}
                autoCapitalize="none"
                clearButtonMode="while-editing"
              />
            </View>
            <Button label="New message" onPress={() => nav.navigate('NewMessage', {})} />
          </>
        )}
        ListEmptyComponent={(
          <EmptyState
            title={q ? 'No matches' : 'No conversations'}
            body={q ? `No chats with "${query.trim()}".` : 'Make an approved friend to start chatting.'}
          />
        )}
        ListFooterComponent={showMore || loadingMore ? (
          <View style={styles.moreWrap}>
            {loadingMore ? (
              <ActivityIndicator size="small" color={colors.muted} />
            ) : (
              <Pressable
                accessibilityRole="button"
                onPress={() => void loadMore()}
                style={styles.loadMoreBtn}
              >
                <Text style={styles.loadMoreText}>Load more conversations</Text>
              </Pressable>
            )}
          </View>
        ) : null}
        renderItem={({ item }) => {
          const unread = isConversationUnread(item);
          const own = myId != null && item.last_message?.sender_child_id === myId;
          const rawPreview = item.last_message?.message_text ?? '';
          const preview = own && rawPreview ? `You: ${rawPreview}` : rawPreview;
          return (
            <Pressable
              style={({ pressed }) => [styles.row, pressed && styles.rowPressed]}
              onPress={() => nav.navigate('Chat', { peerId: item.peer_id })}
            >
              <Avatar uri={item.peer_avatar_url} name={item.peer_name} size={56} />
              <View style={styles.textCol}>
                <View style={styles.topRow}>
                  <Text style={[styles.name, unread && styles.nameUnread]} numberOfLines={1}>
                    {item.peer_name ?? 'Friend'}
                  </Text>
                  <TimeAgo value={item.last_message?.sent_at} />
                </View>
                <View style={styles.bottomRow}>
                  <Text style={[styles.preview, unread && styles.previewUnread]} numberOfLines={1}>
                    {preview}
                  </Text>
                  {unread ? <View style={styles.unreadDot} /> : null}
                </View>
              </View>
            </Pressable>
          );
        }}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingHorizontal: 12,
    height: 76,
    backgroundColor: colors.surface,
  },
  rowPressed: {
    backgroundColor: '#F5F5F5',
  },
  textCol: {
    flex: 1,
    justifyContent: 'center',
  },
  topRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  name: {
    flex: 1,
    fontSize: 15,
    fontWeight: '700',
    color: colors.ink,
  },
  nameUnread: {
    fontWeight: '800',
  },
  preview: {
    flex: 1,
    fontSize: 14,
    color: colors.muted,
  },
  previewUnread: {
    color: colors.ink,
    fontWeight: '700',
  },
  bottomRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: 3,
  },
  unreadDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: colors.brand,
  },
  searchWrap: {
    paddingHorizontal: 12,
    paddingBottom: 8,
  },
  search: {
    backgroundColor: '#F2F2F2',
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 8,
    fontSize: 15,
    color: colors.ink,
  },
  moreWrap: {
    paddingVertical: 16,
    alignItems: 'center',
  },
  loadMoreBtn: {
    paddingHorizontal: 18,
    paddingVertical: 10,
    borderRadius: 20,
    backgroundColor: '#EFF6FF',
  },
  loadMoreText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#2563EB',
  },
});
