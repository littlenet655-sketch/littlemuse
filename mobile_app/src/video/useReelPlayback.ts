import { useCallback, useEffect, useRef, useState } from 'react';
import { Animated } from 'react-native';
import { useVideoPlayer } from 'expo-video';
import type { FeedItem } from '../api/kidsFeed';
import { refreshCuratedReelPlayback, refreshReelPlayback } from '../api/kidsFeed';
import { getBufferOptions } from './playbackPolicy';
import { ReelMetricsTracker } from './reelPlaybackMetrics';
import type {
  ImpressionEventPayload,
  PlaybackPolicy,
  PlaybackState,
  ReelPlaybackResponse,
} from './types';

const BUFFERING_DEBOUNCE_MS = 300;
const FIRST_FRAME_TIMEOUT_MS = 8000;
const PREEMPTIVE_REFRESH_WINDOW_SEC = 45;
/** Consecutive auto-refresh attempts after playback errors before surfacing the retry UI. */
const MAX_ERROR_REFRESH_ATTEMPTS = 3;

/** Narrow the Agent C playback fetcher result to the full server payload (local typing, no contract change). */
async function fetchPlayback(
  item: FeedItem,
  token: string,
): Promise<ReelPlaybackResponse | null> {
  const postId = item.post_id || item.source_id;
  if (typeof postId !== 'number') return null;
  const res = item.source_type === 'CURATED'
    ? await refreshCuratedReelPlayback(token, postId)
    : await refreshReelPlayback(token, postId);
  return res as unknown as ReelPlaybackResponse;
}

export function useReelPlayback({
  item,
  active,
  nearby,
  paused,
  token,
  policy = 'NORMAL',
  onMetricsFlush,
}: {
  item: FeedItem;
  active: boolean;
  nearby: boolean;
  paused: boolean;
  token?: string;
  policy?: PlaybackPolicy;
  onMetricsFlush?: (payload: ImpressionEventPayload) => void;
}) {
  const [playbackState, setPlaybackState] = useState<PlaybackState>('IDLE');
  const [currentSource, setCurrentSource] = useState<string | null>(item.media_url ?? null);
  const [currentExpiryAt, setCurrentExpiryAt] = useState<number | null>(item.playback_expires_at ?? null);
  const [firstFrameRendered, setFirstFrameRendered] = useState(false);
  const [isDebouncedBuffering, setIsDebouncedBuffering] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  // Instagram parity: per-reel mute toggle. Reels autoplay with sound; the
  // toggle only affects this cell's player instance.
  const [muted, setMuted] = useState(false);

  // Instagram-style progress: 0..1 Animated.Value driven straight from the
  // native timeUpdate events. setValue() avoids re-rendering the cell on
  // every tick — only the thin progress bar reads it.
  const progressAnim = useRef(new Animated.Value(0)).current;

  const sourceRef = useRef<string | null>(null);
  const metricsRef = useRef<ReelMetricsTracker>(new ReelMetricsTracker(item, 'REELS'));
  const bufferingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const firstFrameTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isMountedRef = useRef(true);
  const playbackStartedRef = useRef(false);
  const sourceFetchInFlightRef = useRef(false);
  const errorRefreshAttemptsRef = useRef(0);
  const onMetricsFlushRef = useRef(onMetricsFlush);

  useEffect(() => {
    onMetricsFlushRef.current = onMetricsFlush;
  }, [onMetricsFlush]);

  const player = useVideoPlayer(null, (instance) => {
    instance.loop = true;
    try {
      instance.bufferOptions = getBufferOptions(policy);
    } catch {
      // BufferOptions gracefully handled if platform restricts
    }
  });

  // Keep source up to date when item updates. Also reset per-item visual state
  // here (not only when the source URL changes) so a recycled cell never shows
  // the previous reel's poster/first-frame state for the new item.
  useEffect(() => {
    setCurrentSource(item.media_url ?? null);
    setCurrentExpiryAt(item.playback_expires_at ?? null);
    setFirstFrameRendered(false);
    setErrorMessage(null);
    progressAnim.setValue(0);
    playbackStartedRef.current = false;
    sourceFetchInFlightRef.current = false;
    errorRefreshAttemptsRef.current = 0;
    metricsRef.current = new ReelMetricsTracker(item, 'REELS');
  }, [item.source_type, item.source_id, item.post_id, item.media_url, item.playback_expires_at]);

  const requestFreshPlayback = useCallback(async (): Promise<string | null> => {
    if (!token || sourceFetchInFlightRef.current) return null;
    sourceFetchInFlightRef.current = true;
    try {
      const res = await fetchPlayback(item, token);
      if (res?.ok && res.playback_url && isMountedRef.current) {
        setCurrentSource(res.playback_url);
        setCurrentExpiryAt(res.playback_expires_at ?? null);
        metricsRef.current.onCredentialRefreshed();
        return res.playback_url;
      }
      return null;
    } catch (error) {
      if (isMountedRef.current && active) {
        const message = error instanceof Error ? error.message : 'Could not prepare this reel.';
        setErrorMessage(message);
        setPlaybackState('ERROR');
        setIsDebouncedBuffering(false);
      }
      return null;
    } finally {
      sourceFetchInFlightRef.current = false;
    }
  }, [active, item, token]);

  // Both social and curated Reels use just-in-time playback credentials so the
  // list request stays fast and only the active window touches R2/Stream.
  useEffect(() => {
    if (nearby && !currentSource) {
      void requestFreshPlayback();
    }
  }, [nearby, currentSource, requestFreshPlayback]);

  // Swap the player's signed credential without restarting the reel: preserve
  // the current playback position across replaceAsync so a mid-watch refresh
  // is invisible. Bounded by the shared in-flight guard.
  const swapSourcePreservingPosition = useCallback(async (nextUrl: string) => {
    const position = Math.max(0, player.currentTime || 0);
    sourceRef.current = nextUrl;
    await player.replaceAsync(nextUrl);
    if (!isMountedRef.current) return;
    try {
      const duration = player.duration || 0;
      if (duration > 0 && position > 0 && position < duration - 0.5) {
        player.currentTime = position;
      }
    } catch {
      // Seek restoration is best-effort; playback continues from the start.
    }
    if (active && !paused) {
      player.play();
    }
  }, [active, paused, player]);

  // Preemptive Credential Expiry Check for both social and curated Reels.
  const checkCredentialExpiry = useCallback(async () => {
    if (!currentExpiryAt || !token || sourceFetchInFlightRef.current) return;
    const nowSec = Math.floor(Date.now() / 1000);
    const remainingSec = currentExpiryAt - nowSec;
    if (remainingSec <= PREEMPTIVE_REFRESH_WINDOW_SEC) {
      sourceFetchInFlightRef.current = true;
      try {
        const res = await fetchPlayback(item, token);
        if (res?.ok && res.playback_url && isMountedRef.current) {
          setCurrentSource(res.playback_url);
          setCurrentExpiryAt(res.playback_expires_at ?? null);
          metricsRef.current.onCredentialRefreshed();
          if (sourceRef.current) {
            await swapSourcePreservingPosition(res.playback_url);
          }
        }
      } catch {
        // Will retry on error listener if needed
      } finally {
        sourceFetchInFlightRef.current = false;
      }
    }
  }, [currentExpiryAt, item, token, swapSourcePreservingPosition]);

  // Check credential expiry on active transition and periodically
  useEffect(() => {
    if (active) {
      void checkCredentialExpiry();
      const interval = setInterval(() => {
        void checkCredentialExpiry();
      }, 20000);
      return () => clearInterval(interval);
    }
  }, [active, checkCredentialExpiry]);

  // Manage player listeners
  useEffect(() => {
    const statusSub = player.addListener('statusChange', ({ status, error }) => {
      if (!isMountedRef.current) return;

      if (status === 'error') {
        setPlaybackState('ERROR');
        const msg = error?.message ?? 'This reel could not play.';
        metricsRef.current.onError(msg);
        setIsDebouncedBuffering(false);

        // Refresh an expired/invalid credential, but bound the automatic
        // attempts: a persistently failing source must surface the manual
        // retry UI instead of looping network requests forever.
        if (errorRefreshAttemptsRef.current < MAX_ERROR_REFRESH_ATTEMPTS) {
          errorRefreshAttemptsRef.current += 1;
          void requestFreshPlayback().then((freshUrl) => {
            if (!isMountedRef.current) return;
            if (!freshUrl) {
              setErrorMessage(msg);
            }
          });
        } else {
          setErrorMessage(msg);
        }
        return;
      }

      if (status === 'loading') {
        setPlaybackState(playbackStartedRef.current ? 'BUFFERING' : 'PREPARING');
        if (playbackStartedRef.current) {
          metricsRef.current.onBufferingStarted();
        }
        if (!bufferingTimerRef.current) {
          bufferingTimerRef.current = setTimeout(() => {
            if (isMountedRef.current) {
              setIsDebouncedBuffering(true);
            }
          }, BUFFERING_DEBOUNCE_MS);
        }
        return;
      }

      if (status === 'readyToPlay') {
        if (bufferingTimerRef.current) {
          clearTimeout(bufferingTimerRef.current);
          bufferingTimerRef.current = null;
        }
        setIsDebouncedBuffering(false);
        setPlaybackState('READY');
        // A successful load resets the error-refresh budget.
        errorRefreshAttemptsRef.current = 0;
        // readyToPlay means the decoder can begin; keep the poster visible until
        // the native VideoView confirms an actual first frame was rendered.
        setErrorMessage(null);
        if (active && !paused) player.play();
      }
    });

    const playingSub = player.addListener('playingChange', ({ isPlaying }) => {
      if (!isMountedRef.current) return;
      if (isPlaying) {
        playbackStartedRef.current = true;
        setPlaybackState('PLAYING');
        setIsDebouncedBuffering(false);
        metricsRef.current.onPlayingStarted();
      } else {
        setPlaybackState('PAUSED');
        metricsRef.current.onPlayingPaused();
      }
    });

    const timeSub = player.addListener('timeUpdate', ({ currentTime }) => {
      metricsRef.current.onTimeUpdate(currentTime, player.duration);
      const duration = player.duration || 0;
      progressAnim.setValue(duration > 0 ? Math.min(1, Math.max(0, currentTime / duration)) : 0);
    });

    const endSub = player.addListener('playToEnd', () => {
      metricsRef.current.onPlayToEnd();
    });

    return () => {
      statusSub.remove();
      playingSub.remove();
      timeSub.remove();
      endSub.remove();
      if (bufferingTimerRef.current) {
        clearTimeout(bufferingTimerRef.current);
        bufferingTimerRef.current = null;
      }
      if (firstFrameTimerRef.current) {
        clearTimeout(firstFrameTimerRef.current);
        firstFrameTimerRef.current = null;
      }
    };
  }, [player, active, paused, requestFreshPlayback]);

  // Window loading logic: only load source if active or immediate neighbor (nearby)
  useEffect(() => {
    const nextSource = nearby ? currentSource : null;
    if (sourceRef.current === nextSource) return;
    sourceRef.current = nextSource;

    if (!nextSource) {
      setFirstFrameRendered(false);
      setPlaybackState('IDLE');
      setIsDebouncedBuffering(false);
      setErrorMessage(null);
      void player.replaceAsync(null).catch(() => {});
      return;
    }

    setFirstFrameRendered(false);
    setPlaybackState('PREPARING');
    setErrorMessage(null);
    metricsRef.current.onPlayRequested();

    void player.replaceAsync(nextSource).catch((err: unknown) => {
      if (!isMountedRef.current) return;
      const msg = err instanceof Error ? err.message : 'Failed to prepare video.';
      setErrorMessage(msg);
      setPlaybackState('ERROR');
    });
  }, [nearby, player, currentSource]);

  // Active playing control: strictly the current reel plays
  useEffect(() => {
    if (active && nearby && currentSource && !errorMessage && !paused) {
      player.play();
    } else {
      player.pause();
    }
  }, [active, nearby, currentSource, errorMessage, paused, player]);

  // A decoder can occasionally remain in a non-error preparing state forever.
  // Bound that state so the UI becomes actionable instead of showing a black
  // screen indefinitely. Manual Retry will refresh the JIT playback credential.
  useEffect(() => {
    if (firstFrameTimerRef.current) {
      clearTimeout(firstFrameTimerRef.current);
      firstFrameTimerRef.current = null;
    }
    if (!active || !nearby || !currentSource || firstFrameRendered || errorMessage) return;

    firstFrameTimerRef.current = setTimeout(() => {
      firstFrameTimerRef.current = null;
      if (!isMountedRef.current || firstFrameRendered) return;
      const message = 'This reel is taking too long to start. Tap Retry.';
      metricsRef.current.onError(message);
      setPlaybackState('ERROR');
      setIsDebouncedBuffering(false);
      setErrorMessage(message);
      try {
        player.pause();
      } catch {
        // Best-effort; retry will rebuild playback state.
      }
    }, FIRST_FRAME_TIMEOUT_MS);

    return () => {
      if (firstFrameTimerRef.current) {
        clearTimeout(firstFrameTimerRef.current);
        firstFrameTimerRef.current = null;
      }
    };
  }, [active, nearby, currentSource, firstFrameRendered, errorMessage, player]);

  // Instagram parity: mute/unmute this reel's player only.
  // The player mutation runs outside the state updater (updaters must be pure).
  const toggleMute = useCallback(() => {
    const next = !muted;
    try {
      player.muted = next;
    } catch {
      // Mute is best-effort on platforms that restrict it.
    }
    setMuted(next);
  }, [player, muted]);

  // Manual retry handler — resets the automatic refresh budget.
  const retry = useCallback(async () => {
    errorRefreshAttemptsRef.current = 0;
    setErrorMessage(null);
    setFirstFrameRendered(false);
    setPlaybackState('PREPARING');
    if (token) {
      try {
        const res = await fetchPlayback(item, token);
        if (res?.ok && res.playback_url && isMountedRef.current) {
          setCurrentSource(res.playback_url);
          setCurrentExpiryAt(res.playback_expires_at ?? null);
          metricsRef.current.onCredentialRefreshed();
          await swapSourcePreservingPosition(res.playback_url);
          return;
        }
      } catch {
        // Fall back to existing source attempt
      }
    }
    if (currentSource) {
      await player.replaceAsync(currentSource);
      if (active && !paused) player.play();
    }
  }, [item, token, currentSource, player, active, paused, swapSourcePreservingPosition]);

  // Flush once on unmount. The callback is kept in a ref so a parent render
  // cannot accidentally trigger effect cleanup and duplicate an impression.
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      // Guarantee no audio leaks past the component's lifetime: pause first,
      // then release the source so the native player fully detaches.
      try {
        player.pause();
      } catch {
        // Best-effort teardown.
      }
      void player.replaceAsync(null).catch(() => {});
      const payload = metricsRef.current.toImpressionPayload();
      if (payload.watched_ms && payload.watched_ms > 250) {
        onMetricsFlushRef.current?.(payload);
      }
    };
  }, [player]);

  // Flush when a Reel leaves the active slot, then reset the tracker so later
  // re-entry produces a new delta rather than resending cumulative watch time.
  const prevActiveRef = useRef(active);
  useEffect(() => {
    if (prevActiveRef.current && !active) {
      const payload = metricsRef.current.toImpressionPayload();
      if (payload.watched_ms && payload.watched_ms > 250) {
        onMetricsFlushRef.current?.(payload);
      }
      metricsRef.current = new ReelMetricsTracker(item, 'REELS');
      playbackStartedRef.current = false;
    }
    prevActiveRef.current = active;
  }, [active, item.source_type, item.source_id, item.post_id]);

  const handleFirstFrameRender = useCallback(() => {
    if (firstFrameTimerRef.current) {
      clearTimeout(firstFrameTimerRef.current);
      firstFrameTimerRef.current = null;
    }
    setFirstFrameRendered(true);
    metricsRef.current.onFirstFrame();
    setErrorMessage(null);
  }, []);

  return {
    player,
    playbackState,
    firstFrameRendered,
    isDebouncedBuffering,
    errorMessage,
    retry,
    handleFirstFrameRender,
    progressAnim,
    muted,
    toggleMute,
  };
}
