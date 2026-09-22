import { useEffect, useState } from 'react';
import { Alert, Image, Modal, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { addComment, blockUser, deletePost, fetchConnections, fetchPostDetail, muteUser, submitReport, toggleLike, toggleSave, type CommentItem, type PostDetail } from '../../api/kidsSocial';
import { sharePostToChat } from '../../api/kidsChat';
import { useAuth } from '../../auth/AuthProvider';
import { VideoMedia } from '../../kids/VideoMedia';
import type { ChildScreenProps } from '../../navigation/types';
import { invalidateSocialCaches } from '../../query/keys';
import { Avatar } from '../../ui/social';
import { Button, Card, EmptyState, Field, GateNotice, LoadingState, Notice, Screen } from '../../ui/components';
import { colors } from '../../ui/tokens';

export function PostDetailScreen({ route, navigation }: ChildScreenProps<'PostDetail'>) {
  const { session } = useAuth();
  const postId = Number((route.params as { postId?: number } | undefined)?.postId ?? 0);
  const [post, setPost] = useState<PostDetail | null>(null);
  const [comments, setComments] = useState<CommentItem[]>([]);
  const [text, setText] = useState('');
  const [info, setInfo] = useState('');
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [likeBusy, setLikeBusy] = useState(false);
  const [safetyOpen, setSafetyOpen] = useState(false);
  const [safetyBusy, setSafetyBusy] = useState(false);
  const [safetyError, setSafetyError] = useState('');
  const [hidden, setHidden] = useState(false);
  const [reason, setReason] = useState('');
  const [shareOpen, setShareOpen] = useState(false);
  const [shareError, setShareError] = useState('');
  const [recipients, setRecipients] = useState<Array<{ user_id?: number; child_id?: number; full_name?: string; username?: string; avatar_url?: string | null }>>([]);
  const [sharing, setSharing] = useState<number | null>(null);
  const nav = navigation as unknown as { goBack: () => void };
  const reasons = ['Unsafe or unkind', 'Personal information', 'Something else'];
  const ownPost = Boolean(session?.user.user_id && post?.child_id === session.user.user_id);

  function confirmDelete() {
    if (!session || !post || !ownPost || busy) return;
    Alert.alert(
      'Delete this post?',
      'It will be removed from Feed, Reels, profiles, saved items, comments, and private media storage.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: () => {
            setBusy(true);
            void deletePost(session.token, postId)
              .then(async () => {
                await invalidateSocialCaches([postId]);
                nav.goBack();
              })
              .catch(setError)
              .finally(() => setBusy(false));
          },
        },
      ],
    );
  }

  async function load() {
    if (!session || !postId) return;
    try {
      const res = await fetchPostDetail(session.token, postId);
      setPost(res.post);
      setComments(res.comments ?? []);
      setError(null);
    } catch (err) {
      setError(err);
    }
  }

  useEffect(() => { void load(); }, [session?.token, postId]);
  // Missing/invalid param (e.g. deep-link tampering): never hang on the
  // loading spinner — show a recoverable state with a way back.
  if (!postId) {
    return (
      <Screen>
        <EmptyState
          title="Post unavailable"
          body="We couldn't open this post because it is missing its details. Go back and choose it again."
        />
        <Button label="Back" variant="secondary" onPress={() => nav.goBack()} />
      </Screen>
    );
  }
  if (!post) return <Screen><LoadingState message="Loading post…" /></Screen>;
  if (hidden) return <Screen><Notice tone="ok" message="This post is hidden on this device." /><Button label="Back to post" variant="secondary" onPress={() => setHidden(false)} /></Screen>;

  async function onLike() {
    if (!session || !post || likeBusy) return;
    // Optimistic: the server returns the authoritative liked/likes pair.
    const previous = post;
    const optimisticLiked = !post.viewer_liked;
    const optimisticLikes = (post.likes ?? 0) + (post.viewer_liked ? -1 : 1);
    setLikeBusy(true);
    setPost({ ...post, viewer_liked: optimisticLiked, likes: optimisticLikes });
    try {
      const res = await toggleLike(session.token, postId);
      setPost((current) => (current ? { ...current, viewer_liked: res.liked, likes: res.likes } : current));
      await invalidateSocialCaches([postId]);
    } catch (err) {
      // Roll back on failure so the UI never lies about the server state.
      setPost(previous);
      setError(err);
    } finally {
      setLikeBusy(false);
    }
  }

  async function onComment() {
    if (!session || !text.trim()) return;
    setBusy(true);
    setInfo('');
    try {
      const res = await addComment(session.token, postId, text.trim());
      setText('');
      if (res.status === 'REVIEW') setInfo('Your comment is waiting for a safety check.');
      else await load();
      await invalidateSocialCaches([postId]);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function safetyAction(action: 'report' | 'block' | 'mute') {
    const creatorId = post?.child_id;
    if (!session || !creatorId) return;
    if (action === 'report' && !reason) {
      setSafetyError('Choose a report reason before sending.');
      return;
    }
    setSafetyBusy(true);
    setSafetyError('');
    try {
      if (action === 'report') await submitReport(session.token, 'POST', postId, reason);
      if (action === 'block') await blockUser(session.token, creatorId, 'BLOCK');
      if (action === 'mute') await muteUser(session.token, creatorId, 'MUTE');
      await invalidateSocialCaches([postId]);
      setSafetyOpen(false);
      if (action === 'block') {
        // Blocked creators disappear from every surface; leave the detail
        // screen so stale blocked content is never shown.
        nav.goBack();
        return;
      }
      setInfo(action === 'report' ? 'Report sent for safety review.' : 'Creator muted. Their posts will not appear in your feed.');
    } catch (err) {
      setSafetyError(err instanceof Error ? err.message : 'Safety action failed. Try again.');
    } finally {
      setSafetyBusy(false);
    }
  }

  async function openShare() {
    if (!session) return;
    setShareError('');
    try {
      const res = await fetchConnections(session.token);
      const all = [...res.followers, ...res.following] as typeof recipients;
      setRecipients(all.filter((p, i, list) => Number(p.user_id ?? p.child_id) && list.findIndex((x) => Number(x.user_id ?? x.child_id) === Number(p.user_id ?? p.child_id)) === i));
      setShareOpen(true);
    } catch (err) { setShareError(err instanceof Error ? err.message : 'Could not load friends.'); }
  }

  return (
    <Screen>
      <ScrollView>
        <Card>
          <View style={styles.row}>
            <Avatar uri={post.avatar_url} name={post.full_name} />
            <Text style={styles.name}>{post.full_name ?? 'Friend'}</Text>
          </View>
          {post.caption ? <Text style={styles.caption}>{post.caption}</Text> : null}
          {post.media_url && post.media_type?.toUpperCase() === 'VIDEO' ? <VideoMedia source={post.media_url} posterUrl={post.poster_url} height={320} /> : null}
          {post.media_url && post.media_type?.toUpperCase() !== 'VIDEO' ? <Image source={{ uri: post.media_url }} style={styles.media} /> : null}
          <View style={styles.row}>
            <Button label={post.viewer_liked ? 'Liked' : 'Like'} disabled={likeBusy} onPress={() => void onLike()} />
            <Button label={post.viewer_saved ? 'Saved' : 'Save'} variant="secondary" onPress={() => {
              if (!session) return;
              toggleSave(session.token, postId).then((r) => {
                setPost({ ...post, viewer_saved: r.saved });
                void invalidateSocialCaches([postId]);
              }).catch((err: unknown) => setError(err));
            }} />
            <Button label="Share" variant="secondary" onPress={() => void openShare()} />
          </View>
          <Button label="Safety actions" variant="secondary" onPress={() => { setSafetyOpen((value) => !value); setSafetyError(''); }} />
          {ownPost ? (
            <Button
              label={busy ? 'Deleting…' : 'Delete post'}
              variant="secondary"
              onPress={confirmDelete}
              disabled={busy}
            />
          ) : null}
        </Card>
        {safetyOpen ? <Card>
          <Text style={styles.safetyTitle}>What would you like to do?</Text>
          <Button label="Hide this post" variant="secondary" disabled={safetyBusy} onPress={() => { setHidden(true); setSafetyOpen(false); }} />
          <Button label="Block creator" variant="secondary" disabled={safetyBusy} onPress={() => void safetyAction('block')} />
          <Button label="Mute creator" variant="secondary" disabled={safetyBusy} onPress={() => void safetyAction('mute')} />
          <Text style={styles.reasonLabel}>Report reason</Text>
          {reasons.map((item) => <Button key={item} label={reason === item ? `Selected: ${item}` : item} variant={reason === item ? 'primary' : 'secondary'} disabled={safetyBusy} onPress={() => setReason(item)} />)}
          <Button label={safetyBusy ? 'Sending…' : 'Send report'} disabled={safetyBusy || !reason} onPress={() => void safetyAction('report')} />
          {safetyError ? <Notice message={safetyError} /> : null}
        </Card> : null}
        {error ? <GateNotice error={error} /> : null}
        {info ? <Notice tone="info" message={info} /> : null}
        <Card>
          <Field label="Add a kind comment" value={text} onChangeText={setText} multiline placeholder="Say something kind…" />
          <Button label={busy ? 'Sending…' : 'Comment'} disabled={busy || !text.trim()} onPress={() => void onComment()} />
        </Card>
        {comments.map((c) => (
          <Card key={c.comment_id}>
            <View style={styles.row}>
              <Avatar uri={c.avatar_url} name={c.full_name} size={28} />
              <Text style={styles.name}>{c.full_name ?? 'Friend'}</Text>
            </View>
            <Text style={styles.caption}>{c.comment_text}</Text>
          </Card>
        ))}
      </ScrollView>
      <Modal visible={shareOpen} transparent animationType="slide" onRequestClose={() => setShareOpen(false)}>
        <View style={styles.sheet}><Text style={styles.safetyTitle}>Send to a friend</Text><Text style={styles.sheetHint}>Only approved friends can receive posts.</Text>
          {shareError ? <Notice message={shareError} /> : null}
          {!recipients.length && !shareError ? <Text style={styles.sheetHint}>No approved friends yet.</Text> : recipients.map((person, index) => { const id = Number(person.user_id ?? person.child_id); return <Pressable key={`${id}-${index}`} style={styles.recipient} disabled={sharing !== null} onPress={() => { if (!session) return; setSharing(id); sharePostToChat(session.token, id, postId).then(() => { setInfo('Post sent.'); setShareOpen(false); }).catch((shareErr: unknown) => setShareError(shareErr instanceof Error ? shareErr.message : 'Could not share that post.')).finally(() => setSharing(null)); }}><Avatar uri={person.avatar_url} name={person.full_name ?? person.username ?? 'Friend'} size={36} /><Text style={styles.name}>{person.full_name ?? person.username ?? 'Friend'}</Text><Text style={styles.send}>{sharing === id ? 'Sending…' : 'Send'}</Text></Pressable>; })}
          <Button label="Cancel" variant="secondary" onPress={() => setShareOpen(false)} />
        </View>
      </Modal>
    </Screen>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 8 },
  name: { fontWeight: '800', color: colors.ink },
  caption: { marginTop: 8, color: colors.ink },
  media: { marginTop: 10, width: '100%', height: 320, borderRadius: 12, backgroundColor: colors.line },
  safetyTitle: { color: colors.ink, fontSize: 17, fontWeight: '700' },
  reasonLabel: { color: colors.muted, fontSize: 12, fontWeight: '700', marginTop: 12, marginBottom: 2 },
  sheet: { marginTop: 'auto', backgroundColor: colors.surface, padding: 20, borderTopLeftRadius: 18, borderTopRightRadius: 18, minHeight: 280 },
  sheetHint: { color: colors.muted, marginTop: 6 },
  recipient: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: colors.line },
  send: { marginLeft: 'auto', color: colors.brand, fontWeight: '800' },
});
