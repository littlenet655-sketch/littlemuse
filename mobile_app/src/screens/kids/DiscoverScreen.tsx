import { memo, useCallback, useEffect, useMemo, useState } from 'react';
import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { FlashList } from '@shopify/flash-list';
import { Image } from 'expo-image';
import { Feather } from '@expo/vector-icons';
import { useQuery } from '@tanstack/react-query';
import { searchDiscover, type CuratedSearchItem, type KidSummary } from '../../api/kidsProfiles';
import { fetchReelsV2, type FeedItem } from '../../api/kidsFeed';
import { toggleFollow } from '../../api/kidsSocial';
import { useAuth } from '../../auth/AuthProvider';
import type { ChildScreenProps } from '../../navigation/types';
import { queryClient, useIsOnline } from '../../query/client';
import { kidsKeys } from '../../query/keys';
import { Avatar } from '../../ui/social';
import { DisabledFeature, EmptyState, ErrorState, GateNotice, OfflineBanner } from '../../ui/components';
import { ApiError } from '../../api/client';
import { useDebouncedSearch } from '../../kids/useSearch';
import { colors } from '../../ui/tokens';

/**
 * Memoized discover rows: typing in the search box re-renders the screen on
 * every keystroke; these keep already-rendered rows from re-rendering unless
 * their own data changes.
 */
const PersonRow = memo(function PersonRow({
  kid,
  busy,
  onFollow,
  onOpenProfile,
}: {
  kid: KidSummary;
  busy: boolean;
  onFollow: (kid: KidSummary) => void;
  onOpenProfile: (userId: number) => void;
}) {
  const displayName = kid.full_name || kid.username;
  const statusLabel = busy ? '…' : kid.is_following ? 'Following' : kid.is_pending ? 'Requested' : 'Connect';
  return (
    <Pressable
      style={styles.personCard}
      onPress={() => onOpenProfile(kid.user_id)}
    >
      <Avatar uri={kid.avatar_url} name={displayName} size={48} />
      <View style={styles.personMeta}>
        <Text style={styles.personName} numberOfLines={1}>
          {displayName}
        </Text>
        <Text style={styles.personSub} numberOfLines={1}>
          @{kid.username || 'friend'}
        </Text>
      </View>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={kid.is_following || kid.is_pending ? `Unfollow ${displayName}` : `Follow ${displayName}`}
        disabled={busy}
        hitSlop={6}
        onPress={(e) => {
          e.stopPropagation();
          onFollow(kid);
        }}
        style={[styles.personActionBtn, (kid.is_following || kid.is_pending) && styles.personActionBtnMuted]}
      >
        <Text style={[styles.personActionText, (kid.is_following || kid.is_pending) && styles.personActionTextMuted]}>
          {statusLabel}
        </Text>
      </Pressable>
    </Pressable>
  );
}, (prev, next) => prev.kid === next.kid && prev.busy === next.busy);

/**
 * Minimal shape the explore grid needs. Both discover-search posts and
 * reels-feed items satisfy it, so the Reels tab can show the real reels
 * feed without a type fork.
 */
export type ExploreGridItem = {
  post_id: number;
  media_type?: string;
  media_url?: string | null;
  poster_url?: string | null;
  is_reel?: boolean;
  caption?: string;
  /** Curated learning picks have no post page — the cell is display-only. */
  is_curated?: boolean;
};

const ExploreGridCell = memo(function ExploreGridCell({
  post,
  onOpenPost,
}: {
  post: ExploreGridItem;
  onOpenPost: (postId: number) => void;
}) {
  const hasVideo = post.media_type?.toUpperCase() === 'VIDEO' || post.is_reel;
  const imgUri = hasVideo ? post.poster_url || post.media_url : post.media_url;
  return (
    <Pressable
      style={styles.gridItem}
      onPress={() => {
        // Curated picks have no post page; the cell is display-only.
        if (!post.is_curated) onOpenPost(post.post_id);
      }}
      accessibilityRole="imagebutton"
      accessibilityLabel={
        post.caption ? `Open post: ${post.caption.slice(0, 80)}` : hasVideo ? 'Open reel' : 'Open post'
      }
    >
      {imgUri ? (
        <Image source={{ uri: imgUri }} style={styles.gridThumb} contentFit="cover" cachePolicy="memory-disk" />
      ) : (
        <View style={styles.gridPlaceholder}>
          <Feather name={hasVideo ? 'film' : 'file-text'} size={24} color="#94A3B8" />
        </View>
      )}
      {hasVideo ? (
        <View style={styles.videoBadge}>
          <Feather name="play" size={11} color="#FFFFFF" />
        </View>
      ) : null}
    </Pressable>
  );
}, (prev, next) => prev.post === next.post);

const CuratedRowCard = memo(function CuratedRowCard({ item }: { item: CuratedSearchItem }) {
  const imgUri = item.poster_url || item.media_url;
  return (
    <View style={styles.curatedCard}>
      {imgUri ? (
        <Image source={{ uri: imgUri }} style={styles.curatedThumb} contentFit="cover" cachePolicy="memory-disk" />
      ) : (
        <View style={styles.curatedPlaceholder}>
          <Feather name="book-open" size={24} color="#94A3B8" />
        </View>
      )}
      <Text style={styles.curatedCaption} numberOfLines={2}>{item.title || item.caption || 'Learning pick'}</Text>
    </View>
  );
}, (prev, next) => prev.item === next.item);

export function DiscoverScreen({ navigation }: ChildScreenProps<'KidsTabs'>) {
  const { session } = useAuth();
  const online = useIsOnline();
  const { raw, setRaw, debounced } = useDebouncedSearch(300);
  const [kind, setKind] = useState<'People' | 'Posts' | 'Reels' | 'Learn'>('People');
  const [recent, setRecent] = useState<string[]>([]);
  const [followBusy, setFollowBusy] = useState<number | null>(null);
  const nav = navigation as unknown as { navigate: (r: string, p: object) => void };
  const token = session?.token ?? 'signed-out';
  // Memoized: a fresh array identity every render would churn the query key.
  const queryKey = useMemo(() => [...kidsKeys.discover(debounced), token], [debounced, token]);

  const query = useQuery({
    queryKey,
    enabled: Boolean(session),
    staleTime: 30_000,
    queryFn: ({ signal }) => searchDiscover(session!.token, debounced, signal),
  });

  // Reels tab: the discover endpoint only returns non-reel posts when there
  // is no search query, so the tab was blank on the default Explore view.
  // Pull the real reels feed (server-enforced ALLOWED + is_safe) instead.
  const reelsKey = useMemo(() => [...kidsKeys.reels, 'discover-tab', token], [token]);
  const reelsQuery = useQuery({
    queryKey: reelsKey,
    enabled: Boolean(session) && kind === 'Reels',
    staleTime: 30_000,
    queryFn: ({ signal }) => fetchReelsV2(session!.token, 0, 30, undefined, signal),
  });
  const reels: ExploreGridItem[] = useMemo(
    () => (reelsQuery.data?.items ?? []).map((item: FeedItem) => ({
      post_id: item.post_id,
      media_type: item.media_type,
      media_url: item.media_url,
      poster_url: item.poster_url,
      is_reel: true,
      caption: item.caption,
    })),
    [reelsQuery.data],
  );
  const reelsLoading = reelsQuery.isPending;

  const [refreshing, setRefreshing] = useState(false);
  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: kidsKeys.discover(debounced) }),
        queryClient.invalidateQueries({ queryKey: kidsKeys.reels }),
      ]);
    } finally {
      setRefreshing(false);
    }
  }, [debounced]);
  const refreshControl = <RefreshControl refreshing={refreshing} onRefresh={() => void onRefresh()} />;
  const kids = query.data?.children ?? [];
  const posts = query.data?.posts ?? [];
  const curated = query.data?.curated ?? [];
  const pii = !!query.data?.pii_warning;
  const loading = query.isPending;
  const error = query.error;

  // Track successful, non-PII searches for the "recent" strip.
  useEffect(() => {
    if (query.data && debounced.trim() && !query.data.pii_warning) {
      const term = debounced.trim();
      setRecent((old) => [term, ...old.filter((item) => item !== term)].slice(0, 5));
    }
  }, [query.data, debounced]);

  /** Follow/unfollow toggle with optimistic label and authoritative rollback. */
  const onFollowKid = useCallback(async (kid: KidSummary) => {
    if (!session || followBusy) return;
    setFollowBusy(kid.user_id);
    const wasActive = Boolean(kid.is_following || kid.is_pending);
    // Optimistic: flip to the expected next state instantly.
    queryClient.setQueryData<Awaited<ReturnType<typeof searchDiscover>>>(queryKey, (old) =>
      old
        ? {
            ...old,
            children: old.children.map((c) =>
              c.user_id === kid.user_id
                ? { ...c, is_following: false, is_pending: !wasActive }
                : c,
            ),
          }
        : old,
    );
    try {
      await toggleFollow(session.token, kid.user_id);
    } catch {
      // Roll back to the authoritative server state on failure.
    } finally {
      setFollowBusy(null);
      await queryClient.invalidateQueries({ queryKey: kidsKeys.discover(debounced) });
    }
  }, [session, followBusy, queryKey, debounced]);

  // Stable navigation callbacks for the memoized rows.
  const openProfile = useCallback((userId: number) => nav.navigate('OtherProfile', { targetId: userId }), [nav]);
  const openPost = useCallback((postId: number) => nav.navigate('PostDetail', { postId }), [nav]);

  const filteredPosts = useMemo(() => posts.filter((p) => {
    if (kind === 'Learn') return String(p.content_category ?? '').toLowerCase().includes('learn');
    if (kind === 'Reels') return Boolean(p.is_reel);
    return true;
  }), [posts, kind]);

  // Instagram Explore shows reels on the default view; the discover search
  // only returns reels when a query is typed, so use the reels feed for the
  // unfiltered Reels tab and search results while typing.
  const showReelsFeed = kind === 'Reels' && !debounced.trim();
  // Instagram Explore parity: with no query and no social posts (fresh
  // account), fill the grid with safe curated picks instead of a centered
  // empty state.
  const exploreFallback: ExploreGridItem[] = useMemo(
    () =>
      !debounced.trim() && kind === 'Posts' && filteredPosts.length === 0
        ? curated.map((c) => ({
            post_id: c.source_id,
            media_type: c.media_type,
            media_url: c.media_url ?? null,
            poster_url: c.poster_url ?? null,
            is_reel: false,
            caption: c.caption,
            is_curated: true,
          }))
        : [],
    [debounced, kind, filteredPosts, curated],
  );
  const gridItems: ExploreGridItem[] = showReelsFeed
    ? reels
    : filteredPosts.length > 0
      ? filteredPosts
      : exploreFallback;
  const reelsError = showReelsFeed ? reelsQuery.error : null;
  const hasAnyContent =
    kids.length > 0 || posts.length > 0 || curated.length > 0 || (showReelsFeed && reels.length > 0);

  const renderPerson = useCallback(({ item }: { item: KidSummary }) => (
    <PersonRow
      kid={item}
      busy={followBusy === item.user_id}
      onFollow={(k) => void onFollowKid(k)}
      onOpenProfile={openProfile}
    />
  ), [followBusy, onFollowKid, openProfile]);

  const renderGridCell = useCallback(({ item }: { item: ExploreGridItem }) => (
    <ExploreGridCell post={item} onOpenPost={openPost} />
  ), [openPost]);

  const renderCurated = useCallback(({ item }: { item: CuratedSearchItem }) => (
    <CuratedRowCard item={item} />
  ), []);


  if (error instanceof ApiError && error.code === 'disabled_by_parent') {
    return <DisabledFeature feature="Discover" />;
  }

  return (
    <View style={styles.container}>
      <OfflineBanner online={online} />

      {/* Modern Instagram Search Bar */}
      <View style={styles.searchContainer}>
        <View style={styles.searchBar}>
          <Feather name="search" size={17} color="#94A3B8" />
          <TextInput
            style={styles.searchInput}
            placeholder="Search friends, topics, posts…"
            placeholderTextColor="#94A3B8"
            value={raw}
            onChangeText={setRaw}
            autoCapitalize="none"
            autoCorrect={false}
            returnKeyType="search"
          />
          {raw ? (
            <Pressable onPress={() => setRaw('')} hitSlop={8}>
              <Feather name="x-circle" size={16} color="#94A3B8" />
            </Pressable>
          ) : null}
        </View>
      </View>

      {/* Recent Searches Pills */}
      {!raw && recent.length > 0 ? (
        <View style={styles.recentSection}>
          <Text style={styles.recentTitle}>RECENT</Text>
          <View style={styles.recentRow}>
            {recent.map((item) => (
              <Pressable key={item} onPress={() => setRaw(item)} style={styles.recentPill}>
                <Feather name="clock" size={11} color="#64748B" />
                <Text style={styles.recentText}>{item}</Text>
              </Pressable>
            ))}
          </View>
        </View>
      ) : null}

      {/* Category chips — horizontal pill strip */}
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.chipsStrip}
        contentContainerStyle={styles.chipsRow}
      >
        {(['People', 'Posts', 'Reels', 'Learn'] as const).map((item) => {
          const active = kind === item;
          const icon = item === 'People' ? 'users' : item === 'Posts' ? 'grid' : item === 'Reels' ? 'film' : 'book-open';
          return (
            <Pressable
              key={item}
              onPress={() => setKind(item)}
              style={[styles.filterBtn, active && styles.filterBtnActive]}
            >
              <Feather name={icon} size={13} color={active ? '#FFFFFF' : '#64748B'} />
              <Text style={[styles.filterText, active && styles.filterTextActive]}>{item}</Text>
            </Pressable>
          );
        })}
      </ScrollView>

      {error ? <GateNotice error={error} /> : null}
      {reelsError ? <GateNotice error={reelsError} /> : null}
      {pii ? (
        <GateNotice error={new ApiError(200, 'pii_warning', 'That search cannot be shown. Try different words.')} />
      ) : null}

      {(loading && !kids.length && !posts.length) || (showReelsFeed && reelsLoading && !reels.length) ? (
        <View style={styles.skeletonGrid} accessibilityRole="progressbar">
          {Array.from({ length: 9 }).map((_, i) => (
            <View key={i} style={styles.skeletonCell} />
          ))}
        </View>
      ) : null}

      {!loading && !reelsLoading && !error && !hasAnyContent && kind !== 'Learn' ? (
        <View>
          <EmptyState
            icon="search"
            title="No results found"
            body={raw ? 'Try another name, subject, or friendly topic.' : 'Explore safe learning, friends, and creative ideas.'}
          />
          {!raw ? (
            <View style={styles.suggestionRow} accessibilityRole="list" accessibilityLabel="Suggested topics">
              {['Science', 'Space', 'Animals', 'Art', 'Sports', 'Music'].map((topic) => (
                <Pressable
                  key={topic}
                  style={styles.suggestionChip}
                  accessibilityRole="button"
                  accessibilityLabel={`Search ${topic}`}
                  onPress={() => setRaw(topic)}
                >
                  <Text style={styles.suggestionText}>{topic}</Text>
                </Pressable>
              ))}
            </View>
          ) : null}
        </View>
      ) : null}

      {kind === 'Reels' && showReelsFeed && !reelsLoading && !reelsError && reels.length === 0 ? (
        <EmptyState
          icon="film"
          title="No reels yet"
          body="Reels shared by friends will appear here."
        />
      ) : null}

      {kind === 'Learn' && !loading && !error && curated.length === 0 && filteredPosts.length === 0 ? (
        <EmptyState
          icon="book-open"
          title="Nothing to learn yet"
          body="Try searching a subject like science, space, or art."
        />
      ) : null}

      {error && !hasAnyContent ? (
        <ErrorState
          message="Search is currently unavailable."
          onRetry={() => {
            void query.refetch();
            void reelsQuery.refetch();
          }}
        />
      ) : null}

      {/* People Mode: Vertical list of clean friend cards */}
      {kind === 'People' && kids.length > 0 ? (
        <FlashList
          data={kids}
          keyExtractor={(k) => `kid:${k.user_id}`}
          contentContainerStyle={styles.peopleList}
          showsVerticalScrollIndicator={false}
          drawDistance={600}
          refreshControl={refreshControl}
          renderItem={renderPerson}
        />
      ) : null}

      {/* Learn Mode: server-curated learning picks (displayed as-is; ranking is server-side) */}
      {kind === 'Learn' && curated.length > 0 ? (
        <View>
          <Text style={styles.sectionTitle}>Recommended for you</Text>
          <FlashList
            data={curated}
            horizontal
            keyExtractor={(c) => `curated:${c.source_id}`}
            contentContainerStyle={styles.curatedRow}
            showsHorizontalScrollIndicator={false}
            drawDistance={600}
            renderItem={renderCurated}
          />
        </View>
      ) : null}

      {/* Posts / Reels / Learn Mode: Instagram Explore 3-column grid */}
      {kind !== 'People' && gridItems.length > 0 ? (
        <FlashList
          data={gridItems}
          keyExtractor={(p) => `post:${p.post_id}`}
          numColumns={3}
          contentContainerStyle={styles.gridContainer}
          showsVerticalScrollIndicator={false}
          drawDistance={800}
          refreshControl={refreshControl}
          renderItem={renderGridCell}
        />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  searchContainer: {
    paddingHorizontal: 16,
    paddingTop: 10,
    paddingBottom: 8,
    backgroundColor: colors.surface,
  },
  searchBar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: '#EFEFEF',
    borderRadius: 10,
    paddingHorizontal: 12,
    height: 36,
  },
  searchInput: {
    flex: 1,
    fontSize: 14,
    color: colors.ink,
    paddingVertical: 0,
  },
  recentSection: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    backgroundColor: colors.surface,
    borderBottomWidth: 1,
    borderBottomColor: '#F0F0F0',
  },
  recentTitle: {
    fontSize: 10,
    fontWeight: '800',
    color: '#94A3B8',
    letterSpacing: 0.8,
    marginBottom: 6,
  },
  recentRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  recentPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: '#F1F5F9',
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 14,
  },
  recentText: {
    fontSize: 12,
    color: '#475569',
    fontWeight: '600',
  },
  chipsStrip: {
    backgroundColor: colors.surface,
    borderBottomWidth: 1,
    borderBottomColor: '#F0F0F0',
  },
  chipsRow: {
    paddingHorizontal: 16,
    paddingVertical: 10,
    gap: 8,
    alignItems: 'center',
  },
  filterBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 18,
    backgroundColor: '#F1F5F9',
  },
  filterBtnActive: {
    backgroundColor: colors.brand,
  },
  filterText: {
    fontSize: 12,
    fontWeight: '700',
    color: '#64748B',
  },
  filterTextActive: {
    color: '#FFFFFF',
  },
  sectionTitle: {
    fontSize: 14,
    fontWeight: '800',
    color: colors.ink,
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 8,
  },
  curatedRow: {
    paddingHorizontal: 16,
    gap: 10,
    paddingBottom: 8,
  },
  curatedCard: {
    width: 150,
    backgroundColor: colors.surface,
    borderRadius: 14,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: '#F0F0F0',
  },
  curatedThumb: {
    width: '100%',
    height: 110,
    backgroundColor: '#F1F5F9',
  },
  curatedPlaceholder: {
    width: '100%',
    height: 110,
    backgroundColor: '#F1F5F9',
    justifyContent: 'center',
    alignItems: 'center',
  },
  curatedCaption: {
    fontSize: 12,
    color: colors.ink,
    fontWeight: '600',
    lineHeight: 16,
    padding: 8,
  },
  peopleList: {
    padding: 16,
    gap: 10,
  },
  personCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surface,
    padding: 12,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: '#F0F0F0',
    gap: 12,
  },
  personMeta: {
    flex: 1,
  },
  personName: {
    fontSize: 15,
    fontWeight: '700',
    color: colors.ink,
    marginBottom: 2,
  },
  personSub: {
    fontSize: 12,
    color: colors.muted,
  },
  personActionBtn: {
    paddingHorizontal: 14,
    paddingVertical: 7,
    borderRadius: 16,
    backgroundColor: colors.brand,
  },
  personActionBtnMuted: {
    backgroundColor: '#F1F5F9',
  },
  personActionText: {
    fontSize: 12,
    fontWeight: '700',
    color: '#FFFFFF',
  },
  personActionTextMuted: {
    color: '#64748B',
  },
  gridContainer: {
    padding: 1,
  },
  gridItem: {
    flex: 1,
    aspectRatio: 1,
    margin: 1,
    backgroundColor: '#EFEFEF',
  },
  gridThumb: {
    width: '100%',
    aspectRatio: 1,
    backgroundColor: '#EFEFEF',
  },
  gridPlaceholder: {
    width: '100%',
    aspectRatio: 1,
    backgroundColor: '#EFEFEF',
    justifyContent: 'center',
    alignItems: 'center',
  },
  videoBadge: {
    position: 'absolute',
    top: 8,
    right: 8,
    backgroundColor: 'rgba(0,0,0,0.6)',
    width: 24,
    height: 24,
    borderRadius: 12,
    justifyContent: 'center',
    alignItems: 'center',
  },
  suggestionRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'center',
    gap: 8,
    paddingHorizontal: 24,
    marginTop: 4,
  },
  suggestionChip: {
    backgroundColor: '#EEF2FF',
    borderRadius: 16,
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  suggestionText: {
    color: '#4F46E5',
    fontSize: 13,
    fontWeight: '700',
  },
  skeletonGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    padding: 2,
  },
  skeletonCell: {
    width: '33.333%',
    aspectRatio: 1,
    backgroundColor: '#EFEFEF',
    borderWidth: 1,
    borderColor: colors.background,
  },
});
