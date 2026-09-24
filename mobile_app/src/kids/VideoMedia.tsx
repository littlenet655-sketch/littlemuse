import { useEffect, useRef, useState } from 'react';
import { Image, StyleSheet, Text, View } from 'react-native';
import { useVideoPlayer } from 'expo-video';
import { useIsForeground } from '../query/client';
import { Button } from '../ui/components';
import { NativeVideoView } from '../ui/nativeViews';
import { colors, radius, spacing } from '../ui/tokens';
import { clampAspectRatio } from '../video/types';

export function VideoMedia({
  source,
  posterUrl,
  active = true,
  height = 380,
  aspectRatio,
  onComplete,
  nativeControls = true,
  loop = false,
  muted = false,
  /**
   * Optional one-shot credential refresh. When playback fails (e.g. an expired
   * signed URL), the component asks for a fresh source once before showing the
   * error UI. Return null when no fresh source is available.
   */
  refreshSource,
}: {
  source: string;
  posterUrl?: string | null;
  active?: boolean;
  height?: number;
  aspectRatio?: number;
  onComplete?: () => void;
  nativeControls?: boolean;
  loop?: boolean;
  muted?: boolean;
  refreshSource?: () => Promise<string | null>;
}) {
  const foreground = useIsForeground();
  const player = useVideoPlayer(null);
  const sourceRef = useRef<string | null>(null);
  const refreshTriedRef = useRef(false);
  const refreshSourceRef = useRef(refreshSource);
  const [liveSource, setLiveSource] = useState(source);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [posterAspect, setPosterAspect] = useState<number | null>(null);

  useEffect(() => {
    refreshSourceRef.current = refreshSource;
  }, [refreshSource]);

  // A fresh `source` prop resets all per-source state (retry budget included).
  useEffect(() => {
    setLiveSource(source);
    refreshTriedRef.current = false;
    setError(null);
    setReady(false);
  }, [source]);

  // Graceful measured fallback: derive the frame from the poster when the
  // caller did not supply an explicit aspect ratio.
  useEffect(() => {
    setPosterAspect(null);
    if (aspectRatio || !posterUrl) return;
    let cancelled = false;
    Image.getSize(
      posterUrl,
      (w, h) => {
        if (!cancelled && w > 0 && h > 0) setPosterAspect(clampAspectRatio(w / h));
      },
      () => {},
    );
    return () => {
      cancelled = true;
    };
  }, [posterUrl, aspectRatio]);

  const shellStyle = aspectRatio || posterAspect
    ? { aspectRatio: aspectRatio ?? posterAspect ?? 1 }
    : { height };

  const playableSource = active && foreground ? liveSource : null;

  useEffect(() => {
    player.loop = loop;
    player.muted = muted;
  }, [loop, muted, player]);

  useEffect(() => {
    const subscription = player.addListener('statusChange', ({ status, error: playbackError }) => {
      if (status === 'error') {
        // One bounded attempt at a credential refresh before giving up.
        if (!refreshTriedRef.current && refreshSourceRef.current) {
          refreshTriedRef.current = true;
          void refreshSourceRef.current()
            .then((fresh) => {
              if (fresh && fresh !== sourceRef.current) {
                setLiveSource(fresh);
              } else {
                setError(playbackError?.message ?? 'This video could not play.');
              }
            })
            .catch(() => {
              setError(playbackError?.message ?? 'This video could not play.');
            });
        } else {
          setError(playbackError?.message ?? 'This video could not play.');
        }
      }
    });
    const completeSub = player.addListener('playToEnd', () => {
      onComplete?.();
    });
    return () => {
      subscription.remove();
      completeSub.remove();
    };
  }, [player, onComplete]);

  useEffect(() => {
    if (sourceRef.current === playableSource) return;
    sourceRef.current = playableSource;
    setReady(false);
    setError(null);
    void player.replaceAsync(playableSource).then(() => {
      if (playableSource && sourceRef.current === playableSource) player.play();
    }).catch((reason: unknown) => {
      setError(reason instanceof Error ? reason.message : 'This video could not play.');
    });
  }, [playableSource, player]);

  useEffect(() => {
    if (playableSource && !error) player.play();
    else player.pause();
  }, [error, playableSource, player]);

  useEffect(() => () => player.pause(), [player]);

  async function retry() {
    if (!playableSource) return;
    // Manual retry spends a fresh refresh attempt when a refresher exists.
    refreshTriedRef.current = false;
    setError(null);
    setReady(false);
    const refresher = refreshSourceRef.current;
    if (refresher) {
      refreshTriedRef.current = true;
      try {
        const fresh = await refresher();
        if (fresh) {
          setLiveSource(fresh);
          return;
        }
      } catch {
        // Fall through to the direct retry below.
      }
    }
    try {
      await player.replaceAsync(playableSource);
      if (sourceRef.current === playableSource) player.play();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'This video could not play.');
    }
  }

  return (
    <View style={[styles.shell, shellStyle]}>
      <NativeVideoView player={player} style={styles.video} contentFit="cover" nativeControls={nativeControls} onFirstFrameRender={() => setReady(true)} />
      {!ready && posterUrl ? <Image source={{ uri: posterUrl }} style={styles.overlay} /> : null}
      {!ready && !posterUrl && !error ? <View style={styles.overlayCenter}><Text style={styles.loading}>Loading video…</Text></View> : null}
      {error ? <View style={styles.overlayCenter}><Text style={styles.error}>Playback failed.</Text><Button label="Retry" onPress={() => void retry()} /></View> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  shell: { width: '100%', borderRadius: radius.lg, overflow: 'hidden', backgroundColor: colors.ink },
  video: { width: '100%', height: '100%' },
  overlay: { ...StyleSheet.absoluteFill, width: '100%', height: '100%' },
  overlayCenter: { ...StyleSheet.absoluteFill, alignItems: 'center', justifyContent: 'center', gap: spacing.sm, backgroundColor: 'rgba(0,0,0,0.68)' },
  loading: { color: colors.surface, fontWeight: '700' },
  error: { color: colors.surface, fontWeight: '700' },
});
