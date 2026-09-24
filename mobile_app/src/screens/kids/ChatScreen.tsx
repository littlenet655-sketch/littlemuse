import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Animated, FlatList, Image, Keyboard, KeyboardAvoidingView, Modal, Platform, Pressable, RefreshControl, StyleSheet, Text, TextInput, View } from 'react-native';
import { Feather } from '@expo/vector-icons';
import { useIsFocused } from '@react-navigation/native';
import { completeChatUpload, fetchChat, fetchChatUpdates, MESSAGE_REACTION_EMOJIS, reactToMessage, requestChatUploadSession, sendChatText, sendTyping, sharePostToChat, type ChatMessage } from '../../api/kidsChat';
import { ApiError } from '../../api/client';
import { useAuth } from '../../auth/AuthProvider';
import { CHAT_BLOCKED_COPY, dedupeChat, isChatMessagePending } from '../../kids/social';
import { putFileToSignedUrl } from '../../kids/directUpload';
import { localMediaSize, pickGalleryMedia, validateMediaIdentity } from '../../kids/postMedia';
import { VideoMedia } from '../../kids/VideoMedia';
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
  const [replyTo, setReplyTo] = useState<ChatMessage | null>(null);
  const [actionFor, setActionFor] = useState<number | null>(null);
  const [reactionBusy, setReactionBusy] = useState<number | null>(null);
  const [mediaUploading, setMediaUploading] = useState(false);
  const [mediaProgress, setMediaProgress] = useState(0);
  const [videoModalUri, setVideoModalUri] = useState<string | null>(null);
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
    const replying = replyTo;
    // Optimistic bubble: the message appears instantly (Instagram-style) and
    // the server row replaces it on refresh. Temp ids are negative so they
    // can never collide with real ids and sort after existing messages.
    const optimisticId = tempId.current--;
    const optimistic: ChatMessage = {
      child_message_id: optimisticId,
      sender_child_id: ownId,
      message_text: outgoing,
      message_type: 'TEXT',
      reply_to_message_id: replying?.child_message_id ?? null,
      reply_message_text: replying?.message_text ?? (replying?.message_type === 'SHARED_POST' ? 'Shared post' : null),
      reply_message_type: replying?.message_type ?? null,
      reply_sender_child_id: replying?.sender_child_id ?? null,
      // Fail-closed: render the optimistic bubble in the pending style until
      // the server row replaces it, so an unmoderated message never looks
      // approved (brief "waiting" flash on fast ALLOWED sends is intended).
      moderation_status: 'REVIEW',
      sent_at: new Date().toISOString(),
    };
    setMessages((prev) => dedupeChat([...prev, optimistic]));
    setText('');
    setReplyTo(null);
    setActionFor(null);
    setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 50);
    try {
      const res = await sendChatText(session.token, peerId, outgoing, replying?.child_message_id ?? null);
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
      setReplyTo(replying);
      setSendError(err instanceof ApiError && err.code.includes('blocked') ? CHAT_BLOCKED_COPY : 'Could not send. Tap Retry to try again.');
    } finally {
      setSending(false);
    }
  }

  async function toggleMessageReaction(message: ChatMessage, emoji: string) {
    if (!session || !peerId || message.child_message_id <= 0 || reactionBusy) return;
    setReactionBusy(message.child_message_id);
    try {
      const next = message.viewer_reaction === emoji ? '' : emoji;
      const result = await reactToMessage(session.token, peerId, message.child_message_id, next);
      setMessages((current) => current.map((item) => (
        item.child_message_id === message.child_message_id
          ? { ...item, reactions: result.reactions, viewer_reaction: result.viewer_reaction }
          : item
      )));
      setActionFor(null);
    } catch {
      setSendError('Could not update that reaction. Try again.');
    } finally {
      setReactionBusy(null);
    }
  }

  function startReply(message: ChatMessage) {
    if (message.child_message_id <= 0) return;
    setReplyTo(message);
    setActionFor(null);
    setTimeout(() => flatListRef.current?.scrollToEnd({ animated: true }), 50);
  }

  async function sendMedia(kind: 'image' | 'video') {
    if (!session || !peerId || mediaUploading || sending) return;
    if (!online) {
      setSendError('You are offline. Reconnect to send media.');
      return;
    }
    try {
      const picked = await pickGalleryMedia(kind);
      if (!picked) return;
      validateMediaIdentity(picked.fileName, picked.mimeType);
      const sizeBytes = picked.fileSize && picked.fileSize > 0 ? picked.fileSize : localMediaSize(picked.uri);
      const extension = picked.fileName.includes('.') ? picked.fileName.split('.').pop()?.toLowerCase() : undefined;

      setMediaUploading(true);
      setMediaProgress(0);
      setSendError('');
      setInfo('');

      const upload = await requestChatUploadSession(session.token, peerId, {
        mediaType: kind === 'image' ? 'IMAGE' : 'VIDEO',
        filename: picked.fileName,
        sizeBytes,
        mimeType: picked.mimeType,
        extension,
      });

      await putFileToSignedUrl(upload.upload_url, picked.uri, upload.required_headers, {
        onProgress: (sent, total) => {
          if (total > 0) setMediaProgress(Math.max(0, Math.min(1, sent / total)));
        },
      });

      const result = await completeChatUpload(session.token, peerId, upload.upload_id);
      await load('refresh');
      setInfo(
        result.status === 'REVIEW'
          ? 'Your media is waiting for a parent safety review. Only you can see it for now.'
          : 'Media sent safely.',
      );
    } catch (err) {
      setSendError(err instanceof ApiError && err.code.includes('blocked')
        ? 'That media could not be sent because it did not pass LittleMuse safety checks.'
        : err instanceof Error ? err.message : 'Could not send media. Try again.');
    } finally {
      setMediaUploading(false);
      setMediaProgress(0);
    }
  }

  function openAttachmentPicker() {
    if (mediaUploading || sending) return;
    Alert.alert(
      'Send media',
      'Photos and videos are safety-checked before your friend can see them.',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Photo', onPress: () => void sendMedia('image') },
        { text: 'Video', onPress: () => void sendMedia('video') },
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
            const reactionEntries = Object.entries(m.reactions ?? {}).filter(([, count]) => Number(count) > 0);
            const replyLabel = m.reply_message_text
              || (m.reply_message_type === 'SHARED_POST' ? 'Shared post' : m.reply_message_type ? String(m.reply_message_type).toLowerCase() : '');
            const bubble = (
              <View style={[styles.bubble, isOwn ? styles.bubbleOwn : styles.bubblePeer]}>
                {m.reply_to_message_id ? (
                  <View style={[styles.replyPreview, isOwn && styles.replyPreviewOwn]}>
                    <Feather name="corner-up-left" size={12} color={isOwn ? 'rgba(255,255,255,0.8)' : colors.muted} />
                    <Text style={[styles.replyPreviewText, isOwn && styles.replyPreviewTextOwn]} numberOfLines={2}>
                      {replyLabel || 'Original message'}
                    </Text>
                  </View>
                ) : null}
                {m.message_type === 'IMAGE' && m.media_url ? (
                  <Image
                    source={{ uri: m.media_url }}
                    style={styles.chatImage}
                    resizeMode="cover"
                    accessibilityLabel="Photo message"
                  />
                ) : m.message_type === 'VIDEO' && m.media_url ? (
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel="Play video message"
                    onPress={() => setVideoModalUri(m.media_url ?? null)}
                    style={styles.chatVideoCard}
                  >
                    <Feather name="play-circle" size={34} color={isOwn ? '#FFFFFF' : colors.brand} />
                    <Text style={[styles.msg, isOwn && styles.msgOwn]}>Video message · tap to play</Text>
                  </Pressable>
                ) : m.message_type === 'SHARED_POST' ? (
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
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel="Shared post message actions"
                    accessibilityHint="Long press for reply and reactions"
                    onLongPress={() => {
                      if (!pending && m.child_message_id > 0) setActionFor(actionFor === m.child_message_id ? null : m.child_message_id);
                    }}
                  >
                    {bubble}
                  </Pressable>
                ) : (
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel={showTime ? 'Hide message time' : 'Show message time'}
                    accessibilityHint="Long press for reply and reactions"
                    onPress={() => setShowTimeFor(showTime ? null : m.child_message_id)}
                    onLongPress={() => {
                      if (!pending && m.child_message_id > 0) setActionFor(actionFor === m.child_message_id ? null : m.child_message_id);
                    }}
                  >
                    {bubble}
                  </Pressable>
                )}
                {reactionEntries.length ? (
                  <View style={[styles.reactionSummary, isOwn && styles.reactionSummaryOwn]}>
                    {reactionEntries.map(([emoji, count]) => (
                      <Pressable
                        key={emoji}
                        accessibilityRole="button"
                        accessibilityLabel={`${emoji} reaction, ${count}`}
                        disabled={reactionBusy === m.child_message_id}
                        onPress={() => void toggleMessageReaction(m, emoji)}
                        style={[styles.reactionChip, m.viewer_reaction === emoji && styles.reactionChipActive]}
                      >
                        <Text style={styles.reactionChipText}>{emoji} {Number(count)}</Text>
                      </Pressable>
                    ))}
                  </View>
                ) : null}
                {actionFor === m.child_message_id ? (
                  <View style={[styles.messageActions, isOwn && styles.messageActionsOwn]}>
                    <Pressable
                      accessibilityRole="button"
                      accessibilityLabel="Reply to message"
                      onPress={() => startReply(m)}
                      style={styles.messageActionButton}
                    >
                      <Feather name="corner-up-left" size={15} color={colors.ink} />
                      <Text style={styles.messageActionText}>Reply</Text>
                    </Pressable>
                    {MESSAGE_REACTION_EMOJIS.map((emoji) => (
                      <Pressable
                        key={emoji}
                        accessibilityRole="button"
                        accessibilityLabel={`React ${emoji}`}
                        disabled={reactionBusy === m.child_message_id}
                        onPress={() => void toggleMessageReaction(m, emoji)}
                        style={styles.emojiAction}
                      >
                        <Text style={styles.emojiActionText}>{emoji}</Text>
                      </Pressable>
                    ))}
                  </View>
                ) : null}
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
        {mediaUploading ? (
          <View style={styles.mediaProgressRow}>
            <Feather name="shield" size={14} color={colors.brand} />
            <Text style={styles.mediaProgressText}>
              Uploading for safety check… {Math.round(mediaProgress * 100)}%
            </Text>
          </View>
        ) : null}

        {replyTo ? (
          <View style={styles.replyComposer}>
            <View style={{ flex: 1 }}>
              <Text style={styles.replyComposerTitle}>Replying to {replyTo.sender_child_id === ownId ? 'yourself' : peerName}</Text>
              <Text style={styles.replyComposerText} numberOfLines={1}>
                {replyTo.message_text || (replyTo.message_type === 'SHARED_POST' ? 'Shared post' : 'Message')}
              </Text>
            </View>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Cancel reply"
              hitSlop={8}
              onPress={() => setReplyTo(null)}
            >
              <Feather name="x" size={18} color={colors.muted} />
            </Pressable>
          </View>
        ) : null}
        <View style={styles.inputRow}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Attach photo or video"
            accessibilityState={{ disabled: mediaUploading || sending || !online }}
            disabled={mediaUploading || sending || !online}
            onPress={openAttachmentPicker}
            style={[styles.attachButton, (mediaUploading || sending || !online) && styles.sendButtonDisabled]}
          >
            <Feather name="plus" size={20} color={colors.brand} />
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
      <Modal
        visible={Boolean(videoModalUri)}
        animationType="fade"
        transparent
        onRequestClose={() => setVideoModalUri(null)}
      >
        <View style={styles.videoModalBackdrop}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Close video"
            onPress={() => setVideoModalUri(null)}
            style={styles.videoModalClose}
          >
            <Feather name="x" size={22} color="#FFFFFF" />
          </Pressable>
          {videoModalUri ? (
            <View style={styles.videoModalContent}>
              <VideoMedia source={videoModalUri} active height={420} nativeControls />
            </View>
          ) : null}
        </View>
      </Modal>
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
  replyPreview: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    borderLeftWidth: 3,
    borderLeftColor: '#A3A3A3',
    paddingLeft: 8,
    marginBottom: 7,
    maxWidth: 220,
  },
  replyPreviewOwn: { borderLeftColor: 'rgba(255,255,255,0.7)' },
  replyPreviewText: { flex: 1, color: colors.muted, fontSize: 12, fontWeight: '700' },
  replyPreviewTextOwn: { color: 'rgba(255,255,255,0.78)' },
  reactionSummary: { flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginTop: 3, marginLeft: 4 },
  reactionSummaryOwn: { justifyContent: 'flex-end', marginLeft: 0, marginRight: 4 },
  reactionChip: {
    backgroundColor: '#F3F4F6',
    borderWidth: 1,
    borderColor: '#E5E7EB',
    borderRadius: 999,
    paddingHorizontal: 7,
    paddingVertical: 3,
  },
  reactionChipActive: { borderColor: colors.brand, backgroundColor: '#EEF2FF' },
  reactionChipText: { fontSize: 12, color: colors.ink, fontWeight: '700' },
  messageActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginTop: 5,
    paddingHorizontal: 6,
    paddingVertical: 5,
    borderRadius: 999,
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#E5E7EB',
  },
  messageActionsOwn: { alignSelf: 'flex-end' },
  messageActionButton: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 6, paddingVertical: 4 },
  messageActionText: { color: colors.ink, fontSize: 12, fontWeight: '800' },
  emojiAction: { paddingHorizontal: 3, paddingVertical: 3 },
  emojiActionText: { fontSize: 18 },
  replyComposer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: 14,
    paddingVertical: 9,
    backgroundColor: '#F8FAFC',
    borderTopWidth: 1,
    borderTopColor: '#E5E7EB',
    borderLeftWidth: 3,
    borderLeftColor: colors.brand,
  },
  replyComposerTitle: { color: colors.brand, fontSize: 12, fontWeight: '800' },
  replyComposerText: { color: colors.muted, fontSize: 12, marginTop: 2 },
  chatImage: { width: 220, height: 220, borderRadius: 14, backgroundColor: '#E5E7EB' },
  chatVideoCard: {
    width: 220,
    minHeight: 120,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    backgroundColor: 'rgba(0,0,0,0.08)',
    padding: 14,
  },
  mediaProgressRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
    paddingHorizontal: 14,
    paddingVertical: 8,
    backgroundColor: '#EEF2FF',
    borderTopWidth: 1,
    borderTopColor: '#E0E7FF',
  },
  mediaProgressText: { color: colors.brand, fontSize: 12, fontWeight: '800' },
  attachButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#EEF2FF',
  },
  videoModalBackdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.92)',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 16,
  },
  videoModalClose: {
    position: 'absolute',
    top: 52,
    right: 20,
    zIndex: 4,
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: 'rgba(255,255,255,0.14)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  videoModalContent: { width: '100%', maxWidth: 560 },
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
