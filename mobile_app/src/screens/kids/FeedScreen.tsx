import { Pressable, RefreshControl, ScrollView, StyleSheet, Text, View, type ViewToken } from 'react-native';
import { FlashList } from '@shopify/flash-list';
import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useIsFocused } from '@react-navigation/native';
import { useQuery } from '@tanstack/react-query';
import { Feather } from '@expo/vector-icons';
import { ApiError } from '../../api/client';
import { fetchKidsHome, recordFeedImpression, type StoryItem } from '../../api/kidsFeed';
import { submitRecommendationAction } from '../../api/recommendation';
import { useAuth } from '../../auth/AuthProvider';
import { PostCard } from '../../kids/PostCard';
import { useFeed } from '../../kids/useFeed';
import { kidsKeys } from '../../query/keys';
import { socialPostTarget, socialProfileTarget, feedKey } from '../../kids/social';
import type { ChildScreenProps } from '../../navigation/types';
import { useIsForeground, useIsOnline } from '../../query/client';
import type { FeedItem } from '../../api/kidsFeed';
import { Avatar, StoryRing } from '../../ui/social';
import { colors, spacing } from '../../ui/tokens';
import { DisabledFeature, EmptyState, ErrorState, GateNotice, LoadingState, OfflineBanner, Screen, Skeleton } from '../../ui/components';

/**
 * Server sends more than the base StoryItem declares: owner id and whether the
 * viewer already saw the story.
 */
interface TrayStory extends StoryItem {
  child_id?: number;
  viewed?: boolean;
}

/**
 * Instagram-style horizontal stories tray for the feed header. Visual only —
 * taps open the existing Stories viewer at its own start.
 */
function StoriesTray({
  token,
  myId,
  myName,
  onOpen,
}: {
  token?: string;
  myId?: number;
  myName?: string;
  onOpen: (initialStoryId?: number) => void;
}) {
  // Read the shared home query instead of firing a duplicate raw fetch: the
  // hydration layer already warms [...kidsKeys.home, token], so this dedupes
  // to zero extra network requests on feed mount.
  const { data } = useQuery({
    queryKey: [...kidsKeys.home, token],
    queryFn: () => fetchKidsHome(token ?? ''),
    enabled: !!token,
    staleTime: 120_000,
  });
  const stories = ((data?.stories ?? []) as TrayStory[]);

  const myStories = myId != null ? stories.filter((s) => s.child_id === myId) : [];
  const own = myStories[0];
  const ownSeen = myStories.length > 0 && myStories.every((s) => s.viewed);

  // One ring per friend, preserving server order; ring is grey only when every
  // story from that friend was viewed.
  const friendOrder = new Map<number, TrayStory[]>();
  for (const story of stories) {
    if (story.child_id == null || story.child_id === myId) continue;
    const group = friendOrder.get(story.child_id) ?? [];
    group.push(story);
    friendOrder.set(story.child_id, group);
  }
  const friends = [...friendOrder.values()].map((group) => group[0]).filter(Boolean) as TrayStory[];

  return (
    <View style={styles.trayWrap}>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.trayContent}
      >
        <Pressable
          onPress={() => onOpen(own?.post_id)}
          style={styles.trayCell}
          accessibilityRole="button"
          accessibilityLabel="Your story"
        >
          <View>
            <StoryRing size={68} seen={ownSeen}>
              <Avatar uri={own?.avatar_url} name={myName} size={56} />
            </StoryRing>
            <View style={styles.plusBadge} pointerEvents="none">
              <Feather name="plus" size={14} color="#FFFFFF" />
            </View>
          </View>
          <Text style={styles.trayName} numberOfLines={1}>
            Your story
          </Text>
        </Pressable>
        {friends.map((story) => (
          <Pressable
            key={`tray-${story.post_id}`}
            onPress={() => onOpen(story.post_id)}
            style={styles.trayCell}
            accessibilityRole="button"
            accessibilityLabel={`${story.full_name ?? 'Friend'}'s story`}
          >
            <StoryRing size={68} seen={Boolean(story.viewed)}>
              <Avatar uri={story.avatar_url} name={story.full_name ?? 'Friend'} size={56} />
            </StoryRing>
            <Text style={styles.trayName} numberOfLines={1}>
              {story.full_name ?? 'Friend'}
            </Text>
          </Pressable>
        ))}
      </ScrollView>
    </View>
  );
}

type FeedTab = 'For You' | 'Friends' | 'Learn';

/**
 * Memoized list header: the feed re-renders on every scroll tick (viewability)
 * and every optimistic like/save, but the header subtree (stories tray, tabs)
 * only re-renders when its own inputs change.
 */
/**
 * Polished voluntary quiz card shown at the top of the Learn section.
 * Children can practice age-tailored questions anytime without affecting Reel doom-scroll gates.
 */
function QuizZoneCard({ onStart }: { onStart: () => void }) {
  return (
    <View style={styles.quizZoneCard} accessibilityRole="summary" accessibilityLabel="Quiz Zone">
      <View style={styles.quizZoneContent}>
        <View style={styles.quizZoneIconWrap}>
          <Text style={styles.quizZoneEmoji}>🧠</Text>
        </View>
        <View style={styles.quizZoneTextWrap}>
          <View style={styles.quizZoneBadge}>
            <Text style={styles.quizZoneBadgeText}>AGE-BASED QUIZ</Text>
          </View>
          <Text style={styles.quizZoneTitle}>Quiz Zone</Text>
          <Text style={styles.quizZoneSubtitle}>
            Test yourself with a quiz made for your age. Earn XP whenever you want!
          </Text>
        </View>
      </View>
      <Pressable
        style={({ pressed }) => [styles.quizZoneButton, pressed && styles.quizZoneButtonPressed]}
        onPress={onStart}
        accessibilityRole="button"
        accessibilityLabel="Start Quiz"
      >
        <Feather name="play" size={15} color="#FFFFFF" style={{ marginRight: 6 }} />
        <Text style={styles.quizZoneButtonText}>Start Quiz</Text>
      </Pressable>
    </View>
  );
}

const FeedListHeader = memo(function FeedListHeader({
  token,
  myId,
  myName,
  tab,
  onTabChange,
  onOpenStories,
  online,
  error,
  onStartQuizZone,
}: {
  token?: string;
  myId?: number;
  myName?: string;
  tab: FeedTab;
  onTabChange: (tab: FeedTab) => void;
  onOpenStories: (initialStoryId?: number) => void;
  online: boolean;
  error: unknown;
  onStartQuizZone?: () => void;
}) {
  return (
    <>
      <StoriesTray token={token} myId={myId} myName={myName} onOpen={onOpenStories} />
      <View style={styles.tabs}>
        {(['For You', 'Friends', 'Learn'] as const).map((item) => (
          <Pressable
            key={item}
            onPress={() => onTabChange(item)}
            style={styles.tabHit}
            accessibilityRole="tab"
            accessibilityState={{ selected: tab === item }}
          >
            <Text style={[styles.tabLabel, tab === item && styles.tabLabelActive]}>{item}</Text>
            <View style={[styles.tabIndicator, tab === item && styles.tabIndicatorActive]} />
          </Pressable>
        ))}
      </View>
      <OfflineBanner online={online} />
      {error ? <GateNotice error={error} /> : null}
      {tab === 'Learn' ? <QuizZoneCard onStart={() => onStartQuizZone?.()} /> : null}
    </>
  );
});

/**
 * Memoized feed row: parent renders on every viewability tick and every
 * optimistic cache update re-rendered ALL PostCards before; now a row only
 * re-renders when its item identity, its own video-active flag, or the tab
 * (which controls the Not Interested affordance) changes.
 */
/**
 * Kit end-of-feed card (from the Stitch 08_kids_home_feed mockup): circled
 * check, "You're All Caught Up" title, grey subtitle. Purely visual — shown
 * only when the list has items and there are no more pages to load.
 */
const CaughtUpCard = memo(function CaughtUpCard() {
  return (
    <View style={styles.caughtUpWrap} accessibilityLabel="You're all caught up">
      <View style={styles.caughtUpCircle}>
        <Feather name="check" size={24} color={colors.ok} />
      </View>
      <Text style={styles.caughtUpTitle}>You&apos;re All Caught Up</Text>
      <Text style={styles.caughtUpSubtitle}>
        You&apos;ve seen all new safe updates from friends and classmates today.
      </Text>
    </View>
  );
});

const FeedRow = memo(function FeedRow({
  item,
  videoActive,
  tab,
  nav,
  onNotInterestedItem,
  onDeletedItem,
}: {
  item: FeedItem;
  videoActive: boolean;
  tab: FeedTab;
  nav: { navigate: (r: string, p: object) => void };
  onNotInterestedItem: (sourceType: 'SOCIAL' | 'CURATED', sourceId: number) => void;
  onDeletedItem: (item: FeedItem) => void;
}) {
  const post = socialPostTarget(item);
  const profile = socialProfileTarget(item);
  return (
    <PostCard
      item={item}
      onOpen={post ? () => nav.navigate('PostDetail', post) : undefined}
      onProfile={profile ? () => nav.navigate('OtherProfile', profile) : undefined}
      onNotInterested={tab === 'Friends' ? undefined : () => onNotInterestedItem(item.source_type, item.source_id)}
      onDeleted={() => onDeletedItem(item)}
      inlineVideoPlayback
      videoActive={videoActive}
    />
  );
}, (prev, next) =>
  prev.item === next.item &&
  prev.videoActive === next.videoActive &&
  prev.tab === next.tab &&
  prev.onDeletedItem === next.onDeletedItem,
);

export function FeedScreen({ navigation }: ChildScreenProps<'KidsTabs'>) {
  const online = useIsOnline();
  const focused = useIsFocused();
  const foreground = useIsForeground();
  const { session } = useAuth();
  const nav = navigation as unknown as { navigate: (r: string, p: object) => void };
  const [tab, setTab] = useState<FeedTab>('For You');
  const [hiddenKeys, setHiddenKeys] = useState<Set<string>>(new Set());
  const [activeVideoKey, setActiveVideoKey] = useState<string | null>(null);
  const reportedViewsRef = useRef<Set<string>>(new Set());
  const reportedSessionRef = useRef<string | undefined>(undefined);
  const viewabilityConfig = useRef({ itemVisiblePercentThreshold: 60, minimumViewTime: 250 }).current;
  const feedMode = tab === 'Friends' ? 'friends' : tab === 'Learn' ? 'learn' : 'for_you';
  const feed = useFeed('feed', 10, feedMode);
  const loadMoreRef = useRef(feed.loadMore);
  loadMoreRef.current = feed.loadMore;

  if (reportedSessionRef.current !== feed.sessionId) {
    reportedSessionRef.current = feed.sessionId;
    reportedViewsRef.current.clear();
  }

  const onViewableItemsChanged = useCallback(({ viewableItems }: { viewableItems: ViewToken[] }) => {
    const visibleVideo = viewableItems.find((entry) => {
      const item = entry.item as FeedItem | undefined;
      return Boolean(entry.isViewable && item?.media_type?.toUpperCase() === 'VIDEO');
    });
    const videoItem = visibleVideo?.item as FeedItem | undefined;
    setActiveVideoKey(videoItem ? `${videoItem.source_type}:${videoItem.source_id}` : null);

    const furthest = viewableItems.reduce((max, entry) => Math.max(max, entry.index ?? -1), -1);
    if (furthest >= 0 && furthest >= feed.items.length - 2) loadMoreRef.current();

    for (const entry of viewableItems) {
      if (!entry.isViewable) continue;
      const item = entry.item as FeedItem | undefined;
      if (!item) continue;
      if (!session?.token || !feed.sessionId) continue;
      const sourceId = Number(item.source_id ?? item.post_id ?? 0);
      if (!sourceId) continue;
      const key = feedKey(item);
      if (reportedViewsRef.current.has(key)) continue;
      reportedViewsRef.current.add(key);
      void recordFeedImpression(session.token, {
        session_id: feed.sessionId,
        source_type: item.source_type ?? 'SOCIAL',
        source_id: sourceId,
        surface: 'FEED',
        watched_ms: 250,
      }).catch(() => {
        // Allow a later visibility event to retry transient failures.
        reportedViewsRef.current.delete(key);
      });
    }
  }, [feed.items.length, feed.sessionId, session?.token]);

  // Stable: the memoized header/rows must not see a new callback identity per render.
  const onTabChange = useCallback((next: FeedTab) => {
    setActiveVideoKey(null);
    setTab(next);
  }, []);
  const onOpenStories = useCallback((initialStoryId?: number) => {
    nav.navigate('Stories', initialStoryId ? { initialStoryId } : {});
  }, [nav]);
  // A deleted post vanishes from the local list immediately (server already
  // confirmed the soft-delete; cache invalidation happens in the card).
  const deletedItem = useCallback((item: FeedItem) => {
    const key = feedKey(item);
    setHiddenKeys((current) => {
      const next = new Set(current);
      next.add(key);
      return next;
    });
  }, []);

  // Memoized so FlatList doesn't get a new data array (forcing a full re-diff)
  // on every parent render — e.g. every viewability tick.
  const visibleItems = useMemo(
    () => feed.items.filter((it) => !hiddenKeys.has(feedKey(it))),
    [feed.items, hiddenKeys],
  );

  const displayItems = visibleItems;

  const notInterested = useCallback(async (sourceType: 'SOCIAL' | 'CURATED', sourceId: number) => {
    if (!session) return;
    const key = `${sourceType}:${sourceId}`;
    setHiddenKeys((current) => {
      const next = new Set(current);
      next.add(key);
      return next;
    });
    try {
      await submitRecommendationAction(session.token, {
        source_type: sourceType,
        source_id: sourceId,
        action: 'NOT_INTERESTED',
      });
    } catch {
      setHiddenKeys((current) => {
        const next = new Set(current);
        next.delete(key);
        return next;
      });
    }
  }, [session]);

  const listHeader = useMemo(() => (
    <FeedListHeader
      token={session?.token}
      myId={session?.user.user_id}
      myName={session?.user.full_name}
      tab={tab}
      onTabChange={onTabChange}
      onOpenStories={onOpenStories}
      onStartQuizZone={() => nav.navigate('Quiz', { returnTo: 'KidsTabs' })}
      online={online}
      error={feed.error}
    />
  ), [session?.token, session?.user.user_id, session?.user.full_name, tab, onTabChange, onOpenStories, nav, online, feed.error]);

  const renderFeedItem = useCallback(({ item }: { item: FeedItem }) => {
    const key = feedKey(item);
    return (
      <FeedRow
        item={item}
        videoActive={focused && foreground && activeVideoKey === key}
        tab={tab}
        nav={nav}
        onNotInterestedItem={notInterested}
        onDeletedItem={deletedItem}
      />
    );
  }, [focused, foreground, activeVideoKey, tab, nav, notInterested, deletedItem]);

  const listFooter = useMemo(() => {
    // Purely visual gate: show the kit end-of-feed card only when real items
    // are rendered and pagination has no more pages. Does not alter fetch,
    // refresh, or pagination behavior.
    if (visibleItems.length === 0 || feed.hasMore || feed.refreshing) return null;
    return <CaughtUpCard />;
  }, [visibleItems.length, feed.hasMore, feed.refreshing]);

  if (feed.loading) return <Screen><Skeleton lines={5} /><LoadingState message="Loading your feed…" /></Screen>;
  if (feed.error instanceof ApiError && feed.error.code === 'disabled_by_parent') return <Screen><DisabledFeature feature="Feed" /></Screen>;
  if (feed.error && feed.items.length === 0) return <Screen><OfflineBanner online={online} /><GateNotice error={feed.error} /><ErrorState message="Could not load your feed." onRetry={feed.retry} /></Screen>;

  return (
    <Screen>
      <FlashList
        data={displayItems}
        keyExtractor={feedKey}
        refreshControl={<RefreshControl refreshing={feed.refreshing} onRefresh={feed.refresh} />}
        ListHeaderComponent={listHeader}
        ListEmptyComponent={<EmptyState title="Nothing here yet" body="When friends share kind posts, they will appear here." />}
        ListFooterComponent={listFooter}
        renderItem={renderFeedItem}
        onViewableItemsChanged={onViewableItemsChanged}
        viewabilityConfig={viewabilityConfig}
        drawDistance={1200}
        onEndReached={feed.loadMore}
        onEndReachedThreshold={0.5}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  trayWrap: { marginTop: spacing.xs, marginBottom: spacing.sm },
  trayContent: { gap: 12, paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  trayCell: { alignItems: 'center', width: 72 },
  trayName: { marginTop: 5, fontSize: 12, color: colors.muted, fontWeight: '600', maxWidth: 72, textAlign: 'center' },
  plusBadge: {
    position: 'absolute',
    right: 2,
    bottom: 2,
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: colors.brand,
    borderWidth: 2,
    borderColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  tabs: {
    flexDirection: 'row',
    borderBottomWidth: 1,
    borderColor: colors.line,
    paddingHorizontal: spacing.md,
    marginTop: spacing.xs,
    backgroundColor: colors.surface,
  },
  tabHit: { flex: 1, minHeight: 44, alignItems: 'center', justifyContent: 'center', gap: 4 },
  tabLabel: { color: colors.muted, fontWeight: '700', fontSize: 14 },
  tabLabelActive: { color: colors.ink, fontWeight: '800' },
  tabIndicator: { height: 2, width: '64%', borderRadius: 1, backgroundColor: 'transparent' },
  tabIndicatorActive: { backgroundColor: colors.brand },
  caughtUpWrap: {
    paddingVertical: 40,
    paddingHorizontal: spacing.xl,
    alignItems: 'center',
    backgroundColor: colors.surface,
  },
  caughtUpCircle: {
    width: 48,
    height: 48,
    borderRadius: 24,
    borderWidth: 2,
    borderColor: colors.ok,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.sm,
  },
  caughtUpTitle: {
    fontSize: 15,
    fontWeight: '700',
    color: colors.ink,
    marginBottom: spacing.xs,
    textAlign: 'center',
  },
  caughtUpSubtitle: {
    fontSize: 13,
    color: colors.muted,
    textAlign: 'center',
    maxWidth: 280,
    lineHeight: 18,
  },
  quizZoneCard: {
    marginHorizontal: spacing.md,
    marginTop: spacing.md,
    marginBottom: spacing.xs,
    padding: spacing.md,
    borderRadius: 16,
    backgroundColor: '#F0F9FF',
    borderWidth: 1.5,
    borderColor: '#BAE6FD',
    shadowColor: '#0284C7',
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.1,
    shadowRadius: 6,
    elevation: 3,
  },
  quizZoneContent: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginBottom: spacing.md,
  },
  quizZoneIconWrap: {
    width: 44,
    height: 44,
    borderRadius: 14,
    backgroundColor: '#E0F2FE',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: spacing.sm,
  },
  quizZoneEmoji: {
    fontSize: 22,
  },
  quizZoneTextWrap: {
    flex: 1,
  },
  quizZoneBadge: {
    alignSelf: 'flex-start',
    backgroundColor: '#E0F2FE',
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 6,
    marginBottom: 4,
  },
  quizZoneBadgeText: {
    fontSize: 10,
    fontWeight: '800',
    color: '#0284C7',
    letterSpacing: 0.5,
  },
  quizZoneTitle: {
    fontSize: 17,
    fontWeight: '900',
    color: colors.ink,
    letterSpacing: -0.3,
    marginBottom: 2,
  },
  quizZoneSubtitle: {
    fontSize: 13,
    color: '#475569',
    lineHeight: 18,
  },
  quizZoneButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.brand,
    paddingVertical: 10,
    paddingHorizontal: spacing.md,
    borderRadius: 12,
  },
  quizZoneButtonPressed: {
    opacity: 0.85,
  },
  quizZoneButtonText: {
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: '700',
  },
});
