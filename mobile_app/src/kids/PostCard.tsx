import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Alert, Animated, Easing, Image, Modal, Pressable, StyleSheet, Text, View } from 'react-native';
import { Feather, FontAwesome } from '@expo/vector-icons';
import type { InfiniteData } from '@tanstack/react-query';
import type { FeedItem, FeedPage } from '../api/kidsFeed';
import { useAuth } from '../auth/AuthProvider';
import { queryClient } from '../query/client';
import { invalidateSocialCaches, kidsKeys } from '../query/keys';
import { deletePost, toggleLike, toggleSave } from '../api/kidsSocial';
import { isPubliclyVisible, runSocialPostAction, socialPostTarget } from './social';
import { VideoMedia } from './VideoMedia';
import { Avatar, CategoryBadge, TimeAgo } from '../ui/social';
import { colors, radius, spacing, type } from '../ui/tokens';
import { clampAspectRatio, parseAspectRatio } from '../video/types';

const FALLBACK_MEDIA_HEIGHT = 300;

/**
 * Aspect ratio for a remote image: prefer the server's aspect_ratio tag when
 * present, otherwise measure the real asset with Image.getSize (no invented
 * dimensions). Returns null while unresolved so callers can show a placeholder.
 */
function useRemoteAspect(uri: string | null | undefined, hint?: string | null): number | null {
  const hintRatio = parseAspectRatio(hint);
  const [measured, setMeasured] = useState<number | null>(null);
  useEffect(() => {
    setMeasured(null);
    if (!uri) return;
    let cancelled = false;
    Image.getSize(
      uri,
      (w, h) => {
        if (!cancelled && w > 0 && h > 0) setMeasured(clampAspectRatio(w / h));
      },
      () => {
        // Measurement failure is non-fatal: the caller falls back gracefully.
      },
    );
    return () => {
      cancelled = true;
    };
  }, [uri]);
  return measured ?? hintRatio;
}

/** Image with placeholder, measured aspect ratio, and a retryable error state. */
function FeedImage({ uri, aspectHint, label }: { uri: string; aspectHint?: string | null; label: string }) {
  const [failed, setFailed] = useState(false);
  const [ready, setReady] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [measured, setMeasured] = useState<number | null>(null);
  const aspect = measured ?? parseAspectRatio(aspectHint);

  useEffect(() => {
    setFailed(false);
    setReady(false);
    setMeasured(null);
  }, [uri]);

  // Warm the disk/memory cache so taps into detail views paint instantly.
  useEffect(() => {
    void Image.prefetch(uri).catch(() => {});
  }, [uri]);

  return (
    <View style={[styles.mediaBox, aspect ? { aspectRatio: aspect } : { height: FALLBACK_MEDIA_HEIGHT }]}>
      {!failed ? (
        <Image
          key={`${uri}#${attempt}`}
          source={{ uri }}
          style={StyleSheet.absoluteFill}
          resizeMode="cover"
          accessibilityLabel={label}
          onLoad={(e) => {
            setReady(true);
            setFailed(false);
            const src = e.nativeEvent.source;
            if (src?.width > 0 && src?.height > 0) {
              setMeasured(clampAspectRatio(src.width / src.height));
            }
          }}
          onError={() => setFailed(true)}
        />
      ) : null}
      {!ready && !failed ? (
        <View style={styles.mediaPlaceholder} pointerEvents="none">
          <ActivityIndicator size="small" color={colors.muted} />
        </View>
      ) : null}
      {failed ? (
        <View style={styles.mediaFallback}>
          <Feather name="image" size={28} color={colors.muted} />
          <Text style={styles.mediaFallbackText}>Couldn't load this image.</Text>
          <Pressable
            style={styles.mediaRetry}
            accessibilityRole="button"
            accessibilityLabel="Retry loading image"
            onPress={() => {
              setAttempt((a) => a + 1);
              setFailed(false);
            }}
          >
            <Feather name="refresh-cw" size={14} color="#FFFFFF" />
            <Text style={styles.mediaRetryText}>Retry</Text>
          </Pressable>
        </View>
      ) : null}
    </View>
  );
}

export function PostCard({
  item,
  onOpen,
  onProfile,
  onNotInterested,
  onDeleted,
  inlineVideoPlayback = false,
  videoActive = false,
}: {
  item: FeedItem;
  onOpen?: () => void;
  onProfile?: () => void;
  onNotInterested?: () => void;
  /** Fired after the server confirms the delete so parents can drop the card locally. */
  onDeleted?: (postId: number) => void;
  inlineVideoPlayback?: boolean;
  videoActive?: boolean;
}) {
  const { session } = useAuth();
  const isVideo = item.media_type?.toUpperCase() === 'VIDEO';
  // Hook runs unconditionally; the visibility gate below only affects rendering.
  const posterAspect = useRemoteAspect(isVideo ? item.poster_url : undefined, item.aspect_ratio);
  const [menuOpen, setMenuOpen] = useState(false);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState('');
  // Per-post in-flight guard: rapid double-taps on like/save used to fire
  // duplicate toggle requests (double optimistic flips, out-of-order server
  // replies). Keys are action-scoped so a like in flight never blocks a save.
  const toggleBusyRef = useRef<Set<string>>(new Set());
  // Instagram-style double-tap to like. Two taps within DOUBLE_TAP_MS on the
  // media like the post and play a big-heart burst; a lone tap still opens
  // the post detail after a short delay so the second tap can cancel it.
  const DOUBLE_TAP_MS = 300;
  const lastTapRef = useRef(0);
  const openTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const burstAnim = useRef(new Animated.Value(0)).current;
  const burstAnimRef = useRef<Animated.CompositeAnimation | null>(null);
  const [burstVisible, setBurstVisible] = useState(false);
  useEffect(
    () => () => {
      if (openTimerRef.current) clearTimeout(openTimerRef.current);
      burstAnimRef.current?.stop();
    },
    [],
  );
  if (!isPubliclyVisible(item)) return null;
  const socialTarget = socialPostTarget(item);
  const previewUrl = isVideo ? item.poster_url : item.media_url;
  // Delete is offered only for the viewer's own social posts (the server
  // re-checks ownership; curated/learn items have no target and no owner).
  const isOwn = socialTarget != null && session?.user?.user_id != null && item.child_id === session.user.user_id;

  function confirmDelete() {
    setMenuOpen(false);
    Alert.alert(
      'Delete this post?',
      'It will be removed for everyone and cannot be undone.',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Delete', style: 'destructive', onPress: () => void doDelete() },
      ],
    );
  }

  async function doDelete() {
    if (!session || !socialTarget || deleteBusy) return;
    setDeleteBusy(true);
    setDeleteError('');
    try {
      await deletePost(session.token, socialTarget.postId);
      await invalidateSocialCaches([socialTarget.postId]);
      onDeleted?.(socialTarget.postId);
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : 'Could not delete this post. Try again.');
    } finally {
      setDeleteBusy(false);
    }
  }

  function fireHeartBurst() {
    setBurstVisible(true);
    burstAnim.setValue(0);
    burstAnimRef.current?.stop();
    burstAnimRef.current = Animated.timing(burstAnim, {
      toValue: 1,
      duration: 800,
      easing: Easing.out(Easing.quad),
      useNativeDriver: true,
    });
    burstAnimRef.current.start(({ finished }) => {
      if (finished) setBurstVisible(false);
    });
  }

  function handleMediaPress(openOnSingleTap: boolean) {
    const now = Date.now();
    const delta = now - lastTapRef.current;
    // Double-tap-to-like only applies to likeable (social) posts: on other
    // media a second quick tap must not cancel the pending open.
    if (socialTarget && delta > 0 && delta < DOUBLE_TAP_MS) {
      // Double tap: cancel the pending single-tap open, burst, and like.
      lastTapRef.current = 0;
      if (openTimerRef.current) {
        clearTimeout(openTimerRef.current);
        openTimerRef.current = null;
      }
      if (socialTarget) {
        fireHeartBurst();
        if (!item.viewer_liked) void onLike();
      }
      return;
    }
    lastTapRef.current = now;
    if (!openOnSingleTap || !onOpen) return;
    if (openTimerRef.current) clearTimeout(openTimerRef.current);
    openTimerRef.current = setTimeout(() => {
      openTimerRef.current = null;
      onOpen();
    }, DOUBLE_TAP_MS);
  }

  const burstAnimatedStyle = {
    opacity: burstAnim.interpolate({ inputRange: [0, 0.25, 1], outputRange: [0, 1, 0] }),
    transform: [
      { scale: burstAnim.interpolate({ inputRange: [0, 0.3, 1], outputRange: [0.2, 1.15, 1] }) },
    ],
  };

  function renderHeartBurst() {
    if (!burstVisible) return null;
    return (
      <Animated.View pointerEvents="none" style={[styles.burst, burstAnimatedStyle]}>
        <FontAwesome name="heart" size={88} color="#FFFFFF" style={styles.burstHeart} />
      </Animated.View>
    );
  }

  async function onLike() {
    if (!session || !socialTarget) return;
    const postId = socialTarget.postId;
    const busyKey = `${postId}:like`;
    if (toggleBusyRef.current.has(busyKey)) return;
    toggleBusyRef.current.add(busyKey);
    try {
      const update = (old: InfiniteData<FeedPage> | undefined, liked: boolean, likes: number) => old ? ({
        ...old,
        pages: old.pages.map((page) => ({ ...page, items: page.items.map((post) => post.source_type === 'SOCIAL' && post.post_id === postId ? { ...post, viewer_liked: liked, likes } : post) })),
      }) : old;
      const optimisticLiked = !item.viewer_liked;
      const optimisticLikes = (item.likes ?? 0) + (item.viewer_liked ? -1 : 1);
      queryClient.setQueriesData<InfiniteData<FeedPage>>({ queryKey: kidsKeys.feed }, (old) => update(old, optimisticLiked, optimisticLikes));
      queryClient.setQueriesData<InfiniteData<FeedPage>>({ queryKey: kidsKeys.reels }, (old) => update(old, optimisticLiked, optimisticLikes));
      try {
        const result = await runSocialPostAction(item, (id) => toggleLike(session.token, id));
        if (!result) return;
        queryClient.setQueriesData<InfiniteData<FeedPage>>({ queryKey: kidsKeys.feed }, (old) => update(old, result.liked, result.likes));
        queryClient.setQueriesData<InfiniteData<FeedPage>>({ queryKey: kidsKeys.reels }, (old) => update(old, result.liked, result.likes));
        await invalidateSocialCaches([postId]);
      } catch {
        await queryClient.invalidateQueries({ queryKey: kidsKeys.feed });
      }
    } finally {
      toggleBusyRef.current.delete(busyKey);
    }
  }

  async function onSave() {
    if (!session || !socialTarget) return;
    const postId = socialTarget.postId;
    const busyKey = `${postId}:save`;
    if (toggleBusyRef.current.has(busyKey)) return;
    toggleBusyRef.current.add(busyKey);
    try {
      const result = await runSocialPostAction(item, (id) => toggleSave(session.token, id));
      if (!result) return;
      const update = (old: InfiniteData<FeedPage> | undefined) => old ? ({
        ...old,
        pages: old.pages.map((page) => ({ ...page, items: page.items.map((post) => post.source_type === 'SOCIAL' && post.post_id === postId ? { ...post, viewer_saved: result.saved } : post) })),
      }) : old;
      queryClient.setQueriesData<InfiniteData<FeedPage>>({ queryKey: kidsKeys.feed }, update);
      queryClient.setQueriesData<InfiniteData<FeedPage>>({ queryKey: kidsKeys.reels }, update);
      await invalidateSocialCaches([postId]);
    } catch {
      await queryClient.invalidateQueries({ queryKey: kidsKeys.saved });
    } finally {
      toggleBusyRef.current.delete(busyKey);
    }
  }

  return (
    <View style={styles.card}>
      <View style={styles.row}>
        <Pressable onPress={onProfile} disabled={!onProfile} style={styles.profileRow}>
          <Avatar uri={item.avatar_url} name={item.full_name} size={40} />
          <View style={styles.meta}>
            <Text style={styles.name}>{item.full_name ?? 'Friend'}</Text>
            <TimeAgo value={item.created_at} />
          </View>
          <CategoryBadge label={item.content_category} />
        </Pressable>
        {onNotInterested ? (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Not interested"
            onPress={onNotInterested}
            hitSlop={8}
            style={styles.dismiss}
          >
            <Feather name="eye-off" size={18} color={colors.muted} />
          </Pressable>
        ) : null}
        {isOwn ? (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Post options"
            onPress={() => {
              setDeleteError('');
              setMenuOpen(true);
            }}
            hitSlop={8}
            style={styles.dismiss}
          >
            <Feather name="more-horizontal" size={18} color={colors.muted} />
          </Pressable>
        ) : null}
      </View>
      {deleteError ? <Text style={styles.deleteError}>{deleteError}</Text> : null}
      {item.title ? <Text style={styles.title}>{item.title}</Text> : null}
      {item.caption ? (
        <Text style={styles.caption}>
          <Text style={styles.captionUser}>{item.full_name ?? 'Friend'}</Text>
          {'  '}
          {item.caption}
        </Text>
      ) : null}
      {isVideo ? (
        inlineVideoPlayback && videoActive && item.media_url ? (
          <Pressable onPress={() => handleMediaPress(false)} style={styles.inlineVideo} accessibilityRole="button" accessibilityLabel="Video playing">
            <VideoMedia
              source={item.media_url}
              posterUrl={item.poster_url}
              active={videoActive}
              height={FALLBACK_MEDIA_HEIGHT}
              aspectRatio={posterAspect ?? undefined}
              nativeControls={false}
              loop
            />
            {renderHeartBurst()}
          </Pressable>
        ) : previewUrl ? (
          <Pressable onPress={() => handleMediaPress(true)} disabled={!onOpen && !socialTarget} style={styles.videoPoster}>
            <FeedImage uri={previewUrl} aspectHint={item.aspect_ratio} label="Video preview" />
            <View style={styles.playBadge} pointerEvents="none">
              <Feather name="play" size={24} color="#FFFFFF" />
            </View>
            {renderHeartBurst()}
          </Pressable>
        ) : (
          <Pressable onPress={onOpen} disabled={!onOpen && !socialTarget} style={[styles.mediaBox, { height: FALLBACK_MEDIA_HEIGHT }]}>
            <Text style={styles.videoLabel}>Video</Text>
          </Pressable>
        )
      ) : previewUrl ? (
        <Pressable onPress={() => handleMediaPress(true)} disabled={!onOpen && !socialTarget} style={styles.mediaTouch}>
          <FeedImage uri={previewUrl} aspectHint={item.aspect_ratio} label="Post image" />
          {renderHeartBurst()}
        </Pressable>
      ) : null}
      {socialTarget ? (
        <View>
          <View style={styles.actions}>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={item.viewer_liked ? 'Unlike post' : 'Like post'}
              onPress={() => void onLike()}
              style={styles.action}
              hitSlop={6}
            >
              {item.viewer_liked ? (
                <FontAwesome name="heart" size={24} color={colors.danger} />
              ) : (
                <Feather name="heart" size={24} color={colors.ink} />
              )}
            </Pressable>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Comments"
              onPress={onOpen}
              style={styles.action}
              hitSlop={6}
            >
              <Feather name="message-circle" size={24} color={colors.ink} />
            </Pressable>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Share post"
              onPress={onOpen}
              style={styles.action}
              hitSlop={6}
            >
              <Feather name="send" size={24} color={colors.ink} />
            </Pressable>
            <View style={styles.flex} />
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={item.viewer_saved ? 'Unsave post' : 'Save post'}
              onPress={() => void onSave()}
              style={styles.action}
              hitSlop={6}
            >
              {item.viewer_saved ? (
                <FontAwesome name="bookmark" size={24} color={colors.brand} />
              ) : (
                <Feather name="bookmark" size={24} color={colors.ink} />
              )}
            </Pressable>
          </View>
          <Text style={styles.likeCount}>{item.likes ?? 0} likes</Text>
          {typeof item.comments_count === 'number' && item.comments_count > 0 ? (
            <Pressable onPress={onOpen} accessibilityRole="button" accessibilityLabel={`View ${item.comments_count} comments`}>
              <Text style={styles.commentCount}>View all {item.comments_count} comments</Text>
            </Pressable>
          ) : null}
        </View>
      ) : null}
      <Modal visible={menuOpen} transparent animationType="slide" onRequestClose={() => setMenuOpen(false)}>
        <Pressable style={styles.sheetBackdrop} onPress={() => setMenuOpen(false)}>
          <View style={styles.sheet} onStartShouldSetResponder={() => true}>
            <Text style={styles.sheetTitle}>Post options</Text>
            <Pressable
              style={styles.sheetDanger}
              accessibilityRole="button"
              accessibilityLabel="Delete post"
              disabled={deleteBusy}
              onPress={confirmDelete}
            >
              <Feather name="trash-2" size={18} color={colors.danger} />
              <Text style={styles.sheetDangerText}>{deleteBusy ? 'Deleting…' : 'Delete post'}</Text>
            </Pressable>
            <Pressable
              style={styles.sheetCancel}
              accessibilityRole="button"
              accessibilityLabel="Close options"
              onPress={() => setMenuOpen(false)}
            >
              <Text style={styles.sheetCancelText}>Cancel</Text>
            </Pressable>
          </View>
        </Pressable>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: colors.line, paddingBottom: spacing.md, marginBottom: spacing.sm },
  row: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  profileRow: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 10 },
  meta: { flex: 1 },
  name: { fontWeight: '800', color: colors.ink, fontSize: type.body },
  title: { marginTop: 8, color: colors.ink, fontSize: type.body, fontWeight: '800' },
  caption: { marginTop: 8, color: colors.ink, fontSize: type.body, lineHeight: 20 },
  captionUser: { fontWeight: '800' },
  burst: { ...StyleSheet.absoluteFill, alignItems: 'center', justifyContent: 'center' },
  burstHeart: { textShadowColor: 'rgba(0,0,0,0.45)', textShadowOffset: { width: 0, height: 2 }, textShadowRadius: 10 },
  mediaTouch: { position: 'relative' },
  mediaBox: { marginTop: 10, width: '100%', backgroundColor: colors.line, overflow: 'hidden' },
  mediaPlaceholder: { ...StyleSheet.absoluteFill, alignItems: 'center', justifyContent: 'center' },
  mediaFallback: { ...StyleSheet.absoluteFill, alignItems: 'center', justifyContent: 'center', gap: 8, padding: spacing.md },
  mediaFallbackText: { color: colors.muted, fontWeight: '700', fontSize: 13 },
  mediaRetry: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: colors.brand, paddingHorizontal: 16, paddingVertical: 8, borderRadius: 18 },
  mediaRetryText: { color: '#FFFFFF', fontWeight: '700', fontSize: 13 },
  videoLabel: { margin: 'auto', color: colors.muted, fontWeight: '700' },
  inlineVideo: { marginTop: 10, width: '100%', backgroundColor: colors.ink, overflow: 'hidden' },
  videoPoster: { position: 'relative' },
  playBadge: { position: 'absolute', left: '50%', top: '50%', marginLeft: -24, marginTop: -24, width: 48, height: 48, borderRadius: 24, backgroundColor: 'rgba(0,0,0,0.55)', alignItems: 'center', justifyContent: 'center' },
  actions: { flexDirection: 'row', alignItems: 'center', gap: 16, marginTop: 8, paddingHorizontal: spacing.md },
  action: { paddingVertical: 5 },
  actionText: { color: colors.brandDark, fontWeight: '700' },
  likeCount: { color: colors.ink, fontSize: type.body, fontWeight: '700', paddingHorizontal: spacing.md, marginTop: 8 },
  commentCount: { color: colors.muted, fontSize: type.body, fontWeight: '700', paddingHorizontal: spacing.md, marginTop: 4, paddingVertical: 4 },
  flex: { flex: 1 },
  dismiss: { padding: 6 },
  deleteError: { color: colors.danger, fontWeight: '700', fontSize: 13, paddingHorizontal: spacing.md, marginTop: 6 },
  sheetBackdrop: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(0,0,0,0.45)' },
  sheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: 18,
    borderTopRightRadius: 18,
    padding: spacing.md,
    gap: 10,
  },
  sheetTitle: { color: colors.ink, fontSize: 16, fontWeight: '800', marginBottom: 4 },
  sheetDanger: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingVertical: 12,
    paddingHorizontal: 8,
    borderRadius: 10,
  },
  sheetDangerText: { color: colors.danger, fontWeight: '800', fontSize: 15 },
  sheetCancel: { alignItems: 'center', paddingVertical: 12, borderRadius: 10, backgroundColor: '#F3F4F6' },
  sheetCancelText: { color: colors.ink, fontWeight: '700', fontSize: 15 },
  icon: { color: colors.ink, fontSize: 24, lineHeight: 24 },
  liked: { color: colors.danger },
});
