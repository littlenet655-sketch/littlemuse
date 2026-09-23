import { memo, useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Animated,
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
} from 'react-native';
import { Feather } from '@expo/vector-icons';
import { useIsFocused } from '@react-navigation/native';
import type { InfiniteData } from '@tanstack/react-query';
import { recordImpressionBatch, type FeedItem, type FeedPage } from '../../api/kidsFeed';
import { ApiError } from '../../api/client';
import { submitRecommendationAction } from '../../api/recommendation';
import { submitReport, toggleLike, toggleSave } from '../../api/kidsSocial';
import { useAuth } from '../../auth/AuthProvider';
import { feedKey, runSocialPostAction, shouldLoadReel, shouldPlayReel, socialPostTarget, socialProfileTarget } from '../../kids/social';
import { useFeed } from '../../kids/useFeed';
import type { ChildScreenProps } from '../../navigation/types';
import { useIsForeground, queryClient } from '../../query/client';
import { invalidateSocialCaches, kidsKeys } from '../../query/keys';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { DisabledFeature, ErrorState, GateNotice } from '../../ui/components';
import { Avatar } from '../../ui/social';
import { colors, shadow } from '../../ui/tokens';
import { ReelPlayer } from '../../video/ReelPlayer';
import type { ImpressionEventPayload } from '../../video/types';
import { QuizBreakCard, isQuizMarker, withQuizBreaks, type QuizMarker } from '../../components/QuizBreakCard';

interface ReelCellProps {
  item: FeedItem;
  index: number;
  activeIndex: number;
  active: boolean;
  nearby: boolean;
  paused: boolean;
  token?: string;
  reelHeight: number;
  windowWidth: number;
  bottomInset: number;
  nav: { navigate: (r: string, p: object) => void };
  onLike: (item: FeedItem) => void;
  onSave: (item: FeedItem) => void;
  onOpenSheet: (item: FeedItem) => void;
  onTogglePause: () => void;
  onMetricsFlush: (payload: ImpressionEventPayload) => void;
  /** Instagram parity: double-tap on the video likes (never unlikes). */
  onDoubleTapLike: (item: FeedItem) => void;
}

/** Compact counts like Instagram: 1.2K, 3.4M. */
function formatCount(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, '')}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1).replace(/\.0$/, '')}K`;
  return `${n}`;
}

/**
 * Memoized reel row: the parent re-renders on every activeIndex/paused change
 * and on every optimistic like/save cache update, but a row only re-renders
 * when its own item identity, playback window flags, or the shared paused
 * state change. This keeps like-taps and scroll ticks from re-rendering (and
 * re-running the playback hook of) every mounted video cell.
 */
const ReelCell = memo(function ReelCell({
  item,
  index,
  activeIndex,
  active,
  nearby,
  paused,
  token,
  reelHeight,
  windowWidth,
  bottomInset,
  nav,
  onLike,
  onSave,
  onOpenSheet,
  onTogglePause,
  onMetricsFlush,
  onDoubleTapLike,
}: ReelCellProps) {
  const post = socialPostTarget(item);
  const profile = socialProfileTarget(item);
  // Instagram parity: tap a truncated caption to expand it. Reset per reel.
  const [captionExpanded, setCaptionExpanded] = useState(false);
  const itemKey = feedKey(item);
  useEffect(() => {
    setCaptionExpanded(false);
  }, [itemKey]);

  return (
    <View style={[styles.reelPage, { height: reelHeight, width: windowWidth }]}>
      {/* Full-bleed Video Background */}
      <View style={StyleSheet.absoluteFill}>
        <ReelPlayer
          item={item}
          active={active}
          nearby={nearby}
          paused={paused}
          onTogglePlay={() => {
            if (index === activeIndex) onTogglePause();
          }}
          onDoubleTap={() => onDoubleTapLike(item)}
          token={token}
          onMetricsFlush={onMetricsFlush}
        />
      </View>

      {/* Bottom readability gradient — two stacked scrims, no new deps */}
      <View style={styles.bottomScrim} pointerEvents="none">
        <View style={styles.bottomScrimUpper} />
        <View style={styles.bottomScrimLower} />
      </View>

      {/* Pause Indicator overlay in center */}
      {paused && index === activeIndex ? (
        <View style={styles.pauseOverlay} pointerEvents="none">
          <View style={styles.pauseIconCircle}>
            <Feather name="pause" size={32} color="#FFFFFF" />
          </View>
        </View>
      ) : null}

      {/* Floating Right Action Column (Instagram Reels style) */}
      <View style={[styles.rightActionsColumn, { bottom: bottomInset + 80 }]}>
        {/* Like Button */}
        <Pressable
          style={styles.actionBtn}
          onPress={() => onLike(item)}
          accessibilityRole="button"
          accessibilityLabel={item.viewer_liked ? 'Unlike' : 'Like'}
          hitSlop={8}
        >
          <View style={[styles.actionIconCircle, item.viewer_liked && styles.actionIconLiked]}>
            <Feather
              name="heart"
              size={24}
              color={item.viewer_liked ? '#EF4444' : '#FFFFFF'}
            />
          </View>
          <Text style={styles.actionLabel}>{formatCount(item.likes ?? 0)}</Text>
        </Pressable>

        {/* Comment Button */}
        {post ? (
          <Pressable
            style={styles.actionBtn}
            onPress={() => nav.navigate('PostDetail', post)}
            accessibilityRole="button"
            accessibilityLabel="Comments"
            hitSlop={8}
          >
            <View style={styles.actionIconCircle}>
              <Feather name="message-circle" size={24} color="#FFFFFF" />
            </View>
            <Text style={styles.actionLabel}>{formatCount(item.comments_count ?? 0)}</Text>
          </Pressable>
        ) : null}

        {/* Bookmark / Save Button */}
        <Pressable
          style={styles.actionBtn}
          onPress={() => onSave(item)}
          accessibilityRole="button"
          accessibilityLabel={item.viewer_saved ? 'Saved' : 'Save'}
          hitSlop={8}
        >
          <View style={styles.actionIconCircle}>
            <Feather
              name="bookmark"
              size={23}
              color={item.viewer_saved ? colors.brand : '#FFFFFF'}
            />
          </View>
          <Text style={styles.actionLabel}>Save</Text>
        </Pressable>

        {/* More / Safety Options */}
        <Pressable
          style={styles.actionBtn}
          onPress={() => onOpenSheet(item)}
          accessibilityRole="button"
          accessibilityLabel="Options"
          hitSlop={8}
        >
          <View style={styles.actionIconCircle}>
            <Feather name="more-horizontal" size={22} color="#FFFFFF" />
          </View>
        </Pressable>
      </View>

      {/* Floating Bottom Metadata (Author, Caption, Audio tag) */}
      <View style={[styles.bottomMetaContainer, { bottom: bottomInset + 18 }]} pointerEvents="box-none">
        {/* Creator Row */}
        <Pressable
          style={styles.creatorRow}
          onPress={() => profile && nav.navigate('OtherProfile', profile)}
          disabled={!profile}
        >
          <Avatar uri={item.avatar_url} name={item.full_name ?? 'F'} size={38} />
          <View style={styles.creatorInfo}>
            <Text style={styles.creatorName} numberOfLines={1}>
              {item.full_name ?? 'Friend'}
            </Text>
          </View>
        </Pressable>

        {/* Caption — tap to expand like Instagram */}
        {item.caption ? (
          <Pressable onPress={() => setCaptionExpanded((v) => !v)}>
            <Text style={styles.reelCaption} numberOfLines={captionExpanded ? undefined : 2}>
              {item.caption}
            </Text>
          </Pressable>
        ) : null}

        {/* Safe Audio Tag */}
        <View style={styles.audioTagRow}>
          <Feather name="music" size={13} color="#CBD5E1" />
          <Text style={styles.audioTagText}>Safe Sound • Kid Approved</Text>
        </View>
      </View>
    </View>
  );
}, (prev, next) =>
  prev.item === next.item &&
  prev.activeIndex === next.activeIndex &&
  prev.active === next.active &&
  prev.nearby === next.nearby &&
  prev.paused === next.paused &&
  prev.token === next.token &&
  prev.onDoubleTapLike === next.onDoubleTapLike,
);

export function ReelsScreen({ navigation }: ChildScreenProps<'KidsTabs'>) {
  const insets = useSafeAreaInsets();
  const { session } = useAuth();
  const { width: windowWidth, height: windowHeight } = useWindowDimensions();
  // Use the actual navigator viewport, not the raw device window. The bottom
  // LittleNet tab bar sits outside this screen; using windowHeight made each
  // paging cell taller than the visible body on some Android devices.
  const [viewportHeight, setViewportHeight] = useState<number | null>(null);
  const REEL_HEIGHT = viewportHeight ?? windowHeight;
  const focused = useIsFocused();
  const feed = useFeed('reels', 8);
  const foreground = useIsForeground();
  const [activeIndex, setActiveIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  // Instagram-style bottom action sheet (visual restyle of the old Alert menu).
  const [sheetItem, setSheetItem] = useState<FeedItem | null>(null);
  const flatListRef = useRef<FlatList<FeedItem | QuizMarker>>(null);
  const impressionBatchRef = useRef<ImpressionEventPayload[]>([]);
  const badgeAnim = useRef(new Animated.Value(1)).current;
  // Per-post in-flight guard for like/save: rapid double-taps used to fire
  // duplicate toggle requests. Keys are action-scoped so a like in flight
  // never blocks a save.
  const toggleBusyRef = useRef<Set<string>>(new Set());
  const displayItems = useMemo(() => withQuizBreaks(feed.items), [feed.items]);

  // Pulse the AI GUARDED badge
  useEffect(() => {
    const pulse = Animated.loop(
      Animated.sequence([
        Animated.timing(badgeAnim, { toValue: 0.6, duration: 900, useNativeDriver: true }),
        Animated.timing(badgeAnim, { toValue: 1, duration: 900, useNativeDriver: true }),
      ]),
    );
    pulse.start();
    return () => pulse.stop();
  }, [badgeAnim]);

  const viewabilityConfig = useRef({ itemVisiblePercentThreshold: 55, minimumViewTime: 80 }).current;
  const onViewableItemsChanged = useRef(({ viewableItems }: { viewableItems: Array<{ index: number | null }> }) => {
    const first = viewableItems.find((row) => typeof row.index === 'number')?.index;
    if (typeof first === 'number') {
      setActiveIndex((current) => current === first ? current : first);
      setPaused(false);
    }
  }).current;

  // Keep the active index inside the loaded window: feed refreshes must not
  // leave it pointing past the end (which would idle every player).
  useEffect(() => {
    if (displayItems.length === 0) {
      if (activeIndex !== 0) setActiveIndex(0);
      return;
    }
    if (activeIndex > displayItems.length - 1) {
      setActiveIndex(displayItems.length - 1);
    }
  }, [displayItems.length, activeIndex]);

  // Flush batched impressions to server
  const flushBatch = useCallback(async () => {
    if (!session?.token || impressionBatchRef.current.length === 0) return;
    const events = [...impressionBatchRef.current];
    impressionBatchRef.current = [];
    try {
      await recordImpressionBatch(session.token, events);
    } catch {
      // Non-blocking telemetry
    }
  }, [session?.token]);

  // Buffer impression events emitted by ReelPlayer
  const handleMetricsFlush = useCallback((payload: ImpressionEventPayload) => {
    if (feed.sessionId && !payload.session_id) {
      payload.session_id = feed.sessionId;
    }
    impressionBatchRef.current.push(payload);
    if (impressionBatchRef.current.length >= 5) {
      void flushBatch();
    }
  }, [feed.sessionId, flushBatch]);

  // Flush on app backgrounding or screen blur
  useEffect(() => {
    if (!foreground || !focused) {
      void flushBatch();
    }
  }, [foreground, focused, flushBatch]);

  // Flush on unmount
  useEffect(() => {
    return () => {
      void flushBatch();
    };
  }, [flushBatch]);

  // Stable callbacks: the memoized ReelCell only re-renders when its own
  // playback flags or item identity change, not when these are recreated.
  const togglePause = useCallback(() => setPaused((v) => !v), []);

  const handleLike = useCallback(async (item: FeedItem) => {
    if (!session) return;
    const socialTarget = socialPostTarget(item);
    if (!socialTarget) return;
    const postId = socialTarget.postId;
    const busyKey = `${postId}:like`;
    if (toggleBusyRef.current.has(busyKey)) return;
    toggleBusyRef.current.add(busyKey);
    try {
      const optimisticLiked = !item.viewer_liked;
      const optimisticLikes = (item.likes ?? 0) + (item.viewer_liked ? -1 : 1);

      const update = (old: InfiniteData<FeedPage> | undefined) =>
        old
          ? {
              ...old,
              pages: old.pages.map((page) => ({
                ...page,
                items: page.items.map((post) =>
                  post.source_type === 'SOCIAL' && post.post_id === postId
                    ? { ...post, viewer_liked: optimisticLiked, likes: optimisticLikes }
                    : post,
                ),
              })),
            }
          : old;

      queryClient.setQueriesData<InfiniteData<FeedPage>>({ queryKey: kidsKeys.reels }, update);
      try {
        const result = await runSocialPostAction(item, (id) => toggleLike(session.token, id));
        if (!result) return;
        queryClient.setQueriesData<InfiniteData<FeedPage>>({ queryKey: kidsKeys.reels }, (old) =>
          old
            ? {
                ...old,
                pages: old.pages.map((page) => ({
                  ...page,
                  items: page.items.map((post) =>
                    post.source_type === 'SOCIAL' && post.post_id === postId
                      ? { ...post, viewer_liked: result.liked, likes: result.likes }
                      : post,
                  ),
                })),
              }
            : old,
        );
        await invalidateSocialCaches([postId]);
      } catch {
        await queryClient.invalidateQueries({ queryKey: kidsKeys.reels });
      }
    } finally {
      toggleBusyRef.current.delete(busyKey);
    }
  }, [session]);

  const handleSave = useCallback(async (item: FeedItem) => {
    if (!session) return;
    const socialTarget = socialPostTarget(item);
    if (!socialTarget) return;
    const postId = socialTarget.postId;
    const busyKey = `${postId}:save`;
    if (toggleBusyRef.current.has(busyKey)) return;
    toggleBusyRef.current.add(busyKey);
    try {
      const optimisticSaved = !item.viewer_saved;

      const update = (old: InfiniteData<FeedPage> | undefined) =>
        old
          ? {
              ...old,
              pages: old.pages.map((page) => ({
                ...page,
                items: page.items.map((post) =>
                  post.source_type === 'SOCIAL' && post.post_id === postId
                    ? { ...post, viewer_saved: optimisticSaved }
                    : post,
                ),
              })),
            }
          : old;

      queryClient.setQueriesData<InfiniteData<FeedPage>>({ queryKey: kidsKeys.reels }, update);
      try {
        const result = await runSocialPostAction(item, (id) => toggleSave(session.token, id));
        if (!result) return;
        await invalidateSocialCaches([postId]);
      } catch {
        await queryClient.invalidateQueries({ queryKey: kidsKeys.reels });
      }
    } finally {
      toggleBusyRef.current.delete(busyKey);
    }
  }, [session]);

  const nav = navigation as unknown as { navigate: (r: string, p: object) => void };

  // Instagram parity: double-tap always likes, never unlikes.
  const handleDoubleTapLike = useCallback((item: FeedItem) => {
    if (!item.viewer_liked) {
      void handleLike(item);
    }
  }, [handleLike]);

  // Stable renderItem: combined with the memoized ReelCell, parent renders
  // (scroll ticks, like-taps, pause toggles) no longer re-render every cell.
  const renderReelItem = useCallback(({ item, index }: { item: FeedItem | QuizMarker; index: number }) => {
    if (isQuizMarker(item)) {
      return (
        <View style={[styles.quizPage, { height: REEL_HEIGHT }]}>
          <QuizBreakCard token={session?.token} fullscreen />
        </View>
      );
    }
    return (
    <ReelCell
      item={item}
      index={index}
      activeIndex={activeIndex}
      active={shouldPlayReel(index, activeIndex, foreground && focused)}
      nearby={shouldLoadReel(index, activeIndex)}
      paused={paused}
      token={session?.token}
      reelHeight={REEL_HEIGHT}
      windowWidth={windowWidth}
      bottomInset={insets.bottom}
      nav={nav}
      onLike={(it) => void handleLike(it)}
      onSave={(it) => void handleSave(it)}
      onOpenSheet={setSheetItem}
      onTogglePause={togglePause}
      onMetricsFlush={handleMetricsFlush}
      onDoubleTapLike={handleDoubleTapLike}
    />
    );
  }, [activeIndex, foreground, focused, paused, session?.token, REEL_HEIGHT, windowWidth, insets.bottom, nav, handleLike, handleSave, togglePause, handleMetricsFlush, handleDoubleTapLike]);

  /** Same report action the old Alert menu ran — now invoked from the action sheet.
   * Awaits the submission: the success confirmation must only show when the
   * server actually accepted the report (fire-and-forget lied on failure). */
  async function performReport(item: FeedItem) {
    if (!session) return;
    const post = socialPostTarget(item);
    if (!post) return;
    try {
      await submitReport(session.token, 'post', post.postId, 'inappropriate');
      Alert.alert('Reported', 'Thank you. Our safety team will review this video promptly.');
    } catch {
      Alert.alert('Could not report', 'Your report could not be sent. Check your connection and try again.');
    }
  }

  /** Same not-interested action the old Alert menu ran — now invoked from the action sheet. */
  function performNotInterested(item: FeedItem) {
    if (!session) return;
    const post = socialPostTarget(item);
    if (!post) return;
    void submitRecommendationAction(session.token, {
      source_type: 'SOCIAL',
      source_id: post.postId,
      action: 'NOT_INTERESTED',
    });
  }

  function closeSheetAnd(run: (item: FeedItem) => void) {
    const item = sheetItem;
    setSheetItem(null);
    if (item) run(item);
  }

  // Guard: initial loading
  if (feed.loading && feed.items.length === 0) {
    return (
      <View style={styles.guardContainer}>
        <View style={[styles.topHeader, { top: insets.top > 0 ? insets.top + 8 : 14 }]}>
          <Text style={styles.topTitle}>Reels</Text>
          <Animated.View style={[styles.topSafeBadge, { opacity: badgeAnim }]}>
            <Feather name="shield" size={12} color="#10B981" />
            <Text style={styles.topSafeBadgeText}>AI GUARDED</Text>
          </Animated.View>
        </View>
        <ActivityIndicator size="large" color="#3B82F6" />
        <Text style={styles.loadingText}>Loading reels…</Text>
      </View>
    );
  }
  if (feed.error instanceof ApiError && feed.error.code === 'disabled_by_parent') {
    return (
      <View style={styles.guardContainer}>
        <DisabledFeature feature="Reels" />
      </View>
    );
  }
  if (feed.error && feed.items.length === 0) {
    return (
      <View style={styles.guardContainer}>
        <GateNotice error={feed.error} />
        <ErrorState message="Could not load reels." onRetry={feed.retry} />
      </View>
    );
  }
  // Guard: authenticated, no error, but truly empty
  if (!feed.loading && feed.items.length === 0) {
    return (
      <View style={styles.guardContainer}>
        <View style={[styles.topHeader, { top: insets.top > 0 ? insets.top + 8 : 14 }]}>
          <Text style={styles.topTitle}>Reels</Text>
          <Animated.View style={[styles.topSafeBadge, { opacity: badgeAnim }]}>
            <Feather name="shield" size={12} color="#10B981" />
            <Text style={styles.topSafeBadgeText}>AI GUARDED</Text>
          </Animated.View>
        </View>
        <View style={styles.emptyWrapper}>
          <View style={styles.emptyIconCircle}>
            <Feather name="film" size={40} color="#60A5FA" />
          </View>
          <Text style={styles.emptyTitle}>No reels yet</Text>
          <Text style={styles.emptyBody}>
            Educational and fun short videos from friends &amp; LittleNet will appear here.
          </Text>
          <Pressable
            style={styles.refreshButton}
            onPress={() => void feed.refresh()}
            accessibilityRole="button"
            accessibilityLabel="Refresh reels"
          >
            <Feather name="refresh-cw" size={14} color="#FFFFFF" />
            <Text style={styles.refreshButtonText}>Refresh</Text>
          </Pressable>
        </View>
      </View>
    );
  }

  return (
    <View
      style={styles.container}
      onLayout={({ nativeEvent }) => {
        const next = Math.round(nativeEvent.layout.height);
        if (next > 0 && next !== viewportHeight) setViewportHeight(next);
      }}
    >
      {/* Floating Top Header — Instagram Reels style */}
      <View style={[styles.topHeader, { top: insets.top > 0 ? insets.top + 8 : 14 }]}>
        <Text style={styles.topTitle}>Reels</Text>
        <Animated.View style={[styles.topSafeBadge, { opacity: badgeAnim }]}>
          <Feather name="shield" size={12} color="#10B981" />
          <Text style={styles.topSafeBadgeText}>AI GUARDED</Text>
        </Animated.View>
      </View>

      {/* Non-blocking error banner when items already loaded */}
      {feed.error ? <GateNotice error={feed.error} /> : null}

      <FlatList<FeedItem | QuizMarker>
        ref={flatListRef}
        data={displayItems}
        style={styles.list}
        keyExtractor={(it) => (isQuizMarker(it) ? it.markerId : `reel:${feedKey(it)}`)}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={feed.refreshing} onRefresh={feed.refresh} tintColor="#FFFFFF" />}
        onViewableItemsChanged={onViewableItemsChanged}
        viewabilityConfig={viewabilityConfig}
        onEndReached={feed.loadMore}
        onEndReachedThreshold={0.5}
        windowSize={3}
        maxToRenderPerBatch={2}
        initialNumToRender={2}
        updateCellsBatchingPeriod={50}
        removeClippedSubviews={false}
        pagingEnabled
        decelerationRate="fast"
        // Snap exactly one page per fling (Android): without this, a fast
        // fling's momentum can skip past a reel and land between pages.
        disableIntervalMomentum
        getItemLayout={(_, index) => ({ length: REEL_HEIGHT, offset: REEL_HEIGHT * index, index })}
        renderItem={renderReelItem}
      />

      {/* Instagram-style bottom action sheet — same actions as the old Alert menu */}
      {sheetItem ? (
        <View style={styles.sheetBackdrop}>
          <Pressable
            style={StyleSheet.absoluteFill}
            onPress={() => setSheetItem(null)}
            accessibilityRole="button"
            accessibilityLabel="Dismiss options"
          />
          <View style={styles.sheet} accessibilityRole="menu">
            <View style={styles.sheetHandle} />
            <Text style={styles.sheetTitle}>Reel Options</Text>
            <Pressable
              style={styles.sheetRow}
              onPress={() => closeSheetAnd(performReport)}
              accessibilityRole="menuitem"
            >
              <Feather name="flag" size={18} color={colors.danger} />
              <Text style={[styles.sheetLabel, styles.sheetLabelDanger]}>Report to Safety Review</Text>
            </Pressable>
            <View style={styles.sheetDivider} />
            <Pressable
              style={styles.sheetRow}
              onPress={() => closeSheetAnd(performNotInterested)}
              accessibilityRole="menuitem"
            >
              <Feather name="eye-off" size={18} color={colors.ink} />
              <Text style={styles.sheetLabel}>Not Interested</Text>
            </Pressable>
            <View style={styles.sheetDivider} />
            <Pressable
              style={styles.sheetCancel}
              onPress={() => setSheetItem(null)}
              accessibilityRole="menuitem"
            >
              <Text style={styles.sheetCancelLabel}>Cancel</Text>
            </Pressable>
          </View>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#000000',
  },
  quizPage: {
    backgroundColor: '#000000',
    justifyContent: 'center',
  },
  // Full-screen guard container for loading/empty/error states
  guardContainer: {
    flex: 1,
    backgroundColor: '#000000',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 14,
  },
  // FlatList fills the full container
  list: {
    flex: 1,
    backgroundColor: '#000000',
  },
  loadingText: {
    color: '#94A3B8',
    fontSize: 14,
    fontWeight: '700',
    marginTop: 4,
  },
  // Empty state wrapper (centered by guardContainer)
  emptyWrapper: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 32,
    gap: 14,
    maxWidth: 340,
  },
  emptyIconCircle: {
    width: 76,
    height: 76,
    borderRadius: 38,
    backgroundColor: 'rgba(59, 130, 246, 0.12)',
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1.5,
    borderColor: 'rgba(59, 130, 246, 0.35)',
    marginBottom: 4,
  },
  emptyTitle: {
    color: '#FFFFFF',
    fontSize: 20,
    fontWeight: '800',
    textAlign: 'center',
  },
  emptyBody: {
    color: '#94A3B8',
    fontSize: 14,
    lineHeight: 20,
    textAlign: 'center',
  },
  refreshButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: '#2563EB',
    paddingHorizontal: 22,
    paddingVertical: 10,
    borderRadius: 22,
    marginTop: 6,
  },
  refreshButtonText: {
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: '700',
  },
  topHeader: {
    position: 'absolute',
    top: 14,
    left: 16,
    zIndex: 10,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  topTitle: {
    fontSize: 22,
    fontWeight: '900',
    color: '#FFFFFF',
    letterSpacing: -0.5,
    textShadowColor: 'rgba(0,0,0,0.6)',
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 3,
  },
  topSafeBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: 'rgba(16, 185, 129, 0.22)',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: 'rgba(16, 185, 129, 0.4)',
  },
  topSafeBadgeText: {
    color: '#6EE7B7',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 0.5,
  },
  reelPage: {
    position: 'relative',
    backgroundColor: '#000000',
    overflow: 'hidden',
  },
  // Subtle dark gradient behind the bottom caption area for readability:
  // two stacked semi-transparent scrims give the fading look without new deps.
  bottomScrim: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    zIndex: 5,
  },
  bottomScrimUpper: {
    height: 100,
    backgroundColor: 'rgba(0,0,0,0.15)',
  },
  bottomScrimLower: {
    height: 140,
    backgroundColor: 'rgba(0,0,0,0.35)',
  },
  pauseOverlay: {
    ...StyleSheet.absoluteFill,
    justifyContent: 'center',
    alignItems: 'center',
  },
  pauseIconCircle: {
    width: 68,
    height: 68,
    borderRadius: 34,
    backgroundColor: 'rgba(0, 0, 0, 0.55)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  rightActionsColumn: {
    position: 'absolute',
    right: 12,
    alignItems: 'center',
    gap: 20,
    zIndex: 10,
  },
  actionBtn: {
    alignItems: 'center',
    gap: 4,
  },
  actionIconCircle: {
    width: 46,
    height: 46,
    borderRadius: 23,
    backgroundColor: 'rgba(0, 0, 0, 0.50)',
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.12)',
  },
  actionIconLiked: {
    backgroundColor: 'rgba(239, 68, 68, 0.2)',
  },
  actionLabel: {
    color: '#FFFFFF',
    fontSize: 12,
    fontWeight: '700',
    textShadowColor: 'rgba(0,0,0,0.7)',
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 2,
  },
  bottomMetaContainer: {
    position: 'absolute',
    left: 14,
    right: 76,
    zIndex: 10,
    gap: 6,
  },
  creatorRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    marginBottom: 8,
  },
  creatorInfo: {
    justifyContent: 'center',
  },
  creatorName: {
    color: '#FFFFFF',
    fontSize: 15,
    fontWeight: '800',
    textShadowColor: 'rgba(0,0,0,0.8)',
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 3,
  },
  reelCaption: {
    color: '#FFFFFF',
    fontSize: 13.5,
    lineHeight: 19,
    marginBottom: 8,
    textShadowColor: 'rgba(0,0,0,0.8)',
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 3,
  },
  audioTagRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: 'rgba(0, 0, 0, 0.45)',
    alignSelf: 'flex-start',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 10,
  },
  audioTagText: {
    color: '#E2E8F0',
    fontSize: 11,
    fontWeight: '600',
  },
  // Bottom action sheet (Instagram-style restyle of the old Alert menu)
  sheetBackdrop: {
    ...StyleSheet.absoluteFill,
    backgroundColor: 'rgba(0,0,0,0.45)',
    justifyContent: 'flex-end',
    zIndex: 30,
  },
  sheet: {
    backgroundColor: '#FFFFFF',
    borderTopLeftRadius: 16,
    borderTopRightRadius: 16,
    paddingHorizontal: 16,
    paddingTop: 10,
    paddingBottom: 24,
    ...shadow.pop,
  },
  sheetHandle: {
    alignSelf: 'center',
    width: 40,
    height: 4,
    borderRadius: 2,
    backgroundColor: '#DBDBDB',
    marginBottom: 10,
  },
  sheetTitle: {
    fontSize: 14,
    fontWeight: '800',
    color: colors.ink,
    textAlign: 'center',
    marginBottom: 12,
  },
  sheetRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingVertical: 12,
  },
  sheetLabel: {
    fontSize: 15,
    fontWeight: '700',
    color: colors.ink,
  },
  sheetLabelDanger: {
    color: colors.danger,
  },
  sheetDivider: {
    height: 1,
    backgroundColor: '#EFEFEF',
  },
  sheetCancel: {
    alignItems: 'center',
    paddingVertical: 12,
  },
  sheetCancelLabel: {
    fontSize: 15,
    fontWeight: '800',
    color: colors.brand,
  },
});
