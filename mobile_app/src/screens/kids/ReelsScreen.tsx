import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Animated,
  Easing,
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
} from 'react-native';
import { Feather } from '@expo/vector-icons';
import { IgIcon } from '../../components/IgIcon';
import { useIsFocused } from '@react-navigation/native';
import type { InfiniteData } from '@tanstack/react-query';
import { recordImpressionBatch, type FeedItem, type FeedPage } from '../../api/kidsFeed';
import { ApiError } from '../../api/client';
import { submitRecommendationAction } from '../../api/recommendation';
import { recordCuratedShare, submitReport, toggleCuratedLike, toggleCuratedSave, toggleFollow, toggleLike, toggleSave } from '../../api/kidsSocial';
import { useAuth } from '../../auth/AuthProvider';
import { engagementTarget, feedKey, shouldLoadReel, shouldPlayReel, socialPostTarget, socialProfileTarget } from '../../kids/social';
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
import { QuizBreakCard } from '../../components/QuizBreakCard';

type ReelFollowStatus = 'Follow' | 'Requested' | 'Following';

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
  onShare: (item: FeedItem) => void;
  onOpenSheet: (item: FeedItem) => void;
  onTogglePause: () => void;
  onMetricsFlush: (payload: ImpressionEventPayload) => void;
  /** Instagram parity: double-tap on the video likes (never unlikes). */
  onDoubleTapLike: (item: FeedItem) => void;
  /** Pulse animation for the kit-style safety pill (stable ref from parent). */
  badgeAnim: Animated.Value;
  myUserId?: number;
  followStatus?: ReelFollowStatus;
  isFollowBusy?: boolean;
  onFollow?: (childId: number) => void;
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
  onShare,
  onOpenSheet,
  onTogglePause,
  onMetricsFlush,
  onDoubleTapLike,
  badgeAnim,
  myUserId,
  followStatus,
  isFollowBusy,
  onFollow,
}: ReelCellProps) {
  const post = socialPostTarget(item);
  const profile = socialProfileTarget(item);
  const toggleMuteRef = useRef<(() => void) | null>(null);
  const [cellMuted, setCellMuted] = useState(false);

  const handleToggleMute = useCallback(() => {
    toggleMuteRef.current?.();
  }, []);
  // Instagram parity: tap a truncated caption to expand it. Reset per reel.
  const [captionExpanded, setCaptionExpanded] = useState(false);
  const itemKey = feedKey(item);
  useEffect(() => {
    setCaptionExpanded(false);
  }, [itemKey]);

  // Kit-style spinning audio disc (visual only; independent of playback logic).
  const discSpin = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    const spin = Animated.loop(
      Animated.timing(discSpin, {
        toValue: 1,
        duration: 5000,
        easing: Easing.linear,
        useNativeDriver: true,
      }),
    );
    spin.start();
    return () => spin.stop();
  }, [discSpin]);
  const discRotate = discSpin.interpolate({
    inputRange: [0, 1],
    outputRange: ['0deg', '360deg'],
  });

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
          onMuteStateChange={setCellMuted}
          toggleMuteRef={toggleMuteRef}
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

      {/* Right action rail — kit style: plain white 28px icons with counts */}
      <View style={[styles.rightActionsColumn, { bottom: bottomInset + 80 }]}>
        {/* Like Button */}
        <Pressable
          style={styles.actionBtn}
          onPress={() => onLike(item)}
          accessibilityRole="button"
          accessibilityLabel={item.viewer_liked ? 'Unlike' : 'Like'}
          hitSlop={8}
        >
          <IgIcon
            name={item.viewer_liked ? 'heart-filled' : 'heart'}
            size={28}
            color={item.viewer_liked ? '#ff3040' : '#FFFFFF'}
          />
          <Text style={styles.actionLabel}>{formatCount(item.likes ?? 0)}</Text>
        </Pressable>

        {/* Comment Button */}
        {post && item.comments_enabled !== false ? (
          <Pressable
            style={styles.actionBtn}
            onPress={() => nav.navigate('PostDetail', post)}
            accessibilityRole="button"
            accessibilityLabel="Comments"
            hitSlop={8}
          >
            <IgIcon name="comment" size={28} color="#FFFFFF" />
            <Text style={styles.actionLabel}>{formatCount(item.comments_count ?? 0)}</Text>
          </Pressable>
        ) : null}

        <Pressable
          style={styles.actionBtn}
          onPress={() => onShare(item)}
          accessibilityRole="button"
          accessibilityLabel="Share"
          hitSlop={8}
        >
          <IgIcon name="send" size={28} color="#FFFFFF" />
          <Text style={styles.actionLabel}>Share</Text>
        </Pressable>

        {/* Bookmark / Save Button — kept (existing feature); restyled to kit icons */}
        <Pressable
          style={styles.actionBtn}
          onPress={() => onSave(item)}
          accessibilityRole="button"
          accessibilityLabel={item.viewer_saved ? 'Saved' : 'Save'}
          hitSlop={8}
        >
          <IgIcon
            name={item.viewer_saved ? 'bookmark-filled' : 'bookmark'}
            size={28}
            color={item.viewer_saved ? colors.brand : '#FFFFFF'}
          />
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
          <IgIcon name="more-horizontal" size={28} color="#FFFFFF" />
        </Pressable>

        {/* Spinning audio disc — tap toggles audio mute */}
        <Pressable
          style={styles.audioDiscWrap}
          onPress={handleToggleMute}
          accessibilityRole="button"
          accessibilityLabel={cellMuted ? 'Audio muted, tap to unmute' : 'Audio on, tap to mute'}
          hitSlop={8}
        >
          <Animated.View style={[styles.audioDisc, { transform: [{ rotate: discRotate }] }]}>
            <View style={styles.audioDiscInner}>
              <Feather name={cellMuted ? 'volume-x' : 'music'} size={11} color="#FFFFFF" />
            </View>
          </Animated.View>
        </Pressable>
      </View>

      {/* Bottom metadata — kit layout: safety pill, creator row, caption, audio */}
      <View style={[styles.bottomMetaContainer, { bottom: bottomInset + 18 }]} pointerEvents="box-none">
        {/* Safety pill — kit's dark translucent pill; pulse logic untouched */}
        <Animated.View style={[styles.safetyPill, { opacity: badgeAnim }]}>
          <Feather name="shield" size={14} color="#4CD964" />
          <Text style={styles.safetyPillText}>🛡️ AI Approved • Classroom Safe</Text>
        </Animated.View>

        {/* Creator Row */}
        <View style={styles.creatorRow}>
          <Pressable
            style={styles.creatorIdentity}
            onPress={() => profile && nav.navigate('OtherProfile', profile)}
            disabled={!profile}
          >
            <Avatar uri={item.avatar_url} name={item.full_name ?? 'F'} size={36} />
            <Text style={styles.creatorName} numberOfLines={1}>
              {item.full_name ?? 'Friend'}
            </Text>
          </Pressable>
          {/* Follow pill: authoritatively wired for SOCIAL creators; disabled/curated for CURATED */}
          {item.source_type === 'SOCIAL' && profile && profile.targetId !== myUserId ? (
            <Pressable
              style={[
                styles.followPill,
                (followStatus === 'Following' || followStatus === 'Requested') && styles.followPillActive,
              ]}
              onPress={() => onFollow?.(profile.targetId)}
              disabled={isFollowBusy}
              accessibilityRole="button"
              accessibilityLabel={`${followStatus ?? 'Follow'} ${item.full_name ?? 'friend'}`}
              hitSlop={6}
            >
              <Text
                style={[
                  styles.followPillText,
                  (followStatus === 'Following' || followStatus === 'Requested') && styles.followPillTextActive,
                ]}
              >
                {isFollowBusy ? '…' : (followStatus ?? 'Follow')}
              </Text>
            </Pressable>
          ) : item.source_type !== 'SOCIAL' ? (
            <Pressable
              style={[styles.followPill, styles.followPillDisabled]}
              disabled={true}
              accessibilityRole="button"
              accessibilityLabel="Curated creator"
            >
              <Text style={styles.followPillText}>Curated</Text>
            </Pressable>
          ) : null}
        </View>

        {/* Caption — tap to expand like Instagram */}
        {item.caption ? (
          <Pressable onPress={() => setCaptionExpanded((v) => !v)}>
            <Text style={styles.reelCaption} numberOfLines={captionExpanded ? undefined : 2}>
              {item.caption}
            </Text>
          </Pressable>
        ) : null}

        {/* Audio row — tap toggles authoritative mute */}
        <Pressable
          style={styles.audioTagRow}
          onPress={handleToggleMute}
          accessibilityRole="button"
          accessibilityLabel={cellMuted ? 'Audio muted, tap to turn on' : 'Audio on, tap to mute'}
          hitSlop={8}
        >
          <Feather name={cellMuted ? 'volume-x' : 'music'} size={14} color="rgba(255,255,255,0.9)" />
          <Text style={styles.audioTagText}>
            {cellMuted ? 'Audio off • Tap to turn on' : 'Safe Sound • Kid Approved'}
          </Text>
        </Pressable>
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
  prev.onDoubleTapLike === next.onDoubleTapLike &&
  prev.followStatus === next.followStatus &&
  prev.isFollowBusy === next.isFollowBusy,
);

export function ReelsScreen({ navigation }: ChildScreenProps<'KidsTabs'>) {
  const nav = navigation as unknown as { navigate: (r: string, p: object) => void };
  const insets = useSafeAreaInsets();
  const { session, refreshMe } = useAuth();
  const { width: windowWidth, height: windowHeight } = useWindowDimensions();
  // Measure the actual navigator viewport: raw device height includes the tab
  // bar on some Android devices and causes cells to land between pages.
  const [viewportHeight, setViewportHeight] = useState<number | null>(null);
  const REEL_HEIGHT = viewportHeight ?? windowHeight;
  const focused = useIsFocused();
  const feed = useFeed('reels', 8);
  const displayItems = feed.items;
  const loadMoreRef = useRef(feed.loadMore);
  loadMoreRef.current = feed.loadMore;
  const foreground = useIsForeground();
  const [activeIndex, setActiveIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const [followStates, setFollowStates] = useState<Record<number, ReelFollowStatus>>({});
  const [followBusyIds, setFollowBusyIds] = useState<Set<number>>(new Set());

  // Task 4: Camera buttons navigation to CreateTab with initialKind: 'reel'
  const openReelCamera = useCallback(() => {
    nav.navigate('KidsTabs', { tab: 'CreateTab', initialKind: 'reel' });
  }, [nav]);

  // Task 8: SOCIAL Follow with optimistic UI and authoritative rollback
  const onFollowChild = useCallback(async (childId: number) => {
    if (!session || followBusyIds.has(childId)) return;
    const currentStatus = followStates[childId] ?? 'Follow';
    const nextStatus: ReelFollowStatus = currentStatus === 'Follow' ? 'Requested' : 'Follow';

    setFollowBusyIds((prev) => new Set(prev).add(childId));
    setFollowStates((prev) => ({ ...prev, [childId]: nextStatus }));

    try {
      const res = await toggleFollow(session.token, childId);
      if (res?.ok && res.status) {
        const s = res.status.toLowerCase();
        const authoritative: ReelFollowStatus =
          s === 'following' || s === 'connected' ? 'Following' :
          s === 'requested' || s === 'pending' ? 'Requested' : 'Follow';
        setFollowStates((prev) => ({ ...prev, [childId]: authoritative }));
      }
      await invalidateSocialCaches();
    } catch {
      // Roll back to prior state on failure
      setFollowStates((prev) => ({ ...prev, [childId]: currentStatus }));
    } finally {
      setFollowBusyIds((prev) => {
        const next = new Set(prev);
        next.delete(childId);
        return next;
      });
    }
  }, [session, followStates, followBusyIds]);
  const [quizLocked, setQuizLocked] = useState(false);
  // Instagram-style bottom action sheet (visual restyle of the old Alert menu).
  const [sheetItem, setSheetItem] = useState<FeedItem | null>(null);
  const flatListRef = useRef<FlatList<FeedItem>>(null);
  const impressionBatchRef = useRef<ImpressionEventPayload[]>([]);
  const badgeAnim = useRef(new Animated.Value(1)).current;
  // Per-post in-flight guard for like/save: rapid double-taps used to fire
  // duplicate toggle requests. Keys are action-scoped so a like in flight
  // never blocks a save.
  const toggleBusyRef = useRef<Set<string>>(new Set());

  // Server latch persistence: if the server says a compulsory quiz is required,
  // lock scrolling and pause playback immediately (e.g. after app restart, tab change).
  useEffect(() => {
    if (session?.user?.quiz_required) {
      setQuizLocked(true);
      setPaused(true);
    }
  }, [session?.user?.quiz_required]);

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
  const onViewableItemsChanged = useCallback(({ viewableItems }: { viewableItems: Array<{ index: number | null; item?: FeedItem }> }) => {
    const firstRow = viewableItems.find((row) => typeof row.index === 'number');
    const first = firstRow?.index;
    if (typeof first === 'number') {
      setActiveIndex((current) => current === first ? current : first);
      setPaused(false);
      if (first >= displayItems.length - 2) loadMoreRef.current();
    }
  }, [displayItems.length]);

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
      const result = await recordImpressionBatch(session.token, events);
      if (result.quiz_required) {
        setQuizLocked(true);
        setPaused(true);
        await refreshMe();
      }
    } catch (error) {
      if (error instanceof ApiError && error.code === 'quiz_required') {
        setQuizLocked(true);
        setPaused(true);
        await refreshMe();
      }
      // Impression telemetry itself remains non-blocking.
    }
  }, [session?.token, refreshMe]);

  // Buffer impression events emitted by ReelPlayer
  const handleMetricsFlush = useCallback((payload: ImpressionEventPayload) => {
    if (feed.sessionId && !payload.session_id) {
      payload.session_id = feed.sessionId;
    }
    impressionBatchRef.current.push(payload);
    // One lightweight request per meaningfully watched Reel keeps the persisted
    // random 2–5 gate exact. This fires when a Reel leaves the active slot, not
    // on video frames or playback ticks.
    void flushBatch();
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
    const target = engagementTarget(item);
    if (!target) return;
    const { sourceType, sourceId } = target;
    const busyKey = `${sourceType}:${sourceId}:like`;
    if (toggleBusyRef.current.has(busyKey)) return;
    toggleBusyRef.current.add(busyKey);
    const matches = (post: FeedItem) =>
      post.source_type === sourceType && Number(post.source_id ?? post.post_id) === sourceId;
    const update = (old: InfiniteData<FeedPage> | undefined, liked: boolean, likes: number) =>
      old ? {
        ...old,
        pages: old.pages.map((page) => ({
          ...page,
          items: page.items.map((post) => matches(post) ? { ...post, viewer_liked: liked, likes } : post),
        })),
      } : old;
    try {
      const optimisticLiked = !item.viewer_liked;
      const optimisticLikes = Math.max(0, (item.likes ?? 0) + (item.viewer_liked ? -1 : 1));
      queryClient.setQueriesData<InfiniteData<FeedPage>>({ queryKey: kidsKeys.reels }, (old) => update(old, optimisticLiked, optimisticLikes));
      const result = sourceType === 'CURATED'
        ? await toggleCuratedLike(session.token, sourceId)
        : await toggleLike(session.token, sourceId);
      queryClient.setQueriesData<InfiniteData<FeedPage>>({ queryKey: kidsKeys.reels }, (old) => update(old, result.liked, result.likes));
      if (sourceType === 'SOCIAL') await invalidateSocialCaches([sourceId]);
    } catch {
      await queryClient.invalidateQueries({ queryKey: kidsKeys.reels });
    } finally {
      toggleBusyRef.current.delete(busyKey);
    }
  }, [session]);

  const handleSave = useCallback(async (item: FeedItem) => {
    if (!session) return;
    const target = engagementTarget(item);
    if (!target) return;
    const { sourceType, sourceId } = target;
    const busyKey = `${sourceType}:${sourceId}:save`;
    if (toggleBusyRef.current.has(busyKey)) return;
    toggleBusyRef.current.add(busyKey);
    const matches = (post: FeedItem) =>
      post.source_type === sourceType && Number(post.source_id ?? post.post_id) === sourceId;
    const update = (old: InfiniteData<FeedPage> | undefined, saved: boolean) =>
      old ? {
        ...old,
        pages: old.pages.map((page) => ({
          ...page,
          items: page.items.map((post) => matches(post) ? { ...post, viewer_saved: saved } : post),
        })),
      } : old;
    try {
      const optimisticSaved = !item.viewer_saved;
      queryClient.setQueriesData<InfiniteData<FeedPage>>({ queryKey: kidsKeys.reels }, (old) => update(old, optimisticSaved));
      const result = sourceType === 'CURATED'
        ? await toggleCuratedSave(session.token, sourceId)
        : await toggleSave(session.token, sourceId);
      queryClient.setQueriesData<InfiniteData<FeedPage>>({ queryKey: kidsKeys.reels }, (old) => update(old, result.saved));
      if (sourceType === 'SOCIAL') await invalidateSocialCaches([sourceId]);
    } catch {
      await queryClient.invalidateQueries({ queryKey: kidsKeys.reels });
    } finally {
      toggleBusyRef.current.delete(busyKey);
    }
  }, [session]);

  const handleShare = useCallback(async (item: FeedItem) => {
    if (!session) return;
    const target = engagementTarget(item);
    if (!target) return;
    if (target.sourceType === 'SOCIAL') {
      const post = socialPostTarget(item);
      if (post) nav.navigate('PostDetail', { ...post, openShare: true });
      return;
    }
    try {
      await recordCuratedShare(session.token, target.sourceId);
    } catch {
      // Analytics failure does not relax the child sharing boundary.
    }
    Alert.alert(
      'Sharing stays inside LittleMuse',
      'Curated learning reels cannot be sent through unrestricted external apps from a child account. Save it to revisit it safely.',
    );
  }, [session, nav]);


  // Instagram parity: double-tap always likes, never unlikes.
  const handleDoubleTapLike = useCallback((item: FeedItem) => {
    if (!item.viewer_liked) {
      void handleLike(item);
    }
  }, [handleLike]);

  // Stable renderItem: combined with the memoized ReelCell, parent renders
  // (scroll ticks, like-taps, pause toggles) no longer re-render every cell.
  const renderReelItem = useCallback(({ item, index }: { item: FeedItem; index: number }) => {
    return (
    <ReelCell
      item={item}
      index={index}
      activeIndex={activeIndex}
      active={!quizLocked && shouldPlayReel(index, activeIndex, foreground && focused)}
      nearby={!quizLocked && shouldLoadReel(index, activeIndex)}
      paused={paused || quizLocked}
      token={session?.token}
      reelHeight={REEL_HEIGHT}
      windowWidth={windowWidth}
      bottomInset={insets.bottom}
      nav={nav}
      onLike={(it) => void handleLike(it)}
      onSave={(it) => void handleSave(it)}
      onShare={(it) => void handleShare(it)}
      onOpenSheet={setSheetItem}
      onTogglePause={togglePause}
      onMetricsFlush={handleMetricsFlush}
      onDoubleTapLike={handleDoubleTapLike}
      badgeAnim={badgeAnim}
    />
    );
  }, [activeIndex, foreground, focused, paused, quizLocked, session?.token, REEL_HEIGHT, windowWidth, insets.bottom, nav, handleLike, handleSave, handleShare, togglePause, handleMetricsFlush, handleDoubleTapLike]);

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
          <View style={styles.topTitleRow}>
            <Text style={styles.topTitle}>Reels</Text>
            <Feather name="chevron-down" size={20} color="#FFFFFF" />
          </View>
          <Pressable
            style={styles.cameraBtn}
            onPress={openReelCamera}
            accessibilityRole="button"
            accessibilityLabel="Create reel"
            hitSlop={8}
          >
            <Feather name="camera" size={26} color="#FFFFFF" />
          </Pressable>
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
          <View style={styles.topTitleRow}>
            <Text style={styles.topTitle}>Reels</Text>
            <Feather name="chevron-down" size={20} color="#FFFFFF" />
          </View>
          <Pressable
            style={styles.cameraBtn}
            onPress={openReelCamera}
            accessibilityRole="button"
            accessibilityLabel="Create reel"
            hitSlop={8}
          >
            <Feather name="camera" size={26} color="#FFFFFF" />
          </Pressable>
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
    <View style={styles.container} onLayout={(event) => { const h = event.nativeEvent.layout.height; if (h > 0 && h !== viewportHeight) setViewportHeight(h); }}>
      {/* Top header — kit: "Reels" + chevron (left), camera (right) */}
      <View style={[styles.topHeader, { top: insets.top > 0 ? insets.top + 8 : 14 }]}>
        <View style={styles.topTitleRow}>
          <Text style={styles.topTitle}>Reels</Text>
          <Feather name="chevron-down" size={20} color="#FFFFFF" />
        </View>
        <Pressable
          style={styles.cameraBtn}
          onPress={openReelCamera}
          accessibilityRole="button"
          accessibilityLabel="Create reel"
          hitSlop={8}
        >
          <Feather name="camera" size={26} color="#FFFFFF" />
        </Pressable>
      </View>

      {/* Non-blocking error banner when items already loaded */}
      {feed.error ? <GateNotice error={feed.error} /> : null}

      <FlatList<FeedItem>
        ref={flatListRef}
        data={displayItems}
        style={styles.list}
        keyExtractor={(it) => `reel:${feedKey(it)}`}
        showsVerticalScrollIndicator={false}
        scrollEnabled={!quizLocked}
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

      {/* Full-screen non-skippable brain break lock if server has latch active */}
      {quizLocked ? (
        <View style={[StyleSheet.absoluteFill, styles.lockedOverlay]}>
          <QuizBreakCard
            token={session?.token}
            fullscreen
            completed={false}
            onCompleted={async () => {
              if (!session?.token) return;
              setPaused(true);
              try {
                const refreshed = await refreshMe();
                const stillRequired = refreshed.user.quiz_required || refreshed.onboarding?.quiz_required;
                setQuizLocked(Boolean(stillRequired));
                if (!stillRequired) setPaused(false);
              } catch {
                // Keep the server latch closed until an authoritative refresh succeeds.
                setQuizLocked(true);
                setPaused(true);
              }
            }}
          />
        </View>
      ) : null}

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
    left: 0,
    right: 0,
    zIndex: 10,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
  },
  topTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 2,
  },
  topTitle: {
    fontSize: 20,
    fontWeight: '700',
    color: '#FFFFFF',
    letterSpacing: -0.3,
    textShadowColor: 'rgba(0,0,0,0.6)',
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 3,
  },
  cameraBtn: {
    width: 40,
    height: 40,
    justifyContent: 'center',
    alignItems: 'flex-end',
  },
  quizPage: {
    width: '100%',
    backgroundColor: '#000000',
    justifyContent: 'center',
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
    right: 10,
    alignItems: 'center',
    gap: 20,
    zIndex: 10,
  },
  actionBtn: {
    alignItems: 'center',
    gap: 6,
  },
  actionLabel: {
    color: '#FFFFFF',
    fontSize: 12,
    fontWeight: '400',
    textShadowColor: 'rgba(0,0,0,0.7)',
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 2,
  },
  // Kit spinning audio disc
  audioDiscWrap: {
    marginTop: 4,
  },
  audioDisc: {
    width: 30,
    height: 30,
    borderRadius: 15,
    backgroundColor: '#181818',
    borderWidth: 2,
    borderColor: 'rgba(255,255,255,0.7)',
    padding: 3,
    justifyContent: 'center',
    alignItems: 'center',
  },
  audioDiscInner: {
    width: '100%',
    height: '100%',
    borderRadius: 999,
    backgroundColor: '#000000',
    borderWidth: 1,
    borderColor: '#404040',
    justifyContent: 'center',
    alignItems: 'center',
  },
  bottomMetaContainer: {
    position: 'absolute',
    left: 14,
    right: 76,
    zIndex: 10,
  },
  // Kit's dark translucent safety pill (pulse logic untouched)
  safetyPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: 'rgba(0, 0, 0, 0.45)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.1)',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 999,
    alignSelf: 'flex-start',
    marginBottom: 10,
  },
  safetyPillText: {
    color: 'rgba(255,255,255,0.95)',
    fontSize: 11,
    fontWeight: '500',
    letterSpacing: 0.2,
  },
  creatorRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 10,
  },
  creatorIdentity: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    flexShrink: 1,
    minWidth: 0,
  },
  creatorName: {
    color: '#FFFFFF',
    fontSize: 14,
    fontWeight: '600',
    flexShrink: 1,
    textShadowColor: 'rgba(0,0,0,0.8)',
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 3,
  },
  followPill: {
    marginLeft: 4,
    paddingHorizontal: 12,
    paddingVertical: 4,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.6)',
    backgroundColor: 'transparent',
    flexShrink: 0,
  },
  followPillText: {
    color: '#FFFFFF',
    fontSize: 12,
    fontWeight: '600',
  },
  reelCaption: {
    color: '#FFFFFF',
    fontSize: 13,
    lineHeight: 18,
    marginBottom: 10,
    textShadowColor: 'rgba(0,0,0,0.8)',
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 3,
  },
  audioTagRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  audioTagText: {
    color: 'rgba(255,255,255,0.9)',
    fontSize: 12,
    fontWeight: '400',
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
  lockedOverlay: {
    backgroundColor: '#000000',
    zIndex: 9999,
    justifyContent: 'center',
    alignItems: 'center',
  },
  followPillActive: {
    backgroundColor: 'rgba(255, 255, 255, 0.25)',
    borderColor: 'rgba(255, 255, 255, 0.4)',
  },
  followPillTextActive: {
    color: '#FFFFFF',
    fontWeight: '700',
  },
  followPillDisabled: {
    opacity: 0.6,
  },
});