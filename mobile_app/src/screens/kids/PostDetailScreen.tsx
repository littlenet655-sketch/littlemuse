import { useEffect, useRef, useState } from 'react';
import { Alert, Image, Modal, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { addComment, blockUser, deleteComment, deletePost, fetchComments, fetchConnections, fetchPostDetail, muteUser, setPostCommentsEnabled, submitReport, toggleLike, toggleSave, type CommentItem, type PostDetail } from '../../api/kidsSocial';
import { sharePostToChat } from '../../api/kidsChat';
import { useAuth } from '../../auth/AuthProvider';
import { VideoMedia } from '../../kids/VideoMedia';
import type { ChildScreenProps } from '../../navigation/types';
import { invalidateSocialCaches } from '../../query/keys';
import { Avatar } from '../../ui/social';
import { Button, Card, EmptyState, Field, GateNotice, LoadingState, Notice, Screen, errorText } from '../../ui/components';
import { colors } from '../../ui/tokens';

export function PostDetailScreen({ route, navigation }: ChildScreenProps<'PostDetail'>) {
  const { session } = useAuth();
  const postId = Number((route.params as { postId?: number } | undefined)?.postId ?? 0);
  const [post, setPost] = useState<PostDetail | null>(null);
  const [comments, setComments] = useState<CommentItem[]>([]);
  const [commentsCursor, setCommentsCursor] = useState<number | null>(null);
  const [commentsHasMore, setCommentsHasMore] = useState(false);
  const [commentsLoadingMore, setCommentsLoadingMore] = useState(false);
  const [commentActionBusy, setCommentActionBusy] = useState<number | null>(null);
  const [commentError, setCommentError] = useState<unknown>(null);
  const [commentsSettingBusy, setCommentsSettingBusy] = useState(false);
  const [text, setText] = useState('');
  const [info, setInfo] = useState('');
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [likeBusy, setLikeBusy] = useState(false);
  const [safetyOpen, setSafetyOpen] = useState(false);
  const [safetyBusy, setSafetyBusy] = useState(false);
  const [safetyError, setSafetyError] = useState('');
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState('');
  const [hidden, setHidden] = useState(false);
  const [reason, setReason] = useState('');
  const [shareOpen, setShareOpen] = useState(false);
  const [shareError, setShareError] = useState('');
  const [recipients, setRecipients] = useState<Array<{ user_id?: number; child_id?: number; full_name?: string; username?: string; avatar_url?: string | null }>>([]);
  const [sharing, setSharing] = useState<number | null>(null);
  const requestedShareRef = useRef(false);
  const nav = navigation as unknown as { goBack: () => void };
  const reasons = ['Unsafe or unkind', 'Personal information', 'Something else'];

  async function load() {
    if (!session || !postId) return;
    try {
      const res = await fetchPostDetail(session.token, postId);
      setPost(res.post);
      setError(null);
      if (res.post.comments_enabled === false) {
        setComments([]);
        setCommentsCursor(null);
        setCommentsHasMore(false);
        setCommentError(null);
      } else {
        try {
          const page = await fetchComments(session.token, postId, null, 20);
          setComments(page.comments ?? []);
          setCommentsCursor(page.next_cursor ?? null);
          setCommentsHasMore(Boolean(page.has_more));
          if (page.comments_enabled === false) {
            setPost((current) => current ? { ...current, comments_enabled: false } : current);
          }
          setCommentError(null);
        } catch (commentErr) {
          setComments([]);
          setCommentsCursor(null);
          setCommentsHasMore(false);
          setCommentError(commentErr);
        }
      }
    } catch (err) {
      setError(err);
    }
  }

  useEffect(() => { void load(); }, [session?.token, postId]);

  useEffect(() => {
    const shouldOpenShare = Boolean((route.params as { openShare?: boolean } | undefined)?.openShare);
    if (!shouldOpenShare || !post || requestedShareRef.current) return;
    requestedShareRef.current = true;
    void openShare();
  }, [post, route.params, session?.token]);

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

  async function loadMoreComments() {
    if (!session || !commentsHasMore || !commentsCursor || commentsLoadingMore) return;
    setCommentsLoadingMore(true);
    try {
      const page = await fetchComments(session.token, postId, commentsCursor, 20);
      setComments((current) => {
        const byId = new Map(current.map((item) => [item.comment_id, item]));
        for (const item of page.comments ?? []) byId.set(item.comment_id, item);
        return [...byId.values()];
      });
      setCommentsCursor(page.next_cursor ?? null);
      setCommentsHasMore(Boolean(page.has_more));
      setCommentError(null);
    } catch (err) {
      setCommentError(err);
    } finally {
      setCommentsLoadingMore(false);
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

  async function removeComment(commentId: number) {
    if (!session || commentActionBusy) return;
    setCommentActionBusy(commentId);
    try {
      const res = await deleteComment(session.token, postId, commentId);
      setComments((current) => current.filter((item) => item.comment_id !== commentId));
      setPost((current) => current ? { ...current, comments_count: res.comments_count } : current);
      await invalidateSocialCaches([postId]);
      setInfo('Comment removed.');
    } catch (err) {
      setCommentError(err);
    } finally {
      setCommentActionBusy(null);
    }
  }

  async function commentSafetyAction(comment: CommentItem, action: 'report' | 'mute' | 'block') {
    if (!session || commentActionBusy || comment.child_id === session.user.user_id) return;
    setCommentActionBusy(comment.comment_id);
    try {
      if (action === 'report') {
        await submitReport(session.token, 'COMMENT', comment.comment_id, 'Unsafe or unkind');
        setInfo('Comment reported for safety review.');
      } else if (action === 'mute') {
        await muteUser(session.token, comment.child_id, 'MUTE');
        setComments((current) => current.filter((item) => item.child_id !== comment.child_id));
        setInfo('Commenter muted. Their content will be hidden from your surfaces.');
      } else {
        await blockUser(session.token, comment.child_id, 'BLOCK');
        setComments((current) => current.filter((item) => item.child_id !== comment.child_id));
        setInfo('Commenter blocked. Their profile, posts, messages, and comments are hidden.');
      }
      await invalidateSocialCaches([postId]);
      setCommentError(null);
    } catch (err) {
      setCommentError(err);
    } finally {
      setCommentActionBusy(null);
    }
  }

  function openCommentSafety(comment: CommentItem) {
    if (comment.child_id === session?.user.user_id) return;
    Alert.alert(
      comment.full_name ?? 'Comment safety',
      'Choose a safety action for this commenter.',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Report comment', onPress: () => void commentSafetyAction(comment, 'report') },
        { text: 'Mute account', onPress: () => void commentSafetyAction(comment, 'mute') },
        { text: 'Block account', style: 'destructive', onPress: () => void commentSafetyAction(comment, 'block') },
      ],
    );
  }

  async function toggleCommentsSetting() {
    if (!session || !post || commentsSettingBusy) return;
    setCommentsSettingBusy(true);
    try {
      const res = await setPostCommentsEnabled(session.token, postId, post.comments_enabled === false);
      setPost((current) => current ? { ...current, comments_enabled: res.comments_enabled } : current);
      setInfo(res.comments_enabled ? 'Comments are on for this post.' : 'Comments are off for this post.');
      setCommentError(null);
      if (res.comments_enabled) await load();
    } catch (err) {
      setCommentError(err);
    } finally {
      setCommentsSettingBusy(false);
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

  const isOwnPost = session?.user?.user_id != null && post?.child_id === session.user.user_id;
  const commentsBlockedByParent = (commentError as { code?: string } | null)?.code === 'disabled_by_parent';
  const commentsOpen = post?.comments_enabled !== false && !commentsBlockedByParent;

  function confirmDeletePost() {
    Alert.alert(
      'Delete this post?',
      'It will be removed for everyone and cannot be undone.',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Delete', style: 'destructive', onPress: () => void doDeletePost() },
      ],
    );
  }

  async function doDeletePost() {
    if (!session || !post || deleteBusy) return;
    const postId = post.post_id;
    setDeleteBusy(true);
    setDeleteError('');
    try {
      await deletePost(session.token, postId);
      await invalidateSocialCaches([postId]);
      nav.goBack();
    } catch (err) {
      setDeleteError(errorText(err));
    } finally {
      setDeleteBusy(false);
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
          {isOwnPost ? (
            <>
              <Button
                label={commentsSettingBusy ? 'Updating comments…' : post.comments_enabled === false ? 'Turn comments on' : 'Turn comments off'}
                variant="secondary"
                disabled={commentsSettingBusy}
                onPress={() => void toggleCommentsSetting()}
              />
              <Button
                label={deleteBusy ? 'Deleting…' : 'Delete this post'}
                variant="secondary"
                disabled={deleteBusy}
                onPress={confirmDeletePost}
              />
            </>
          ) : null}
          {deleteError ? <Notice message={deleteError} /> : null}
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
        {commentError && !commentsBlockedByParent ? <GateNotice error={commentError} /> : null}
        {commentsBlockedByParent ? (
          <Card>
            <Text style={styles.safetyTitle}>Comments are turned off by your parent</Text>
            <Text style={styles.sheetHint}>This setting is enforced by LittleMuse and cannot be changed from Kids Mode.</Text>
          </Card>
        ) : post.comments_enabled === false ? (
          <Card>
            <Text style={styles.safetyTitle}>Comments are off for this post</Text>
            <Text style={styles.sheetHint}>{isOwnPost ? 'You can turn them back on above if your parent allows comments.' : 'The post owner chose not to receive comments.'}</Text>
          </Card>
        ) : (
          <Card>
            <Field label="Add a kind comment" value={text} onChangeText={setText} multiline placeholder="Say something kind…" />
            <Button label={busy ? 'Sending…' : 'Comment'} disabled={busy || !text.trim() || !commentsOpen} onPress={() => void onComment()} />
          </Card>
        )}
        {commentsOpen ? comments.map((comment) => (
          <Card key={comment.comment_id}>
            <View style={styles.row}>
              <Avatar uri={comment.avatar_url} name={comment.full_name} size={28} />
              <Text style={styles.name}>{comment.full_name ?? 'Friend'}</Text>
            </View>
            <Text style={styles.caption}>{comment.comment_text}</Text>
            <View style={styles.row}>
              {comment.can_delete ? (
                <Button
                  label={commentActionBusy === comment.comment_id ? 'Removing…' : 'Delete'}
                  variant="secondary"
                  disabled={commentActionBusy !== null}
                  onPress={() => Alert.alert('Delete comment?', 'This comment will be removed.', [
                    { text: 'Cancel', style: 'cancel' },
                    { text: 'Delete', style: 'destructive', onPress: () => void removeComment(comment.comment_id) },
                  ])}
                />
              ) : null}
              {comment.child_id !== session?.user.user_id ? (
                <Button
                  label={commentActionBusy === comment.comment_id ? 'Working…' : 'Safety'}
                  variant="secondary"
                  disabled={commentActionBusy !== null}
                  onPress={() => openCommentSafety(comment)}
                />
              ) : null}
            </View>
          </Card>
        )) : null}
        {commentsOpen && commentsHasMore ? (
          <Button
            label={commentsLoadingMore ? 'Loading comments…' : 'Load more comments'}
            variant="secondary"
            disabled={commentsLoadingMore}
            onPress={() => void loadMoreComments()}
          />
        ) : null}
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
