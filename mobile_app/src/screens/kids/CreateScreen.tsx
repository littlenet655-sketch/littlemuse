import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Image, Pressable, ScrollView, StyleSheet, Text, TextInput, View, Alert } from 'react-native';
import { Feather } from '@expo/vector-icons';
import { useVideoPlayer } from 'expo-video';
import { completeUpload, formatBytes, requestUploadSession, type UploadSession, type UploadStage } from '../../api/kidsUpload';
import { useAuth } from '../../auth/AuthProvider';
import { isUploadCancelled, putFileToSignedUrl } from '../../kids/directUpload';
import { capturePostMedia, localMediaSize, pickGalleryMedia, validateMediaIdentity, type PickedMedia } from '../../kids/postMedia';
import type { ChildScreenProps } from '../../navigation/types';
import { Card, Field, GateNotice, Notice, StepIndicator } from '../../ui/components';
import { NativeVideoView } from '../../ui/nativeViews';
import { colors, shadow, spacing } from '../../ui/tokens';
import { clampAspectRatio } from '../../video/types';

type Kind = 'post' | 'reel' | 'story';

const SUGGESTED_TAGS = ['art', 'fun', 'learning', 'nature', 'friends', 'school'];

/** Muted first-frame preview of the picked local video — never autoplays audio. */
function LocalVideoPreview({ uri, width, height }: { uri: string; width?: number; height?: number }) {
  const player = useVideoPlayer(uri, (instance) => {
    instance.muted = true;
    instance.loop = false;
  });
  const [firstFrame, setFirstFrame] = useState(false);
  const aspect = width && height && width > 0 && height > 0 ? clampAspectRatio(width / height) : null;

  useEffect(() => {
    setFirstFrame(false);
  }, [uri]);

  useEffect(() => () => {
    try {
      player.pause();
    } catch {
      // Best-effort teardown.
    }
  }, [player]);

  return (
    <View style={[styles.previewVideo, aspect ? { aspectRatio: aspect } : { height: 240 }]}>
      <NativeVideoView
        player={player}
        style={StyleSheet.absoluteFill}
        contentFit="contain"
        nativeControls={false}
        onFirstFrameRender={() => setFirstFrame(true)}
      />
      {!firstFrame ? (
        <View style={styles.previewVideoLoading} pointerEvents="none">
          <ActivityIndicator size="small" color="#FFFFFF" />
        </View>
      ) : null}
      <View style={styles.previewVideoBadge} pointerEvents="none">
        <Feather name="film" size={12} color="#FFFFFF" />
        <Text style={styles.previewVideoBadgeText}>Video preview</Text>
      </View>
    </View>
  );
}

type CreateTabParams = { initialKind?: Kind } | undefined;

export function CreateScreen({ navigation, route }: ChildScreenProps<'KidsTabs'>) {
  const { session } = useAuth();
  // Deep links (e.g. the "+ Story" button in StoriesScreen) can request an
  // initial composer mode. CreateTab is typed as `undefined` params in
  // navigation/types.ts, so the runtime param is read through a cast.
  const initialKind = ((route as { params?: CreateTabParams } | undefined)?.params?.initialKind ?? 'post') as Kind;
  const [kind, setKind] = useState<Kind>(['post', 'reel', 'story'].includes(initialKind) ? initialKind : 'post');

  // Re-navigation to an already-mounted CreateScreen (e.g. tapping "+ Story"
  // again after posting) carries fresh params — sync the composer mode then.
  const initialKindRef = useRef(initialKind);
  useEffect(() => {
    if (initialKindRef.current !== initialKind) {
      initialKindRef.current = initialKind;
      if (['post', 'reel', 'story'].includes(initialKind)) {
        setKind(initialKind);
        setMedia(null);
        setStatus('');
        setError(null);
      }
    }
  }, [initialKind]);
  const [media, setMedia] = useState<PickedMedia | null>(null);
  const [caption, setCaption] = useState('');
  const [tags, setTags] = useState('');
  const [location, setLocation] = useState('');
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [status, setStatus] = useState('');
  const [error, setError] = useState<unknown>(null);
  const [failedStage, setFailedStage] = useState<UploadStage | null>(null);
  const nav = navigation as unknown as { navigate: (r: string, p: object) => void };
  const abortRef = useRef<AbortController | null>(null);
  const sessionRef = useRef<UploadSession | null>(null);

  // Never leave a native upload running after the screen goes away.
  useEffect(() => () => {
    abortRef.current?.abort();
  }, []);

  // Draft-loss guard: a kid who picked media or typed a caption should not
  // lose it to an accidental back tap. Blocked only while composing —
  // never during/after a share.
  const hasDraft = Boolean(media || caption.trim() || tags.trim());
  useEffect(() => {
    if (!hasDraft || busy) return;
    const sub = navigation.addListener('beforeRemove', (e) => {
      if (busy) return; // a share in flight must not be interrupted
      e.preventDefault();
      Alert.alert(
        'Discard your post?',
        'You have an unfinished post. Going back will discard it.',
        [
          { text: 'Keep editing', style: 'cancel', onPress: () => {} },
          {
            text: 'Discard',
            style: 'destructive',
            onPress: () => navigation.dispatch(e.data.action),
          },
        ],
      );
    });
    return sub;
  }, [navigation, hasDraft, busy]);

  function resetPipelineState() {
    sessionRef.current = null;
    abortRef.current = null;
    setFailedStage(null);
    setProgress(null);
    setUploading(false);
  }

  async function choose(fn: () => Promise<PickedMedia | null>) {
    try {
      const picked = await fn();
      if (picked) {
        setMedia(picked);
        setError(null);
        resetPipelineState();
      }
    } catch (err) {
      setError(err);
    }
  }

  function addTag(tag: string) {
    const list = tags.split(',').map((t) => t.trim()).filter(Boolean);
    if (!list.includes(tag)) {
      setTags([...list, tag].join(', '));
    }
  }

  function cancelUpload() {
    abortRef.current?.abort();
  }

  async function publish() {
    if (!session || !media || busy) return;
    setBusy(true);
    setError(null);
    // Resume where the last attempt failed: a live upload session is reused so
    // a retry never pays for the session step twice.
    let stage: UploadStage = failedStage === 'r2upload' || failedStage === 'complete' ? failedStage : 'session';
    setFailedStage(null);
    try {
      const mediaType = media.mimeType.startsWith('video/') ? 'VIDEO' : 'IMAGE';
      validateMediaIdentity(media.fileName, media.mimeType);
      const sizeBytes = localMediaSize(media.uri);

      let sess = sessionRef.current;
      if (stage === 'session' || !sess) {
        stage = 'session';
        setStatus('Preparing safe upload…');
        setProgress(null);
        sess = await requestUploadSession(session.token, {
          kind,
          filename: media.fileName,
          mediaType,
          sizeBytes,
          mimeType: media.mimeType,
        });
        sessionRef.current = sess;
      }

      if (stage === 'session' || stage === 'r2upload') {
        stage = 'r2upload';
        setUploading(true);
        const controller = new AbortController();
        abortRef.current = controller;
        setProgress(0);
        await putFileToSignedUrl(sess.upload_url, media.uri, sess.required_headers, {
          signal: controller.signal,
          onProgress: (sent, total) => {
            const pct = total > 0 ? Math.min(1, Math.max(0, sent / total)) : 0;
            setProgress(pct);
            setStatus(`Uploading securely… ${Math.round(pct * 100)}%`);
          },
        });
        abortRef.current = null;
        setUploading(false);
      }

      stage = 'complete';
      setProgress(null);
      setStatus('LittleNet AI safety check…');
      const done = await completeUpload(session.token, sess.upload_id, {
        caption: caption.trim(),
        contentCategory: kind === 'reel' ? 'Fun' : 'Other',
        tags: tags.split(',').map((t) => t.trim()).filter(Boolean),
        locationName: location.trim(),
      });
      resetPipelineState();
      // Hand the local preview to the status screen; the authoritative
      // published state always comes from the server poll, never this preview.
      nav.navigate('ProcessingStatus', {
        postId: done.post_id,
        localUri: media.uri,
        mediaType,
      });
      // Instagram-style: clear the composer so coming back starts a fresh post.
      setMedia(null);
      setCaption('');
      setTags('');
      setLocation('');
    } catch (err) {
      if (isUploadCancelled(err)) {
        // The presigned session survives a cancel: retry resumes the PUT.
        setFailedStage('r2upload');
        setStatus('Upload cancelled. Your file is still selected — tap Share Safely to resume.');
      } else {
        setError(err);
        setFailedStage(stage);
        setStatus(
          stage === 'session'
            ? 'Could not start the safe upload (check your connection). Your details are saved — tap Share Safely to retry.'
            : stage === 'r2upload'
              ? 'The upload was interrupted. Your file is still selected — tap Share Safely to resume.'
              : 'Finishing up hit a snag. Tap Share Safely to retry — this step is safe to repeat.',
        );
      }
    } finally {
      setBusy(false);
      setUploading(false);
      setProgress(null);
      abortRef.current = null;
    }
  }

  const isVideo = kind === 'reel';
  const pickedIsVideo = (media?.mimeType ?? '').startsWith('video/');
  // Visual step tracker: 1 = pick media, 2 = caption/details, 3 = sharing.
  const flowStep = !media ? 1 : busy ? 3 : 2;
  const flowLabels = ['Pick media', 'Add caption', 'Sharing'] as const;

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
      {/* Creation flow steps (visual only) */}
      <StepIndicator
        step={flowStep}
        total={3}
        label={flowLabels[flowStep - 1]}
        steps={['Pick media', 'Add caption', 'Sharing']}
      />

      {/* Mode Switcher — pill chips */}
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.kindChips}
      >
        {(['post', 'reel', 'story'] as Kind[]).map((k) => {
          const active = kind === k;
          const label = k === 'post' ? 'Photo Post' : k === 'reel' ? 'Short Reel' : 'Daily Story';
          const icon = k === 'post' ? 'image' : k === 'reel' ? 'film' : 'zap';
          return (
            <Pressable
              key={k}
              disabled={busy}
              accessibilityRole="button"
              accessibilityLabel={label}
              accessibilityState={{ selected: active }}
              onPress={() => {
                setKind(k);
                setMedia(null);
                resetPipelineState();
                setStatus('');
                setError(null);
              }}
              style={[styles.kindBtn, active && styles.kindBtnActive]}
            >
              <Feather name={icon} size={14} color={active ? '#FFFFFF' : '#64748B'} />
              <Text style={[styles.kindText, active && styles.kindTextActive]}>{label}</Text>
            </Pressable>
          );
        })}
      </ScrollView>

      {error ? <GateNotice error={error} /> : null}
      {status ? <Notice tone="info" message={status} /> : null}

      {/* Determinate upload progress */}
      {progress !== null ? (
        <View style={styles.progressWrap} accessibilityRole="progressbar">
          <View style={styles.progressTrack}>
            <View style={[styles.progressFill, { width: `${Math.round(progress * 100)}%` }]} />
          </View>
          <View style={styles.progressRow}>
            <Text style={styles.progressLabel}>{Math.round(progress * 100)}% uploaded</Text>
            {uploading ? (
              <Pressable onPress={cancelUpload} style={styles.cancelBtn} accessibilityRole="button" accessibilityLabel="Cancel upload">
                <Feather name="x" size={14} color="#DC2626" />
                <Text style={styles.cancelText}>Cancel</Text>
              </Pressable>
            ) : null}
          </View>
        </View>
      ) : null}

      {/* Media Picker / Preview */}
      {!media ? (
        <Card style={styles.pickerCard}>
          <Text style={styles.sectionHeading}>
            {isVideo ? 'Choose or record a video' : 'Choose or snap a photo'}
          </Text>
          <View style={styles.pickRow}>
            {isVideo ? (
              <>
                <Pressable
                  style={styles.pickOption}
                  accessibilityRole="button"
                  accessibilityLabel="Choose a video from your gallery"
                  onPress={() => void choose(() => pickGalleryMedia('video'))}
                >
                  <View style={[styles.pickIconCircle, { backgroundColor: '#EFF6FF' }]}>
                    <Feather name="film" size={24} color={colors.brand} />
                  </View>
                  <Text style={styles.pickOptionTitle}>Gallery Video</Text>
                  <Text style={styles.pickOptionSub}>Choose from files</Text>
                </Pressable>
                <Pressable
                  style={styles.pickOption}
                  accessibilityRole="button"
                  accessibilityLabel="Record a video with the camera"
                  onPress={() => void choose(() => capturePostMedia('video'))}
                >
                  <View style={[styles.pickIconCircle, { backgroundColor: '#FDF2F8' }]}>
                    <Feather name="video" size={24} color="#DB2777" />
                  </View>
                  <Text style={styles.pickOptionTitle}>Camera Video</Text>
                  <Text style={styles.pickOptionSub}>Record right now</Text>
                </Pressable>
              </>
            ) : (
              <>
                <Pressable
                  style={styles.pickOption}
                  accessibilityRole="button"
                  accessibilityLabel="Choose a photo from your gallery"
                  onPress={() => void choose(() => pickGalleryMedia('image'))}
                >
                  <View style={[styles.pickIconCircle, { backgroundColor: '#EFF6FF' }]}>
                    <Feather name="image" size={24} color={colors.brand} />
                  </View>
                  <Text style={styles.pickOptionTitle}>Choose Photo</Text>
                  <Text style={styles.pickOptionSub}>From your gallery</Text>
                </Pressable>
                <Pressable
                  style={styles.pickOption}
                  accessibilityRole="button"
                  accessibilityLabel="Take a photo with the camera"
                  onPress={() => void choose(() => capturePostMedia('image'))}
                >
                  <View style={[styles.pickIconCircle, { backgroundColor: '#ECFDF5' }]}>
                    <Feather name="camera" size={24} color="#10B981" />
                  </View>
                  <Text style={styles.pickOptionTitle}>Take Photo</Text>
                  <Text style={styles.pickOptionSub}>Snap with camera</Text>
                </Pressable>
              </>
            )}
          </View>
        </Card>
      ) : (
        <Card style={styles.previewCard}>
          {pickedIsVideo ? (
            <LocalVideoPreview uri={media.uri} width={media.width} height={media.height} />
          ) : (
            <Image source={{ uri: media.uri }} style={styles.previewImg} resizeMode="cover" />
          )}
          <View style={styles.previewBottom}>
            <View style={styles.fileInfo}>
              <Feather name="check-circle" size={14} color="#10B981" />
              <Text style={styles.fileText} numberOfLines={1}>
                {media.fileName}{typeof media.fileSize === 'number' && media.fileSize > 0 ? ` · ${formatBytes(media.fileSize)}` : ''}
              </Text>
            </View>
            <Pressable
              disabled={busy}
              accessibilityRole="button"
              accessibilityLabel="Change the selected media"
              onPress={() => {
                setMedia(null);
                resetPipelineState();
                setStatus('');
                setError(null);
              }}
              style={styles.changeBtn}
            >
              <Text style={styles.changeBtnText}>Change</Text>
            </Pressable>
          </View>
        </Card>
      )}

      {/* Post Details */}
      <Card>
        {/* Instagram-style borderless caption composer */}
        <View style={styles.captionWrap}>
          <Text style={styles.captionLabel}>CAPTION</Text>
          <TextInput
            style={styles.captionInput}
            value={caption}
            onChangeText={setCaption}
            multiline
            numberOfLines={3}
            textAlignVertical="top"
            placeholder="Write a kind caption…"
            placeholderTextColor="#94A3B8"
            maxLength={2200}
            accessibilityLabel="Caption"
          />
          <Text style={styles.captionCounter} accessibilityLabel={`${caption.length} of 2200 characters used`}>
            {caption.length}/2200
          </Text>
        </View>

        {/* Suggested Quick Tags */}
        <View style={styles.tagSection}>
          <Text style={styles.tagLabel}>QUICK TAGS</Text>
          <View style={styles.tagRow}>
            {SUGGESTED_TAGS.map((t) => (
              <Pressable
                key={t}
                onPress={() => addTag(t)}
                style={styles.tagChip}
                accessibilityRole="button"
                accessibilityLabel={`Add tag ${t}`}
              >
                <Text style={styles.tagChipText}>#{t}</Text>
              </Pressable>
            ))}
          </View>
        </View>

        <Field
          label="Tags"
          value={tags}
          onChangeText={setTags}
          placeholder="art, school, reading"
        />

        <Field
          label="Location (optional)"
          value={location}
          onChangeText={setLocation}
          placeholder="Home, School, Art Class"
        />
      </Card>

      {/* Safety Notice Card */}
      <View style={styles.safetyBox}>
        <Feather name="shield" size={16} color="#10B981" />
        <Text style={styles.safetyText}>
          LittleNet AI automatically checks every upload for child safety before sharing.
        </Text>
      </View>

      {/* Submit Button */}
      <Pressable
        onPress={() => void publish()}
        disabled={busy || !media}
        accessibilityRole="button"
        accessibilityLabel={busy ? 'Sharing your post' : 'Share safely'}
        accessibilityState={{ disabled: busy || !media }}
        style={[styles.publishBtn, (busy || !media) && styles.publishBtnDisabled]}
      >
        {busy ? (
          <ActivityIndicator size="small" color="#FFFFFF" />
        ) : (
          <Feather name="send" size={18} color="#FFFFFF" />
        )}
        <Text style={styles.publishBtnText}>
          {busy ? 'Sharing Safely…' : failedStage ? 'Resume Sharing ✨' : 'Share Safely ✨'}
        </Text>
      </Pressable>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  scrollContent: {
    padding: 16,
    paddingBottom: 40,
  },
  // Mode chips (pill selectors)
  kindChips: {
    flexDirection: 'row',
    gap: 8,
    paddingBottom: 14,
    paddingRight: 4,
  },  kindBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 9,
    paddingHorizontal: 14,
    borderRadius: 999,
    backgroundColor: '#F1F5F9',
    borderWidth: 1,
    borderColor: '#E2E8F0',
  },
  kindBtnActive: {
    backgroundColor: colors.brand,
  },
  kindText: {
    fontSize: 13,
    fontWeight: '700',
    color: '#64748B',
  },
  kindTextActive: {
    color: '#FFFFFF',
  },
  progressWrap: {
    backgroundColor: colors.surface,
    borderRadius: 12,
    padding: 12,
    marginBottom: 14,
    borderWidth: 1,
    borderColor: '#E2E8F0',
  },
  progressTrack: {
    height: 8,
    borderRadius: 4,
    backgroundColor: '#E2E8F0',
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    borderRadius: 4,
    backgroundColor: colors.brand,
  },
  progressRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: 8,
  },
  progressLabel: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.muted,
  },
  cancelBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 12,
    backgroundColor: '#FEF2F2',
  },
  cancelText: {
    fontSize: 12,
    fontWeight: '700',
    color: '#DC2626',
  },
  pickerCard: {
    padding: 16,
    marginBottom: 14,
  },
  sectionHeading: {
    fontSize: 14,
    fontWeight: '800',
    color: colors.ink,
    marginBottom: 12,
  },
  pickRow: {
    flexDirection: 'row',
    gap: 12,
  },
  pickOption: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: 18,
    paddingHorizontal: 10,
    backgroundColor: '#F8FAFC',
    borderRadius: 14,
    borderWidth: 1.5,
    borderColor: '#E2E8F0',
    borderStyle: 'dashed',
  },
  pickIconCircle: {
    width: 48,
    height: 48,
    borderRadius: 24,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 8,
  },
  pickOptionTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.ink,
    marginBottom: 2,
  },
  pickOptionSub: {
    fontSize: 11,
    color: colors.muted,
  },
  previewCard: {
    padding: 0,
    overflow: 'hidden',
    marginBottom: 14,
    borderRadius: 12,
    ...shadow.card,
  },
  previewImg: {
    width: '100%',
    height: 240,
    backgroundColor: '#F1F5F9',
    borderTopLeftRadius: 12,
    borderTopRightRadius: 12,
  },
  previewVideo: {
    width: '100%',
    backgroundColor: '#0F172A',
    borderTopLeftRadius: 12,
    borderTopRightRadius: 12,
    overflow: 'hidden',
  },
  previewVideoLoading: {
    ...StyleSheet.absoluteFill,
    alignItems: 'center',
    justifyContent: 'center',
  },
  previewVideoBadge: {
    position: 'absolute',
    left: 10,
    bottom: 10,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    backgroundColor: 'rgba(0,0,0,0.55)',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 10,
  },
  previewVideoBadgeText: {
    color: '#FFFFFF',
    fontSize: 11,
    fontWeight: '700',
  },
  previewBottom: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 14,
    paddingVertical: 10,
    backgroundColor: colors.surface,
  },
  fileInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    flex: 1,
  },
  fileText: {
    fontSize: 12,
    color: colors.ink,
    fontWeight: '600',
  },
  changeBtn: {
    paddingHorizontal: 12,
    paddingVertical: 5,
    borderRadius: 12,
    backgroundColor: '#F1F5F9',
  },
  changeBtnText: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.brand,
  },
  captionWrap: {
    marginBottom: 4,
  },
  captionLabel: {
    fontSize: 10,
    fontWeight: '800',
    color: '#94A3B8',
    letterSpacing: 0.8,
    marginBottom: 6,
  },
  captionInput: {
    fontSize: 14,
    color: colors.ink,
    minHeight: 72,
    paddingVertical: 4,
  },
  captionCounter: {
    fontSize: 11,
    color: '#94A3B8',
    textAlign: 'right',
    marginTop: 2,
  },
  tagSection: {
    marginTop: 10,
  },
  tagLabel: {
    fontSize: 10,
    fontWeight: '800',
    color: '#94A3B8',
    letterSpacing: 0.8,
    marginBottom: 6,
  },
  tagRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  tagChip: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
    backgroundColor: '#F1F5F9',
  },
  tagChipText: {
    fontSize: 11,
    fontWeight: '700',
    color: colors.brand,
  },
  safetyBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: '#ECFDF5',
    borderWidth: 1,
    borderColor: '#A7F3D0',
    borderRadius: 12,
    padding: 12,
    marginBottom: 16,
  },
  safetyText: {
    flex: 1,
    fontSize: 12,
    color: '#065F46',
    lineHeight: 16,
    fontWeight: '600',
  },
  publishBtn: {
    backgroundColor: colors.brand,
    borderRadius: 999,
    minHeight: 44,
    paddingVertical: 12,
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 8,
    shadowColor: colors.brand,
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.25,
    shadowRadius: 6,
    elevation: 3,
  },
  publishBtnDisabled: {
    opacity: 0.5,
    elevation: 0,
  },
  publishBtnText: {
    color: '#FFFFFF',
    fontSize: 15,
    fontWeight: '800',
  },
});
