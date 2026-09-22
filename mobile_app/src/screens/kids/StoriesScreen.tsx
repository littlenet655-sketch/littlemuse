import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Animated, Image, PanResponder, Pressable, ScrollView, StyleSheet, Text, View, useWindowDimensions } from 'react-native';
import { Feather } from '@expo/vector-icons';
import { useIsFocused } from '@react-navigation/native';
import { fetchKidsHome, recordStoryView, type StoryItem } from '../../api/kidsFeed';
import { deleteStory } from '../../api/kidsSocial';
import { fetchStoryViewers, type StoryViewer } from '../../api/kidsUpload';
import { useAuth } from '../../auth/AuthProvider';
import { VideoMedia } from '../../kids/VideoMedia';
import type { ChildScreenProps } from '../../navigation/types';
import { useIsForeground } from '../../query/client';
import { Avatar, StoryRing, TimeAgo, shortAgo } from '../../ui/social';
import { Button, EmptyState, ErrorState, LoadingState, Screen } from '../../ui/components';
import { colors, spacing } from '../../ui/tokens';

const IMAGE_DURATION = 5000;
const STORY_TTL_MS = 24 * 3600 * 1000;
const REFRESH_STALE_MS = 30_000;

/**
 * Server sends more than the base StoryItem declares (it serializes the whole
 * post row): owner id, creation time, and whether the viewer already saw it.
 */
interface RichStory extends StoryItem {
  child_id?: number;
  created_at?: string;
  viewed?: boolean;
}

function expiresInLabel(createdAt?: string): string | null {
  if (!createdAt) return null;
  const created = Date.parse(createdAt);
  if (Number.isNaN(created)) return null;
  const remaining = STORY_TTL_MS - (Date.now() - created);
  if (remaining <= 0) return 'Expired';
  const hours = Math.floor(remaining / 3600000);
  const mins = Math.floor((remaining % 3600000) / 60000);
  return hours > 0 ? `Expires in ${hours}h ${mins}m` : `Expires in ${mins}m`;
}

/** Full-screen story viewer. Stories are already filtered by the server's public-safety rules. */
export function StoriesScreen({ navigation }: ChildScreenProps<'KidsTabs'>) {
  // Loose navigate cast: CreateTab accepts an initialKind param at runtime
  // (see CreateScreen), which types.ts deliberately leaves as undefined.
  const nav = navigation as unknown as { navigate: (r: string, p?: object) => void };
  const { session } = useAuth();
  const { height } = useWindowDimensions();
  const focused = useIsFocused();
  const foreground = useIsForeground();
  const [stories, setStories] = useState<RichStory[]>([]);
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [imgError, setImgError] = useState(false);
  const [viewers, setViewers] = useState<StoryViewer[] | null>(null);
  const [viewersOpen, setViewersOpen] = useState(false);
  const [storyDeleting, setStoryDeleting] = useState(false);
  const [storyDeleteError, setStoryDeleteError] = useState('');
  const mounted = useRef(true);
  const lastLoadedAt = useRef(0);
  const progressAnim = useRef(new Animated.Value(0)).current;
  const progressValueRef = useRef(0);

  // Mirror the animated progress so pause/resume can continue from the true
  // remaining time instead of restarting the story duration.
  useEffect(() => {
    const id = progressAnim.addListener(({ value }) => {
      progressValueRef.current = value;
    });
    return () => progressAnim.removeListener(id);
  }, [progressAnim]);

  // New story (or fresh list) → progress restarts. Declared before the timer
  // effect so the reset lands before the timer reads the value.
  useEffect(() => {
    progressValueRef.current = 0;
    progressAnim.setValue(0);
  }, [index, stories, progressAnim]);

  const load = useCallback(async () => {
    if (!session) return;
    setError(null);
    try {
      const home = await fetchKidsHome(session.token);
      if (mounted.current) {
        setStories((home.stories ?? []) as RichStory[]);
        lastLoadedAt.current = Date.now();
      }
    } catch (err) {
      if (mounted.current) setError(err);
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, [session?.token]);

  useEffect(() => {
    mounted.current = true;
    setLoading(true);
    void load();
    return () => {
      mounted.current = false;
    };
  }, [load]);

  // A story published from CreateScreen lands here when the tab regains focus.
  // Staleness-guarded so every tab visit doesn't refetch.
  useEffect(() => {
    if (focused && !loading && Date.now() - lastLoadedAt.current > REFRESH_STALE_MS) {
      void load();
    }
  }, [focused, loading, load]);

  const current = stories[index];
  const isVideo = current?.media_type?.toUpperCase() === 'VIDEO';
  const myId = session?.user.user_id;
  const isOwnStory = Boolean(current && myId && current.child_id === myId);
  const completedRef = useRef<Record<number, boolean>>({});

  // Keep the index valid when the list shrinks (e.g. stories expiring).
  useEffect(() => {
    if (stories.length > 0 && index > stories.length - 1) setIndex(0);
  }, [stories.length, index]);

  useEffect(() => {
    setPaused(false);
    setImgError(false);
    if (session?.token && current?.post_id) {
      // Record initial story view at start of playback (0.1 completion ratio)
      void recordStoryView(session.token, current.post_id, 0.1).catch(() => {});
    }
  }, [index, current?.post_id, session?.token]);

  // Viewer list for the child's OWN story (server enforces ownership).
  useEffect(() => {
    setViewers(null);
    setViewersOpen(false);
    if (isOwnStory && session?.token && current?.post_id) {
      const storyId = current.post_id;
      void fetchStoryViewers(session.token, storyId)
        .then((res) => {
          if (mounted.current) setViewers(res.viewers ?? []);
        })
        .catch(() => {
          // Viewer list is a bonus — never block the story itself.
        });
    }
  }, [index, current?.post_id, isOwnStory, session?.token]);

  function markStoryComplete(postId: number) {
    if (session?.token && postId && !completedRef.current[postId]) {
      completedRef.current[postId] = true;
      void recordStoryView(session.token, postId, 1.0).catch(() => {});
    }
  }

  function confirmDeleteStory() {
    Alert.alert(
      'Delete this story?',
      'It will be removed for everyone and cannot be undone.',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Delete', style: 'destructive', onPress: () => void doDeleteStory() },
      ],
    );
  }

  async function doDeleteStory() {
    if (!session?.token || !current || storyDeleting) return;
    const storyId = current.post_id;
    setStoryDeleting(true);
    setStoryDeleteError('');
    try {
      await deleteStory(session.token, storyId);
      // Drop it locally; the existing index guard resets to 0 if the index
      // falls off the end of the shortened list.
      setStories((prev) => prev.filter((story) => story.post_id !== storyId));
    } catch (err) {
      setStoryDeleteError(err instanceof Error ? err.message : 'Could not delete this story. Try again.');
    } finally {
      setStoryDeleting(false);
    }
  }

  const advance = useCallback(() => {
    if (!current) return;
    markStoryComplete(current.post_id);
    setIndex((value) => (value < stories.length - 1 ? value + 1 : 0));
  }, [current, stories.length, session?.token]);

  // Image-story auto-advance with an animated progress bar. Pauses on manual
  // pause, navigation blur, AND app backgrounding (foreground gate). Pause
  // freezes the bar; resume continues from the remaining time.
  useEffect(() => {
    if (!current || isVideo || !stories.length || !focused || !foreground) {
      progressValueRef.current = 0;
      progressAnim.setValue(0);
      return;
    }
    if (paused) return;
    const remaining = Math.max(500, Math.round(IMAGE_DURATION * (1 - progressValueRef.current)));
    progressAnim.setValue(progressValueRef.current);
    const anim = Animated.timing(progressAnim, {
      toValue: 1,
      duration: remaining,
      useNativeDriver: false,
    });
    anim.start();
    const timer = setTimeout(advance, remaining);
    return () => {
      anim.stop();
      clearTimeout(timer);
    };
  }, [index, current?.post_id, isVideo, stories.length, paused, focused, foreground, advance, progressAnim]);

  // Fresh signed URLs for story video: the home payload's media_url can expire
  // mid-session, so VideoMedia gets one bounded refresh via a home refetch.
  const refreshStoryMedia = useCallback(async (): Promise<string | null> => {
    if (!session?.token || !current?.post_id) return null;
    try {
      const home = await fetchKidsHome(session.token);
      const fresh = (home.stories ?? []).find((s) => s.post_id === current.post_id);
      return fresh?.media_url ?? null;
    } catch {
      return null;
    }
  }, [session?.token, current?.post_id]);

  if (loading) return <Screen><LoadingState message="Loading stories…" /></Screen>;
  if (error) return <Screen><ErrorState message="Could not load stories." onRetry={() => void load()} /></Screen>;
  if (!current) return <Screen><EmptyState title="No stories" body="New stories from friends will appear here." /><Button label="Create a story" onPress={() => nav.navigate('CreateTab', { initialKind: 'story' })} /></Screen>;

  const next = () => advance();
  const previous = () => setIndex((value) => Math.max(0, value - 1));
  const expiryLabel = isOwnStory ? expiresInLabel(current.created_at) : null;

  // Instagram parity: swipe down anywhere on the viewer to close it. Only a
  // deliberate downward swipe claims the gesture — plain taps still reach the
  // tap zones below.
  const swipeDown = useRef(
    PanResponder.create({
      onMoveShouldSetPanResponder: (_, gesture) =>
        gesture.dy > 24 && Math.abs(gesture.dy) > Math.abs(gesture.dx) * 1.5,
      onPanResponderRelease: (_, gesture) => {
        if (gesture.dy > 90) navigation.goBack();
      },
    }),
  ).current;

  return (
    <Screen>
      {/* Swipe-down-to-close is disabled while the viewer-list sheet is open:
          pulling down at the top of that list must not dismiss the screen. */}
      <View style={[styles.viewer, { height }]} {...(viewersOpen ? {} : swipeDown.panHandlers)}>
        <View style={styles.top}>
          <View style={styles.progressRow}>
            {stories.map((story, storyIndex) => (
              <View key={story.post_id} style={styles.progressTrack}>
                {storyIndex < index ? (
                  <View style={[styles.progress, styles.complete]} />
                ) : storyIndex === index && !isVideo ? (
                  <Animated.View
                    style={[
                      styles.progress,
                      {
                        width: progressAnim.interpolate({
                          inputRange: [0, 1],
                          outputRange: ['0%', '100%'],
                        }),
                      },
                    ]}
                  />
                ) : null}
              </View>
            ))}
          </View>
          <View style={styles.identity}>
            <StoryRing size={44} seen={false}>
              <Avatar uri={current.avatar_url} name={current.full_name ?? 'Friend'} size={32} />
            </StoryRing>
            <View style={styles.identityMeta}>
              <View style={styles.nameRow}>
                <Text style={styles.name}>{current.full_name ?? 'Friend'}</Text>
                {current.created_at && !Number.isNaN(Date.parse(current.created_at)) ? (
                  <Text style={styles.timestamp}> · {shortAgo(Date.now() - Date.parse(current.created_at))}</Text>
                ) : null}
              </View>
              {expiryLabel ? <Text style={styles.expiry}>{expiryLabel}</Text> : null}
            </View>
            {isOwnStory && viewers ? (
              <Pressable
                onPress={() => setViewersOpen((v) => !v)}
                style={styles.viewersBtn}
                accessibilityRole="button"
                accessibilityLabel={`Viewed by ${viewers.length} friends`}
              >
                <Feather name="eye" size={14} color="#FFFFFF" />
                <Text style={styles.viewersText}>{viewers.length}</Text>
              </Pressable>
            ) : null}
            <Pressable onPress={() => nav.navigate('CreateTab', { initialKind: 'story' })} style={styles.create}>
              <Text style={styles.createText}>＋ Story</Text>
            </Pressable>
            {isOwnStory ? (
              <Pressable
                onPress={confirmDeleteStory}
                disabled={storyDeleting}
                style={[styles.close, storyDeleting && styles.deleting]}
                accessibilityRole="button"
                accessibilityLabel="Delete this story"
                hitSlop={8}
              >
                <Feather name="trash-2" size={16} color="#FFFFFF" />
              </Pressable>
            ) : null}
            <Pressable
              onPress={() => navigation.goBack()}
              style={styles.close}
              accessibilityRole="button"
              accessibilityLabel="Close stories"
              hitSlop={8}
            >
              <Feather name="x" size={18} color="#FFFFFF" />
            </Pressable>
          </View>
        </View>
        <View style={styles.media}>
          {current.media_url && isVideo ? (
            <VideoMedia
              key={current.post_id}
              source={current.media_url}
              posterUrl={current.poster_url}
              active={!paused && focused}
              height={height}
              refreshSource={refreshStoryMedia}
              onComplete={advance}
            />
          ) : null}
          {current.media_url && !isVideo && !imgError ? (
            <Image
              source={{ uri: current.media_url }}
              style={styles.image}
              resizeMode="cover"
              onError={() => setImgError(true)}
            />
          ) : null}
          {current.media_url && !isVideo && imgError ? (
            <View style={styles.imgFallback}>
              <Feather name="image" size={32} color="rgba(255,255,255,0.6)" />
              <Text style={styles.imgFallbackText}>Couldn't load this story.</Text>
              <Pressable style={styles.imgRetry} onPress={() => setImgError(false)} accessibilityRole="button" accessibilityLabel="Retry loading story">
                <Feather name="refresh-cw" size={14} color="#FFFFFF" />
                <Text style={styles.imgRetryText}>Retry</Text>
              </Pressable>
            </View>
          ) : null}
          {!current.media_url ? <Text style={styles.missing}>This story has no media.</Text> : null}
          <Pressable accessibilityLabel="Previous story" onPress={previous} style={styles.leftTap} />
          <Pressable accessibilityLabel={paused ? 'Resume story' : 'Pause story'} onPress={() => setPaused((value) => !value)} style={styles.centerTap} />
          <Pressable accessibilityLabel="Next story" onPress={next} style={styles.rightTap} />
          {paused ? <View pointerEvents="none" style={styles.pause}><Text style={styles.pauseText}>Ⅱ</Text><Text style={styles.pauseLabel}>Paused</Text></View> : null}
          {current.caption ? (
            <View style={styles.captionOverlay} pointerEvents="none">
              <Text style={styles.caption}>{current.caption}</Text>
            </View>
          ) : null}
        </View>

        {/* Viewer list sheet (own stories only) */}
        {viewersOpen && viewers ? (
          <View style={styles.viewerSheet}>
            <View style={styles.dragHandle} />
            <View style={styles.viewerSheetHeader}>
              <Text style={styles.viewerSheetTitle}>
                Viewed by {viewers.length}
              </Text>
              <Pressable onPress={() => setViewersOpen(false)} accessibilityLabel="Close viewer list" hitSlop={8}>
                <Feather name="x" size={18} color="#FFFFFF" />
              </Pressable>
            </View>
            <ScrollView style={styles.viewerList}>
              {viewers.length === 0 ? (
                <Text style={styles.viewerEmpty}>No views yet — share your story with friends!</Text>
              ) : (
                viewers.map((v) => (
                  <View key={v.child_id} style={styles.viewerRow}>
                    <Avatar
                      uri={v.profile_picture && v.profile_picture.startsWith('http') ? v.profile_picture : null}
                      name={v.full_name ?? 'Friend'}
                      size={30}
                    />
                    <Text style={styles.viewerName} numberOfLines={1}>{v.full_name ?? 'Friend'}</Text>
                    {v.last_viewed_at ? <TimeAgo value={v.last_viewed_at} /> : null}
                  </View>
                ))
              )}
            </ScrollView>
          </View>
        ) : null}

        <View style={styles.controls}>
          <Button label="Back" variant="secondary" disabled={index === 0} onPress={previous} />
          <Button label={paused ? 'Resume' : 'Pause'} variant="secondary" onPress={() => setPaused((value) => !value)} />
          <Button label={index === stories.length - 1 ? 'Restart' : 'Next'} onPress={() => (index === stories.length - 1 ? setIndex(0) : next())} />
        </View>
        {storyDeleteError ? <Text style={styles.deleteError}>{storyDeleteError}</Text> : null}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  viewer: { backgroundColor: colors.ink },
  top: { position: 'absolute', zIndex: 3, top: spacing.md, left: spacing.md, right: spacing.md },
  progressRow: { flexDirection: 'row', gap: 4 },
  progressTrack: { flex: 1, height: 3, backgroundColor: 'rgba(255,255,255,0.35)', overflow: 'hidden', borderRadius: 2 },
  progress: { height: '100%', backgroundColor: colors.surface, borderRadius: 2 },
  complete: { width: '100%' },
  identity: { flexDirection: 'row', alignItems: 'center', gap: 9, marginTop: spacing.sm },
  identityMeta: { flex: 1, justifyContent: 'center' },
  nameRow: { flexDirection: 'row', alignItems: 'baseline' },
  name: { color: colors.surface, fontWeight: '800', fontSize: 14 },
  timestamp: { color: 'rgba(255,255,255,0.65)', fontSize: 12, fontWeight: '600' },
  expiry: { color: 'rgba(255,255,255,0.65)', fontSize: 11, fontWeight: '600', marginTop: 1 },
  viewersBtn: { flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: 'rgba(255,255,255,0.18)', paddingHorizontal: 10, paddingVertical: 6, borderRadius: 14 },
  viewersText: { color: '#FFFFFF', fontSize: 12, fontWeight: '800' },
  create: { borderWidth: 1, borderColor: 'rgba(255,255,255,0.7)', borderRadius: 999, paddingHorizontal: 12, paddingVertical: 6 },
  createText: { color: colors.surface, fontWeight: '800', fontSize: 13 },
  close: { padding: 6, borderRadius: 999, backgroundColor: 'rgba(255,255,255,0.18)' },
  deleting: { opacity: 0.5 },
  deleteError: { color: '#FCA5A5', fontWeight: '700', fontSize: 13, textAlign: 'center', paddingHorizontal: spacing.md },
  media: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  image: { width: '100%', height: '100%' },
  missing: { color: colors.surface, fontWeight: '700' },
  imgFallback: { alignItems: 'center', justifyContent: 'center', gap: 10 },
  imgFallbackText: { color: 'rgba(255,255,255,0.8)', fontWeight: '700' },
  imgRetry: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: 'rgba(255,255,255,0.2)', paddingHorizontal: 16, paddingVertical: 8, borderRadius: 18 },
  imgRetryText: { color: '#FFFFFF', fontWeight: '700' },
  leftTap: { position: 'absolute', left: 0, top: 0, bottom: 0, width: '28%' },
  centerTap: { position: 'absolute', left: '28%', right: '28%', top: 0, bottom: 0 },
  rightTap: { position: 'absolute', right: 0, top: 0, bottom: 0, width: '28%' },
  pause: { position: 'absolute', alignItems: 'center' },
  pauseText: { color: colors.surface, fontSize: 42, fontWeight: '800' },
  pauseLabel: { color: colors.surface, fontWeight: '800' },
  captionOverlay: {
    position: 'absolute',
    bottom: 96,
    left: spacing.md,
    right: spacing.md,
    backgroundColor: 'rgba(0,0,0,0.45)',
    borderRadius: 12,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  caption: { color: colors.surface, fontSize: 15, fontWeight: '700', lineHeight: 21 },
  viewerSheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    maxHeight: '45%',
    backgroundColor: 'rgba(15,23,42,0.97)',
    borderTopLeftRadius: 16,
    borderTopRightRadius: 16,
    padding: spacing.md,
    paddingTop: spacing.sm,
    zIndex: 5,
  },
  dragHandle: { width: 40, height: 4, borderRadius: 2, backgroundColor: 'rgba(255,255,255,0.35)', alignSelf: 'center', marginBottom: spacing.sm },
  viewerSheetHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: spacing.sm },
  viewerSheetTitle: { color: '#FFFFFF', fontWeight: '800', fontSize: 15 },
  viewerList: { maxHeight: 220 },
  viewerEmpty: { color: 'rgba(255,255,255,0.65)', textAlign: 'center', paddingVertical: 16, fontWeight: '600' },
  viewerRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8 },
  viewerName: { color: '#FFFFFF', fontWeight: '700', flex: 1 },
  controls: { flexDirection: 'row', gap: 8, padding: spacing.md },
});
