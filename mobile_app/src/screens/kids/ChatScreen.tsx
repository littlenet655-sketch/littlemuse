import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Animated, FlatList, Image, Keyboard, KeyboardAvoidingView, Platform, Pressable, RefreshControl, StyleSheet, Text, TextInput, View } from 'react-native';
import { Feather } from '@expo/vector-icons';
import { useIsFocused } from '@react-navigation/native';
import { completeChatImageUpload, fetchChat, fetchChatUpdates, requestChatImageUpload, sendChatText, sendTyping, sharePostToChat, type ChatMessage } from '../../api/kidsChat';
import { ApiError } from '../../api/client';
import { useAuth } from '../../auth/AuthProvider';
import { putFileToSignedUrl } from '../../kids/directUpload';
import { capturePostMedia, localMediaSize, pickGalleryMedia, validateMediaIdentity } from '../../kids/postMedia';
import { CHAT_BLOCKED_COPY, dedupeChat, isChatMessagePending } from '../../kids/social';
import type { ChildScreenProps } from '../../navigation/types';
import { useIsForeground, useIsOnline } from '../../query/client';
import { Button, DisabledFeature, EmptyState, ErrorState, GateNotice, LoadingState, Notice, OfflineBanner, Screen } from '../../ui/components';
import { colors, radius } from '../../ui/tokens';

const PAGE_SIZE = 30;

type Row =
  | { kind: 'day'; key: string; label: string }
  | { kind: 'msg'; key: string; message: ChatMessage }
  | { kind: 'typing'; key: string };

function dayKey(iso?: string): string {
  const t = iso ? Date.parse(iso) : Number.NaN;
  if (Number.isNaN(t)) return 'unknown';
  const d = new Date(t);
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

function timeLabel(iso?: string): string {
  const t = iso ? Date.parse(iso) : Number.NaN;
  if (Number.isNaN(t)) return '';
  return new Date(t).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
}

/** Instagram-style animated "…" typing bubble shown inside the thread. */
function TypingDots() {
  const dots = [useRef(new Animated.Value(0.3)).current, useRef(new Animated.Value(0.3)).current, useRef(new Animated.Value(0.3)).current];
  useEffect(() => {
    const loops = dots.map((a, i) =>
      Animated.loop(
        Animated.sequence([
          Animated.delay(i * 180),
          Animated.timing(a, { toValue: 1, duration: 280, useNativeDriver: true }),
          Animated.timing(a, { toValue: 0.3, duration: 280, useNativeDriver: true }),
        ]),
      ),
    );
    loops.forEach((l) => l.start());
    return () => loops.forEach((l) => l.stop());
    // Dots are stable refs; run once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <View style={styles.typingBubble} accessibilityLabel="Peer is typing">
      {dots.map((a, i) => (
        <Animated.View key={i} style={[styles.typingDot, { opacity: a }]} />
      ))}
    </View>
  );
}

function dayLabel(iso?: string): string {
  const t = iso ? Date.parse(iso) : Number.NaN;
  if (Number.isNaN(t)) return '';
  const d = new Date(t);
  const now = new Date();
  const sameDay = (a: Date, b: Date) =>
    a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (sameDay(d, now)) return 'Today';
  if (sameDay(d, yesterday)) return 'Yesterday';
  return d.toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' });
}

export function ChatScreen({ route, navigation }: ChildScreenProps<'Chat'>) {
  const { session } = useAuth();
  const foreground = useIsForeground();
  const online = useIsOnline();
  const focused = useIsFocused();
  const peerId = Number((route.params as { peerId?: number } | undefined)?.peerId ?? 0);
  const postId = (route.params as { postId?: number } | undefined)?.postId;
  const ownId = session?.user.user_id ?? 0;
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [peer, setPeer] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [info, setInfo] = useState('');
  const [sendError, setSendError] = useState('');
  const [shareNotice, setShareNotice] = useState('');
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [mediaSending, setMediaSending] = useState(false);
  const [peerTyping, setPeerTyping] = useState(false);
  /** Message whose per-bubble timestamp is revealed (tap a bubble to toggle). */
  const [showTimeFor, setShowTimeFor] = useState<number | null>(null);
  const lastTypingSent = useRef(0);
  /** Negative temp ids for optimistic messages; server ids are positive. */
  const tempId = useRef(-1);
  /** Highest real message id seen; drives bottom-scroll only for new arrivals. */
  const maxSeenId = useRef(0);
  // Ref mirror so the poll interval always reads the latest messages.
  const messagesRef = useRef(messages);
  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);
  const flatListRef = useRef<FlatList>(null);
  const nav = navigation as unknown as { goBack: () => void; navigate: (r: string, p: object) => void };

  // Insert centered date-divider pills wherever the calendar day changes,
  // plus an Instagram-style typing bubble at the end while the peer types.
  const rows = useMemo<Row[]>(() => {
    const out: Row[] = [];
    let lastDay = '';
    for (const m of messages) {
      const day = dayKey(m.sent_at);
      if (day !== lastDay) {
        const label = dayLabel(m.sent_at);
        if (label) out.push({ kind: 'day', key: `d:${day}`, label });
        lastDay = day;
      }
      out.push({ kind: 'msg', key: `m:${m.child_message_id}`, message: m });
    }
    if (peerTyping) out.push({ kind: 'typing', key: 'typing' });
    return out;
  }, [messages, peerTyping]);

  /** Latest own ALLOWED message the peer has seen → Instagram "Seen" receipt.
      Shown under that message even if newer unseen own messages exist. */
  const seenMessageId = useMemo(() => {
    let latest: number | null = null;
    for (const m of messages) {
      if (m.sender_child_id !== ownId) continue;
      if (isChatMessagePending(m, true)) continue;
      if (m.is_seen) latest = m.child_message_id;
    }
    return latest;
  }, [messages, ownId]);

  useEffect(() => {
    const showSub = Keyboard.addListener(
      Platform.OS === 'ios' ? 'keyboardWillShow' : 'keyboardDidShow',
      () => {
        setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 100);
      }
    );
    return () => {
      showSub.remove();
    };
  }, []);

  const load = useCallback(async (mode: 'first' | 'more' | 'refresh' | 'silent', beforeId?: number) => {
    if (!session || !peerId || !foreground) return;
    if (mode === 'more' && (loadingMore || !hasMore)) return;
    if (mode === 'first') setLoading(true);
    if (mode === 'refresh') setRefreshing(true);
    if (mode === 'more') setLoadingMore(true);
    try {
      const res = await fetchChat(session.token, peerId, PAGE_SIZE, beforeId);
      setPeer(res.peer ?? {});
      setPeerTyping(!!res.peer_typing);
      const newRows = res.messages ?? [];
      setMessages((prev) => (mode === 'more' ? dedupeChat([...newRows, ...prev]) : dedupeChat(newRows)));
      if (mode === 'more' || mode === 'first') setHasMore(newRows.length >= PAGE_SIZE);
      setError(null);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
      setRefreshing(false);
      setLoadingMore(false);
    }
  }, [session, peerId, foreground, loadingMore, hasMore]);

  useEffect(() => { void load('first'); }, [session?.token, peerId, foreground]);

  // Pull the latest messages when the screen regains focus.
  useEffect(() => {
    if (focused && foreground && messages.length > 0) void load('silent');
  }, [focused, foreground]);

  // Real-time v1: while the chat is open and visible, poll for new messages
  // every few seconds and refresh the peer typing flag. Cheap indexed query;
  // the server stays authoritative and polling never clobbers the list.
  useEffect(() => {
    if (!session || !peerId || !focused || !foreground || !online || loading) return;
    const timer = setInterval(() => {
      void (async () => {
        try {
          // after_id=0 is valid: the server returns everything newer, so an
          // empty chat still picks up the peer's first message live.
          const maxId = messagesRef.current.reduce((m, x) => Math.max(m, x.child_message_id), 0);
          const res = await fetchChatUpdates(session.token, peerId, maxId);
          if (res.messages?.length) {
            setMessages((prev) => dedupeChat([...prev, ...res.messages]));
          }
          setPeerTyping(!!res.peer_typing);
        } catch {
          // Silent: transient poll failures must not disturb the chat.
        }
      })();
    }, 4000);
    return () => clearInterval(timer);
  }, [session, peerId, focused, foreground, online, loading]);

  // Typing heartbeat: throttled, fire-and-forget. The server owns the TTL.
  const onChangeText = useCallback((value: string) => {
    setText(value);
    if (!session || !peerId || !online || !value.trim()) return;
    const now = Date.now();
    if (now - lastTypingSent.current < 3000) return;
    lastTypingSent.current = now;
    void sendTyping(session.token, peerId).catch(() => {});
  }, [session, peerId, online]);

  // Auto-scroll to the bottom only when genuinely new messages arrive.
  // Paginating older history (prepend) leaves the scroll position alone —
  // scrolling to the end there would yank the reader away from old messages.
  useEffect(() => {
    if (messages.length === 0) {
      maxSeenId.current = 0;
      return;
    }
    const maxId = messages.reduce((m, x) => Math.max(m, x.child_message_id), 0);
    if (maxId > maxSeenId.current) {
      const firstLoad = maxSeenId.current === 0;
      maxSeenId.current = maxId;
      setTimeout(() => flatListRef.current?.scrollToEnd({ animated: !firstLoad }), 50);
    }
  }, [messages]);

  // Keep the typing bubble in view when it appears. Runs independently of
  // the message effect so paginating history never triggers a scroll.
  useEffect(() => {
    if (!peerTyping) return;
    const t = setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 50);
    return () => clearTimeout(t);
  }, [peerTyping]);

  async function onSend() {
    if (!session || !peerId || !text.trim() || sending) return;
    if (!online) {
      setSendError('You are offline. Reconnect to send messages.');
      return;
    }
    setSending(true);
    setSendError('');
    const outgoing = text.trim();
    // Optimistic bubble: the message appears instantly (Instagram-style) and
    // the server row replaces it on refresh. Temp ids are negative so they
    // can never collide with real ids and sort after existing messages.
    const optimisticId = tempId.current--;
    const optimistic: ChatMessage = {
      child_message_id: optimisticId,
      sender_child_id: ownId,
      message_text: outgoing,
      message_type: 'TEXT',
      // Fail-closed: render the optimistic bubble in the pending style until
      // the server row replaces it, so an unmoderated message never looks
      // approved (brief "waiting" flash on fast ALLOWED sends is intended).
      moderation_status: 'REVIEW',
      sent_at: new Date().toISOString(),
    };
    setMessages((prev) => dedupeChat([...prev, optimistic]));
    setText('');
    setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 50);
    try {
      const res = await sendChatText(session.token, peerId, outgoing);
      // Always refresh: the server returns own REVIEW messages to the sender
      // so they render in the pending state below instead of vanishing.
      // The refresh also swaps the optimistic bubble for the real row.
      await load('refresh');
      if (res.status === 'REVIEW') {
        setInfo('Your message is waiting for a safety check. Only you can see it for now.');
      } else {
        setInfo('');
      }
    } catch (err) {
      // Drop the optimistic bubble and restore the text so the child can
      // retry; do not leave a phantom message in the thread.
      setMessages((prev) => prev.filter((m) => m.child_message_id !== optimisticId));
      setText(outgoing);
      setSendError(err instanceof ApiError && err.code.includes('blocked') ? CHAT_BLOCKED_COPY : 'Could not send. Tap Retry to try again.');
    } finally {
      setSending(false);
    }
  }

  async function sendPhoto(source: 'gallery' | 'camera') {
    if (!session || !peerId || mediaSending || sending) return;
    if (!online) {
      setSendError('You are offline. Reconnect to send a photo.');
      return;
    }
    setMediaSending(true);
    setSendError('');
    setInfo('Preparing your photo for a safety check…');
    try {
      const picked = source === 'camera'
        ? await capturePostMedia('image')
        : await pickGalleryMedia('image');
      if (!picked) {
        setInfo('');
        return;
      }
      validateMediaIdentity(picked.fileName, picked.mimeType);
      const sizeBytes = picked.fileSize && picked.fileSize > 0
        ? picked.fileSize
        : localMediaSize(picked.uri);
      const upload = await requestChatImageUpload(session.token, peerId, {
        filename: picked.fileName,
        sizeBytes,
        mimeType: picked.mimeType,
      });
      setInfo('Uploading privately for safety review…');
      await putFileToSignedUrl(upload.upload_url, picked.uri, upload.required_headers);
      setInfo('Checking your photo before it enters the chat…');
      const result = await completeChatImageUpload(session.token, upload.upload_id);
      await load('refresh');
      if (result.status === 'REVIEW') {
        setInfo('Your photo is waiting for a safety check. Only you can see it for now.');
      } else {
        setInfo('');
      }
    } catch (err) {
      setInfo('');
      setSendError(
        err instanceof ApiError && (err.code.includes('blocked') || err.code.includes('image_blocked'))
          ? 'That photo cannot be shared here because it did not pass the safety check.'
          : err instanceof ApiError
            ? err.message
            : 'Could not send that photo. Try again.',
      );
    } finally {
      setMediaSending(false);
    }
  }

  function choosePhotoSource() {
    if (mediaSending || sending || !online) return;
    Alert.alert(
      'Send a photo',
      'Photos stay private and are safety-checked before your friend can see them.',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Photo library', onPress: () => void sendPhoto('gallery') },
        { text: 'Camera', onPress: () => void sendPhoto('camera') },
      ],
    );
  }

  useEffect(() => {
    if (session && peerId && postId) {
      sharePostToChat(session.token, peerId, postId)
        .then(() => {
          setShareNotice('Post sent to this chat.');
          void load('refresh');
        })
        .catch((err: unknown) => {
          setShareNotice(err instanceof ApiError ? err.message : 'Could not share that post here.');
        });
    }
    // Share once per screen mount: postId is fixed for this route instance.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.token, peerId, postId]);

  // Missing/invalid param (e.g. deep-link tampering): never hang on the
  // loading spinner — show a recoverable state with a way back.
  if (!peerId) {
    return (
      <Screen>
        <EmptyState
          title="Chat unavailable"
          body="We couldn't open this conversation because it is missing its details. Go back and choose it again."
        />
        <Button label="Back" variant="secondary" onPress={() => nav.goBack()} />
      </Screen>
    );
  }
  if (loading) return <Screen><LoadingState message="Loading chat…" /></Screen>;
  if (error instanceof ApiError && error.code === 'disabled_by_parent') return <Screen><DisabledFeature feature="Messages" /></Screen>;
  if (error instanceof ApiError && error.status === 403) {
    return (
      <Screen>
        <EmptyState
          title="Chat unavailable"
          body="You can message after both families approve this friendship. If the friendship was removed, this chat is closed."
        />
        <Button label="Back" variant="secondary" onPress={() => nav.goBack()} />
      </Screen>
    );
  }
  if (error && !messages.length) return <Screen><GateNotice error={error} /><ErrorState message="Could not load this chat." onRetry={() => void load('first')} /></Screen>;

  const peerName = String(peer.full_name ?? peer.username ?? 'Chat');
  const peerInitial = (peerName.trim().charAt(0) || '?').toUpperCase();

  return (
    <Screen>
      {/* Android uses softwareKeyboardLayoutMode="resize" (see app.json), so
          the window already shrinks for the keyboard — a padding-mode
          KeyboardAvoidingView would double-offset the input. iOS keeps it. */}
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}
        style={styles.keyboardWrap}
      >
        <View style={styles.peerRow}>
          <View style={styles.avatar}>
            <Text style={styles.avatarText}>{peerInitial}</Text>
          </View>
          <View style={styles.peerCol}>
            <Text style={styles.peer}>{peerName}</Text>
          </View>
          <Button label="Details" variant="secondary" onPress={() => nav.navigate('ChatDetails', { peerId })} />
        </View>
        {!online ? <OfflineBanner online={online} /> : null}
        {error ? <GateNotice error={error} /> : null}
        {info ? <Notice tone="info" message={info} /> : null}
        {shareNotice ? <Notice tone="info" message={shareNotice} /> : null}
        {sendError ? (
          <View style={styles.sendErrorRow}>
            <Notice message={sendError} />
            {text.trim() ? <Button label="Retry" onPress={() => void onSend()} /> : null}
          </View>
        ) : null}

        <FlatList
          ref={flatListRef}
          data={rows}
          keyExtractor={(r) => r.key}
          keyboardDismissMode="on-drag"
          keyboardShouldPersistTaps="handled"
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void load('refresh')} />}
          ListEmptyComponent={<EmptyState title="Say hello kindly" body="Messages appear here in order." />}
          onEndReached={() => {
            const oldest = messages[0]?.child_message_id;
            if (oldest && hasMore && !loadingMore) void load('more', oldest);
          }}
          onEndReachedThreshold={0.4}
          ListFooterComponent={loadingMore ? <Text style={styles.moreLoading}>Loading older messages…</Text> : null}
          contentContainerStyle={styles.listContent}
          renderItem={({ item }) => {
            if (item.kind === 'day') {
              return (
                <View style={styles.dayDivider}>
                  <Text style={styles.dayLabel}>{item.label}</Text>
                </View>
              );
            }
            if (item.kind === 'typing') {
              return (
                <View style={styles.row}>
                  <TypingDots />
                </View>
              );
            }
            const m = item.message;
            const isOwn = ownId !== 0 && m.sender_child_id === ownId;
            const pending = isChatMessagePending(m, isOwn);
            const showTime = showTimeFor === m.child_message_id;
            // The bubble itself, without the timestamp-toggle wrapper: shared
            // posts already contain their own "View shared post" button, so
            // they must not be nested inside another button for screen readers.
            const bubble = (
              <View style={[styles.bubble, isOwn ? styles.bubbleOwn : styles.bubblePeer]}>
                {m.message_type === 'SHARED_POST' ? (
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel="View shared post"
                    onPress={() => {
                      if (m.shared_post_id) nav.navigate('PostDetail', { postId: m.shared_post_id });
                    }}
                  >
                    <View style={styles.sharedCard}>
                      <Feather name="image" size={16} color={isOwn ? '#FFFFFF' : colors.brand} />
                      <Text style={[styles.msg, isOwn && styles.msgOwn, styles.sharedText]}>
                        Shared a post — tap to view
                      </Text>
                    </View>
                  </Pressable>
                ) : m.message_type === 'IMAGE' ? (
                  m.media_url ? (
                    <Image
                      source={{ uri: m.media_url }}
                      style={styles.messageImage}
                      resizeMode="cover"
                      accessibilityLabel={pending ? 'Photo waiting for safety review' : 'Photo message'}
                    />
                  ) : (
                    <View style={styles.imageUnavailable}>
                      <Feather name="image" size={22} color={isOwn ? '#FFFFFF' : colors.muted} />
                      <Text style={[styles.msg, isOwn && styles.msgOwn, pending && styles.pendingMsg]}>
                        {pending ? 'Photo waiting for safety check' : 'Photo unavailable'}
                      </Text>
                    </View>
                  )
                ) : (
                  <Text style={[styles.msg, isOwn && styles.msgOwn, pending && styles.pendingMsg]}>
                    {m.message_text}
                  </Text>
                )}
              </View>
            );
            return (
              <View style={[styles.row, isOwn && styles.rowOwn]}>
                {m.message_type === 'SHARED_POST' ? (
                  bubble
                ) : (
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel={showTime ? 'Hide message time' : 'Show message time'}
                    onPress={() => setShowTimeFor(showTime ? null : m.child_message_id)}
                  >
                    {bubble}
                  </Pressable>
                )}
                {showTime ? <Text style={[styles.timeLabel, isOwn && styles.timeLabelOwn]}>{timeLabel(m.sent_at)}</Text> : null}
                {pending ? (
                  <View style={styles.pendingBadge}>
                    <Feather name="clock" size={11} color="#B45309" />
                    <Text style={styles.pendingText}>Waiting for safety check</Text>
                  </View>
                ) : null}
                {!pending && isOwn && seenMessageId === m.child_message_id ? (
                  <Text style={styles.seenLabel}>Seen</Text>
                ) : null}
              </View>
            );
          }}
        />
        <View style={styles.inputRow}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Send a photo"
            accessibilityState={{ disabled: mediaSending || sending || !online }}
            disabled={mediaSending || sending || !online}
            onPress={choosePhotoSource}
            style={[styles.mediaButton, (mediaSending || sending || !online) && styles.sendButtonDisabled]}
          >
            <Feather name={mediaSending ? 'loader' : 'camera'} size={18} color={colors.brand} />
          </Pressable>
          <TextInput
            style={styles.chatInput}
            value={text}
            onChangeText={onChangeText}
            placeholder="Message…"
            placeholderTextColor={colors.muted}
            multiline={false}
            returnKeyType="send"
            onSubmitEditing={() => void onSend()}
            onFocus={() => {
              setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 100);
            }}
          />
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Send message"
            style={[styles.sendButton, (!text.trim() || sending || !online) && styles.sendButtonDisabled]}
            disabled={sending || !text.trim() || !online}
            onPress={() => void onSend()}
          >
            <Feather name="send" size={17} color="#FFFFFF" />
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  peerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 12,
    paddingVertical: 8,
    backgroundColor: colors.surface,
    borderBottomWidth: 1,
    borderBottomColor: '#EFEFEF',
  },
  avatar: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: colors.brand,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 10,
  },
  avatarText: { color: '#FFFFFF', fontWeight: '800', fontSize: 16 },
  peer: { flex: 1, fontWeight: '800', color: colors.ink, fontSize: 17 },
  peerCol: { flex: 1 },
  keyboardWrap: { flex: 1 },
  listContent: { paddingHorizontal: 12, paddingBottom: 16, paddingTop: 8, flexGrow: 1 },
  dayDivider: {
    alignSelf: 'center',
    backgroundColor: '#EFEFEF',
    borderRadius: radius.pill,
    paddingHorizontal: 12,
    paddingVertical: 5,
    marginVertical: 10,
  },
  dayLabel: {
    fontSize: 12,
    color: colors.muted,
    fontWeight: '700',
  },
  row: {
    alignItems: 'flex-start',
    marginVertical: 2,
  },
  rowOwn: {
    alignItems: 'flex-end',
  },
  bubble: {
    maxWidth: '75%',
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 18,
  },
  bubblePeer: {
    backgroundColor: '#EFEFEF',
    borderBottomLeftRadius: 4,
  },
  bubbleOwn: {
    backgroundColor: colors.brand,
    borderBottomRightRadius: 4,
  },
  msg: {
    color: '#262626',
    fontSize: 14,
    fontWeight: '400',
    lineHeight: 20,
  },
  msgOwn: {
    color: '#FFFFFF',
  },
  pendingMsg: { color: colors.muted, fontStyle: 'italic' },
  timeLabel: { fontSize: 11, color: colors.muted, marginTop: 3, marginLeft: 4 },
  timeLabelOwn: { marginLeft: 0, marginRight: 4 },
  seenLabel: { fontSize: 11, color: colors.muted, marginTop: 3, marginRight: 4, fontWeight: '600' },
  sharedCard: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  sharedText: { textDecorationLine: 'underline' },
  messageImage: { width: 220, height: 220, borderRadius: 14, backgroundColor: '#D8D8D8' },
  imageUnavailable: { width: 190, minHeight: 88, alignItems: 'center', justifyContent: 'center', gap: 8 },
  typingBubble: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    backgroundColor: '#EFEFEF',
    borderRadius: 18,
    borderBottomLeftRadius: 4,
    paddingHorizontal: 14,
    paddingVertical: 13,
  },
  typingDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: '#8E8E8E' },
  pendingBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: '#FEF3C7',
    borderRadius: 10,
    paddingHorizontal: 8,
    paddingVertical: 3,
    marginTop: 4,
  },
  pendingText: { color: '#B45309', fontSize: 11, fontWeight: '700' },
  moreLoading: { textAlign: 'center', color: colors.muted, paddingVertical: 12, fontSize: 12 },
  sendErrorRow: { paddingHorizontal: 12, paddingTop: 4 },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    backgroundColor: colors.surface,
    borderTopWidth: 1,
    borderTopColor: '#EFEFEF',
  },
  mediaButton: {
    width: 42,
    height: 42,
    borderRadius: 21,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#EEF2FF',
  },
  chatInput: {
    flex: 1,
    backgroundColor: '#EFEFEF',
    borderRadius: 24,
    paddingHorizontal: 16,
    paddingVertical: 10,
    fontSize: 14,
    color: colors.ink,
  },
  sendButton: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.brand,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendButtonDisabled: {
    opacity: 0.5,
  },
});
