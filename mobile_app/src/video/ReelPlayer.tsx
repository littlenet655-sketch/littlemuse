import { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Animated,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { Image } from 'expo-image';
import { Feather } from '@expo/vector-icons';
import type { FeedItem } from '../api/kidsFeed';
import { NativeVideoView } from '../ui/nativeViews';
import { colors, radius, spacing } from '../ui/tokens';
import type { ImpressionEventPayload, PlaybackPolicy } from './types';
import { useReelPlayback } from './useReelPlayback';

/** Max gap between two taps to count as a double-tap (Instagram parity). */
const DOUBLE_TAP_WINDOW_MS = 280;

interface ReelPlayerProps {
  item: FeedItem;
  active: boolean;
  nearby: boolean;
  paused: boolean;
  onTogglePlay: () => void;
  /** Instagram parity: double-tap on the video likes the reel. */
  onDoubleTap?: () => void;
  token?: string;
  policy?: PlaybackPolicy;
  onMetricsFlush?: (payload: ImpressionEventPayload) => void;
  onMuteStateChange?: (muted: boolean) => void;
  toggleMuteRef?: React.MutableRefObject<(() => void) | null>;
}

export function ReelPlayer({
  item,
  active,
  nearby,
  paused,
  onTogglePlay,
  onDoubleTap,
  token,
  policy = 'NORMAL',
  onMetricsFlush,
  onMuteStateChange,
  toggleMuteRef,
}: ReelPlayerProps) {
  const [showPlayStateFeedback, setShowPlayStateFeedback] = useState(false);
  const feedbackTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Double-tap disambiguation: a single tap waits out the double-tap window
  // so a double-tap never also toggles play/pause underneath it.
  const lastTapRef = useRef(0);
  const singleTapTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Big-heart burst shown on double-tap (Instagram parity).
  const [showHeart, setShowHeart] = useState(false);
  const heartScale = useRef(new Animated.Value(0)).current;
  const heartOpacity = useRef(new Animated.Value(0)).current;

  const {
    player,
    playbackState,
    firstFrameRendered,
    isDebouncedBuffering,
    showPreparing,
    errorMessage,
    retry,
    handleFirstFrameRender,
    progressAnim,
    muted,
    toggleMute,
  } = useReelPlayback({
    item,
    active,
    nearby,
    paused,
    token,
    policy,
    onMetricsFlush,
  });

  useEffect(() => {
    if (toggleMuteRef) {
      toggleMuteRef.current = toggleMute;
    }
  }, [toggleMuteRef, toggleMute]);

  useEffect(() => {
    onMuteStateChange?.(muted);
  }, [onMuteStateChange, muted]);

  const posterUri = item.poster_url ?? null;
  const showPoster = !firstFrameRendered && Boolean(posterUri);

  // Progress bar fill width as a percentage string — interpolated from the
  // Animated.Value so the native timeUpdate ticks never re-render the cell.
  const progressWidth = progressAnim.interpolate({
    inputRange: [0, 1],
    outputRange: ['0%', '100%'],
  });

  // Warm the poster into the image cache as soon as the cell mounts so the
  // first paint shows artwork instead of black, even on slow networks.
  useEffect(() => {
    if (posterUri) {
      void Image.prefetch(posterUri).catch(() => {});
    }
  }, [posterUri]);

  const handlePress = () => {
    // While the error overlay is up, taps belong to the retry control —
    // never toggle play/pause underneath it.
    if (errorMessage) return;
    if (onDoubleTap) {
      const now = Date.now();
      if (now - lastTapRef.current < DOUBLE_TAP_WINDOW_MS) {
        // Double-tap: cancel the pending single-tap, burst the heart, like.
        if (singleTapTimerRef.current) {
          clearTimeout(singleTapTimerRef.current);
          singleTapTimerRef.current = null;
        }
        lastTapRef.current = 0;
        triggerHeartBurst();
        onDoubleTap();
        return;
      }
      lastTapRef.current = now;
      singleTapTimerRef.current = setTimeout(() => {
        singleTapTimerRef.current = null;
        runSingleTap();
      }, DOUBLE_TAP_WINDOW_MS);
      return;
    }
    runSingleTap();
  };

  const runSingleTap = () => {
    onTogglePlay();
    setShowPlayStateFeedback(true);
    if (feedbackTimerRef.current) clearTimeout(feedbackTimerRef.current);
    feedbackTimerRef.current = setTimeout(() => {
      setShowPlayStateFeedback(false);
      feedbackTimerRef.current = null;
    }, 600);
  };

  const triggerHeartBurst = () => {
    setShowHeart(true);
    // Stop any in-flight burst first: rapid successive double-taps would
    // otherwise leave competing drivers writing the same animated values.
    heartScale.stopAnimation();
    heartOpacity.stopAnimation();
    heartScale.setValue(0);
    heartOpacity.setValue(1);
    Animated.parallel([
      Animated.sequence([
        Animated.timing(heartScale, { toValue: 1.3, duration: 170, useNativeDriver: true }),
        Animated.timing(heartScale, { toValue: 1, duration: 130, useNativeDriver: true }),
      ]),
      Animated.timing(heartOpacity, { toValue: 0, duration: 650, delay: 300, useNativeDriver: true }),
    ]).start(({ finished }) => {
      if (finished) setShowHeart(false);
    });
  };

  useEffect(() => () => {
    if (feedbackTimerRef.current) clearTimeout(feedbackTimerRef.current);
    if (singleTapTimerRef.current) clearTimeout(singleTapTimerRef.current);
  }, []);

  return (
    <Pressable style={styles.container} onPress={handlePress} accessibilityLabel="Toggle video playback">
      {/* Underlying Native Video Player */}
      <NativeVideoView
        player={player}
        style={StyleSheet.absoluteFill}
        contentFit="cover"
        nativeControls={false}
        onFirstFrameRender={handleFirstFrameRender}
      />

      {/* Poster overlay: rendered until first video frame is decoded */}
      {showPoster && posterUri ? (
        <Image
          source={{ uri: posterUri }}
          style={StyleSheet.absoluteFill}
          contentFit="cover"
          cachePolicy="memory-disk"
          accessibilityLabel="Reel poster"
        />
      ) : null}

      {/* Buffering / preparing indicator: the debounced stall pill, plus the
          preparing spinner for an active cell whose player emits no status
          events at all (otherwise a pure black screen). */}
      {(isDebouncedBuffering || showPreparing) && !errorMessage ? (
        <View style={styles.bufferingOverlay} pointerEvents="none">
          <View style={styles.bufferingPill}>
            <ActivityIndicator size="small" color="#FFFFFF" />
            <Text style={styles.bufferingText}>Loading…</Text>
          </View>
        </View>
      ) : null}

      {/* Tap Feedback Icon (Play / Pause) */}
      {showPlayStateFeedback ? (
        <View style={styles.feedbackOverlay} pointerEvents="none">
          <View style={styles.feedbackCircle}>
            <Feather
              name={paused ? 'play' : 'pause'}
              size={32}
              color="#FFFFFF"
            />
          </View>
        </View>
      ) : null}

      {/* Double-tap heart burst (Instagram parity) */}
      {showHeart ? (
        <View style={styles.heartOverlay} pointerEvents="none">
          <Animated.View
            style={[
              styles.heartBurst,
              { transform: [{ scale: heartScale }], opacity: heartOpacity },
            ]}
          >
            <Feather name="heart" size={84} color="#FFFFFF" />
          </Animated.View>
        </View>
      ) : null}

      {/* Mute / unmute toggle (Instagram parity) */}
      <Pressable
        style={styles.muteButton}
        onPress={toggleMute}
        accessibilityRole="button"
        accessibilityLabel={muted ? 'Unmute reel' : 'Mute reel'}
        hitSlop={10}
      >
        <Feather name={muted ? 'volume-x' : 'volume-2'} size={18} color="#FFFFFF" />
      </Pressable>

      {/* Instagram-style playback progress bar */}
      <View style={styles.progressTrack} pointerEvents="none">
        <Animated.View style={[styles.progressFill, { width: progressWidth }]} />
      </View>

      {/* Error & Controlled Retry Overlay */}
      {errorMessage ? (
        <View style={styles.errorOverlay}>
          <View style={styles.errorCard}>
            <Feather name="alert-circle" size={28} color="#EF4444" />
            <Text style={styles.errorTitle}>Could not play reel</Text>
            <Text style={styles.errorDescription}>{errorMessage}</Text>
            <Pressable style={styles.retryButton} onPress={retry}>
              <Feather name="refresh-cw" size={16} color="#FFFFFF" />
              <Text style={styles.retryText}>Retry</Text>
            </Pressable>
          </View>
        </View>
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#000000',
    overflow: 'hidden',
  },
  bufferingOverlay: {
    ...StyleSheet.absoluteFill,
    justifyContent: 'center',
    alignItems: 'center',
  },
  bufferingPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: 'rgba(0, 0, 0, 0.65)',
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 24,
  },
  bufferingText: {
    color: '#FFFFFF',
    fontSize: 13,
    fontWeight: '600',
  },
  feedbackOverlay: {
    ...StyleSheet.absoluteFill,
    justifyContent: 'center',
    alignItems: 'center',
  },
  feedbackCircle: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: 'rgba(0, 0, 0, 0.55)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  errorOverlay: {
    ...StyleSheet.absoluteFill,
    backgroundColor: 'rgba(0, 0, 0, 0.75)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: spacing.lg,
  },
  errorCard: {
    backgroundColor: colors.surface,
    padding: spacing.lg,
    borderRadius: radius.md,
    alignItems: 'center',
    maxWidth: 320,
    gap: 8,
  },
  errorTitle: {
    fontSize: 16,
    fontWeight: '800',
    color: colors.ink,
  },
  errorDescription: {
    fontSize: 13,
    color: colors.muted,
    textAlign: 'center',
    lineHeight: 18,
  },
  retryButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: colors.brand,
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 20,
    marginTop: 4,
  },
  retryText: {
    color: '#FFFFFF',
    fontWeight: '700',
    fontSize: 14,
  },
  heartOverlay: {
    ...StyleSheet.absoluteFill,
    justifyContent: 'center',
    alignItems: 'center',
  },
  heartBurst: {
    justifyContent: 'center',
    alignItems: 'center',
    textShadowColor: 'rgba(0,0,0,0.45)',
    textShadowOffset: { width: 0, height: 2 },
    textShadowRadius: 8,
  },
  muteButton: {
    position: 'absolute',
    top: 64,
    right: 12,
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: 'rgba(0, 0, 0, 0.50)',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.12)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  progressTrack: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    height: 3,
    backgroundColor: 'rgba(255,255,255,0.22)',
  },
  progressFill: {
    height: 3,
    backgroundColor: '#FFFFFF',
  },
});
