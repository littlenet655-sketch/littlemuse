import { useEffect, useRef, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { Image } from 'expo-image';
import { useVideoPlayer, VideoView } from 'expo-video';
import { Feather } from '@expo/vector-icons';
import { MAX_POLL_ATTEMPTS, moderationCopy } from '../../kids/social';
import { useProcessingStatus } from '../../kids/useProcessing';
import type { ChildScreenProps } from '../../navigation/types';
import { useIsForeground } from '../../query/client';
import { invalidateSocialCaches } from '../../query/keys';
import { BrandHeader, Button, Card, GateNotice, Notice, Screen } from '../../ui/components';
import { colors, spacing } from '../../ui/tokens';

interface ProcessingRouteParams {
  postId?: number;
  /** Local file preview passed by CreateScreen — display only, never authoritative. */
  localUri?: string;
  mediaType?: 'IMAGE' | 'VIDEO';
}

const STEPS = [
  { key: 'uploaded', label: 'Uploaded', icon: 'upload-cloud' },
  { key: 'checking', label: 'Safety check', icon: 'shield' },
  { key: 'done', label: 'Published', icon: 'check-circle' },
] as const;

function stepIndexFor(stage: string): number {
  if (stage === 'allowed') return 2;
  if (stage === 'blocked' || stage === 'failed' || stage === 'retryable' || stage === 'review') return 1;
  return 1;
}

/** Elapsed seconds since mount — makes a slow safety check visible instead of a frozen spinner. */
function useElapsedSeconds(running: boolean): number {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!running) return;
    const started = Date.now();
    const t = setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(t);
  }, [running]);
  return elapsed;
}

function formatElapsed(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return m > 0 ? `${m}m ${s.toString().padStart(2, '0')}s` : `${s}s`;
}

export function ProcessingStatusScreen({ route, navigation }: ChildScreenProps<'ProcessingStatus'>) {
  const params = (route.params ?? {}) as ProcessingRouteParams;
  const postId = Number(params.postId ?? 0);
  const foreground = useIsForeground();
  const poll = useProcessingStatus(postId || null, foreground);
  const invalidatedPost = useRef<number | null>(null);
  const nav = navigation as unknown as { navigate: (r: string, p?: object) => void };

  useEffect(() => {
    if (poll.stage === 'allowed' && invalidatedPost.current !== postId) {
      invalidatedPost.current = postId;
      void invalidateSocialCaches([postId]);
    }
  }, [poll.stage, postId]);

  const exhausted = poll.attempts >= MAX_POLL_ATTEMPTS;
  const currentStep = stepIndexFor(poll.stage);
  const blocked = poll.stage === 'blocked';
  const allowed = poll.stage === 'allowed';
  const failed = poll.stage === 'failed' || poll.stage === 'retryable';
  // The local preview is a comfort placeholder only. The server result is
  // authoritative: nothing is shown as published unless stage === 'allowed'.
  // Local video files cannot render in an Image, so they get a placeholder.
  const serverPreview = poll.result?.poster_url || poll.result?.media_url || undefined;
  const localImagePreview =
    !allowed && params.mediaType === 'IMAGE' ? params.localUri : undefined;
  const previewUri = allowed ? serverPreview || localImagePreview : localImagePreview;
  const showVideoPlaceholder = !allowed && params.mediaType === 'VIDEO';
  const localVideoUri = showVideoPlaceholder ? params.localUri : undefined;
  const elapsed = useElapsedSeconds(!allowed && !blocked);
  // Local preview player: paused, muted, no controls — shows the real first
  // frame of the kid's own video while the server check runs. Display only;
  // the server result stays authoritative.
  const previewPlayer = useVideoPlayer(localVideoUri ?? null, (p) => {
    p.loop = false;
    p.muted = true;
  });
  useEffect(() => {
    try { previewPlayer.pause(); } catch { /* best-effort */ }
  }, [previewPlayer, localVideoUri]);

  return (
    <Screen hasNativeHeader={false}>
      <BrandHeader title="Safety check" onBack={() => navigation.goBack()} subtitle={allowed ? 'Your post is live!' : 'Uploaded ✓ — checking privately'} />

      {previewUri ? (
        <Card style={styles.previewCard}>
          <Image source={{ uri: previewUri }} style={styles.preview} contentFit="cover" cachePolicy="memory-disk" />
          <View style={styles.previewTag}>
            <Feather name={allowed ? 'check-circle' : 'clock'} size={12} color="#FFFFFF" />
            <Text style={styles.previewTagText}>{allowed ? 'Published' : 'Waiting for safety check'}</Text>
          </View>
        </Card>
      ) : null}

      {showVideoPlaceholder ? (
        <Card style={styles.previewCard}>
          {localVideoUri ? (
            <VideoView player={previewPlayer} style={styles.preview} contentFit="cover" nativeControls={false} />
          ) : (
            <View style={styles.videoPreviewPlaceholder}>
              <Feather name="film" size={30} color={colors.muted} />
              <Text style={styles.videoPreviewText}>
                Your video is being checked for safety.{'\n'}It'll appear here when it's approved.
              </Text>
            </View>
          )}
          <View style={styles.previewTag}>
            <Feather name="clock" size={12} color="#FFFFFF" />
            <Text style={styles.previewTagText}>Waiting for safety check</Text>
          </View>
        </Card>
      ) : null}

      {/* Stage timeline */}
      <Card>
        <View style={styles.timeline}>
          {STEPS.map((step, i) => {
            const doneStep = i < currentStep || allowed;
            const activeStep = i === currentStep && !allowed;
            return (
              <View key={step.key} style={styles.stepRow}>
                <View style={[styles.stepDot, doneStep && styles.stepDotDone, activeStep && styles.stepDotActive]}>
                  <Feather name={step.icon} size={14} color={doneStep || activeStep ? '#FFFFFF' : colors.muted} />
                </View>
                <Text style={[styles.stepLabel, (doneStep || activeStep) && styles.stepLabelActive]}>{step.label}</Text>
                {i < STEPS.length - 1 ? <View style={[styles.stepLine, doneStep && styles.stepLineDone]} /> : null}
              </View>
            );
          })}
        </View>
        <Text style={styles.copy}>{moderationCopy(poll.stage)}</Text>
        {!allowed && !blocked ? (
          <>
            <Text style={styles.uploadAck}>Uploaded ✓. Our safety models are checking it privately.</Text>
            <Text style={styles.elapsed}>Checking {formatElapsed(elapsed)} — you can keep browsing while this finishes.</Text>
          </>
        ) : null}
      </Card>

      {poll.error ? <GateNotice error={poll.error} /> : null}
      {poll.redriveError ? <GateNotice error={poll.redriveError} /> : null}
      {!foreground ? <Notice tone="info" message="Status checks pause while the app is in the background." /> : null}
      {exhausted && poll.stage === 'processing' ? <Notice tone="info" message="Automatic checks paused. You can refresh when you're ready." /> : null}

      {blocked ? (
        <Card>
          <Text style={styles.blockedTitle}>Not shared</Text>
          <Text style={styles.blockedBody}>
            Our safety check decided this post can't be shared. It was not published anywhere — only you can see this screen.
          </Text>
          <Button label="Create something new" onPress={() => nav.navigate('CreateTab')} />
        </Card>
      ) : null}

      {allowed ? (
        <Button label="View in feed" onPress={() => nav.navigate('FeedTab')} />
      ) : (
        <>
          {!blocked ? <Button label="Keep browsing" onPress={() => nav.navigate('FeedTab')} /> : null}
          <Button label={poll.refreshing ? 'Checking…' : 'Refresh status'} variant="secondary" disabled={poll.refreshing || blocked} onPress={() => void poll.refresh()} />
        </>
      )}
      {failed ? (
        <Button label={poll.redriving ? 'Trying again…' : 'Try again'} variant="secondary" disabled={poll.redriving} onPress={() => void poll.redrive()} />
      ) : null}
    </Screen>
  );
}

const styles = StyleSheet.create({
  previewCard: {
    padding: 0,
    overflow: 'hidden',
    marginBottom: spacing.md,
  },
  preview: {
    width: '100%',
    height: 180,
    backgroundColor: '#F1F5F9',
  },
  videoPreviewPlaceholder: {
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    paddingVertical: 40,
    paddingHorizontal: 24,
    backgroundColor: '#F1F5F9',
  },
  videoPreviewText: {
    color: colors.muted,
    textAlign: 'center',
    lineHeight: 20,
  },
  previewTag: {
    position: 'absolute',
    left: 10,
    bottom: 10,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    backgroundColor: 'rgba(0,0,0,0.6)',
    paddingHorizontal: 9,
    paddingVertical: 4,
    borderRadius: 10,
  },
  previewTagText: {
    color: '#FFFFFF',
    fontSize: 11,
    fontWeight: '700',
  },
  timeline: {
    paddingVertical: spacing.sm,
    gap: 0,
  },
  stepRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingVertical: 6,
  },
  stepDot: {
    width: 30,
    height: 30,
    borderRadius: 15,
    backgroundColor: '#F1F5F9',
    alignItems: 'center',
    justifyContent: 'center',
  },
  stepDotDone: {
    backgroundColor: '#10B981',
  },
  stepDotActive: {
    backgroundColor: colors.brand,
  },
  stepLabel: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.muted,
    flex: 1,
  },
  stepLabelActive: {
    color: colors.ink,
  },
  stepLine: {
    position: 'absolute',
    left: 14,
    top: 36,
    bottom: -6,
    width: 2,
    backgroundColor: '#E2E8F0',
  },
  stepLineDone: {
    backgroundColor: '#10B981',
  },
  copy: { color: colors.ink, fontSize: 15, lineHeight: 22, textAlign: 'center', paddingVertical: 12 },
  uploadAck: { color: colors.ok, fontSize: 14, fontWeight: '800', textAlign: 'center', paddingBottom: 4 },
  elapsed: { color: colors.muted, fontSize: 13, textAlign: 'center', paddingBottom: 8 },
  blockedTitle: {
    fontSize: 16,
    fontWeight: '800',
    color: colors.ink,
    marginBottom: 6,
  },
  blockedBody: {
    fontSize: 14,
    color: colors.muted,
    lineHeight: 20,
    marginBottom: 12,
  },
});
