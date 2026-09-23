import { useEffect, useRef } from 'react';
import { Image, StyleSheet, Text, View } from 'react-native';
import { Feather } from '@expo/vector-icons';
import { useVideoPlayer } from 'expo-video';
import { MAX_POLL_ATTEMPTS, moderationCopy } from '../../kids/social';
import { useProcessingStatus } from '../../kids/useProcessing';
import type { ChildScreenProps } from '../../navigation/types';
import { useIsForeground } from '../../query/client';
import { invalidateSocialCaches } from '../../query/keys';
import { BrandHeader, Button, Card, GateNotice, Notice, Screen } from '../../ui/components';
import { colors, spacing } from '../../ui/tokens';
import { NativeVideoView } from '../../ui/nativeViews';

interface ProcessingRouteParams {
  postId?: number;
  /** Local file preview passed by CreateScreen — display only, never authoritative. */
  localUri?: string;
  mediaType?: 'IMAGE' | 'VIDEO';
}

function VideoPreview({ uri }: { uri: string }) {
  const player = useVideoPlayer(uri, (instance) => {
    instance.loop = true;
    instance.muted = true;
    instance.play();
  });
  return (
    <NativeVideoView
      player={player}
      style={styles.preview}
      contentFit="cover"
      nativeControls={false}
    />
  );
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
  // Local media is comfort-only while the server remains authoritative.
  // Images and videos can both stay visible while moderation runs.
  const isVideo = params.mediaType === 'VIDEO';
  const serverPoster = poll.result?.poster_url || undefined;
  const serverMedia = poll.result?.media_url || undefined;
  const localImagePreview = !allowed && !isVideo ? params.localUri : undefined;
  const localVideoPreview = !allowed && isVideo ? params.localUri : undefined;
  const previewUri = allowed ? serverPoster || (!isVideo ? serverMedia : undefined) || localImagePreview : localImagePreview;
  const videoPreviewUri = isVideo ? (allowed ? serverMedia : localVideoPreview) : undefined;
  const showVideoPlaceholder = isVideo && !videoPreviewUri && !serverPoster;

  return (
    <Screen hasNativeHeader={false}>
      <BrandHeader title="Safety check" subtitle={allowed ? 'Your post is live!' : `Post #${postId}: ${poll.status}`}  onBack={() => navigation.goBack()} />

      {previewUri ? (
        <Card style={styles.previewCard}>
          <Image source={{ uri: previewUri }} style={styles.preview} resizeMode="cover" />
          <View style={styles.previewTag}>
            <Feather name={allowed ? 'check-circle' : 'clock'} size={12} color="#FFFFFF" />
            <Text style={styles.previewTagText}>{allowed ? 'Published' : 'Waiting for safety check'}</Text>
          </View>
        </Card>
      ) : null}

      {videoPreviewUri ? (
        <Card style={styles.previewCard}>
          <VideoPreview uri={videoPreviewUri} />
          <View style={styles.previewTag}>
            <Feather name={allowed ? 'check-circle' : 'clock'} size={12} color="#FFFFFF" />
            <Text style={styles.previewTagText}>{allowed ? 'Published' : 'Checking your video'}</Text>
          </View>
        </Card>
      ) : null}

      {showVideoPlaceholder ? (
        <Card style={styles.previewCard}>
          <View style={styles.videoPreviewPlaceholder}>
            <Feather name="film" size={30} color={colors.muted} />
            <Text style={styles.videoPreviewText}>
              Your video is being checked for safety.{'\n'}You can keep this screen open or come back later.
            </Text>
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
        <Button label={poll.refreshing ? 'Checking…' : 'Refresh status'} disabled={poll.refreshing || blocked} onPress={() => void poll.refresh()} />
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
