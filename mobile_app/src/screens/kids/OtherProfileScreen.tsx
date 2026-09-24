import { useEffect, useMemo, useState } from 'react';
import { Alert, Dimensions, Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Feather } from '@expo/vector-icons';
import { ApiError } from '../../api/client';
import { fetchOtherProfile } from '../../api/kidsProfiles';
import { blockUser, fetchConnectionRequests, muteUser, submitReport, toggleFollow, type PostDetail } from '../../api/kidsSocial';
import { useAuth } from '../../auth/AuthProvider';
import { canMessageRelationship } from '../../kids/social';
import type { ChildScreenProps } from '../../navigation/types';
import { invalidateSocialCaches } from '../../query/keys';
import { Avatar, StoryRing } from '../../ui/social';
import { Button, Card, EmptyState, ErrorState, GateNotice, LoadingState, Notice, Screen } from '../../ui/components';
import { colors, radius, spacing } from '../../ui/tokens';

const AVATAR = 80;
const STORY_RING = AVATAR + 12;
const GAP = 1.5;
const GRID_COLS = 3;
const cellSize = (Dimensions.get('window').width - GAP * (GRID_COLS - 1)) / GRID_COLS;

/** Defensively read story highlights from the profile record when present. */
function readStories(profile: Record<string, unknown> | null): Array<Record<string, unknown>> {
  const raw = profile?.['stories'];
  return Array.isArray(raw) ? (raw as Array<Record<string, unknown>>) : [];
}

export function OtherProfileScreen({ route, navigation }: ChildScreenProps<'OtherProfile'>) {
  const { session } = useAuth();
  const targetId = Number((route.params as { targetId?: number } | undefined)?.targetId ?? 0);
  const [profile, setProfile] = useState<Record<string, unknown> | null>(null);
  const [posts, setPosts] = useState<PostDetail[]>([]);
  const [counts, setCounts] = useState<Record<string, unknown>>({});
  const [rel, setRel] = useState({ connected: false, pending: false, can_message: false });
  // They sent us a follow request that is still awaiting approval (server
  // state). Drives the Instagram-style "Follow Back" button state.
  const [incomingRequest, setIncomingRequest] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [info, setInfo] = useState('');
  // After the viewer blocks this profile the backend hides it (404); keep a
  // local blocked state so the child can still unblock from here.
  const [blocked, setBlocked] = useState(false);
  const [muted, setMuted] = useState(false);
  const nav = navigation as unknown as { navigate: (r: string, p: object) => void; goBack: () => void };

  // Visual-only aggregates from already-fetched data.
  const totalLikes = useMemo(
    () => posts.reduce((sum, p) => sum + (typeof p.likes === 'number' ? p.likes : 0), 0),
    [posts],
  );
  const stories = readStories(profile);
  const hasUnviewedStories = stories.some((s) => !(s.viewed === true || s.seen === true));
  const openStory = (story?: Record<string, unknown>) => {
    const initialStoryId = Number(story?.post_id ?? story?.id ?? stories[0]?.post_id ?? stories[0]?.id ?? 0);
    nav.navigate('Stories', {
      ...(initialStoryId > 0 ? { initialStoryId } : {}),
      ...(targetId > 0 ? { initialChildId: targetId } : {}),
    });
  };

  async function load() {
    if (!session || !targetId) return;
    // Reset per-profile state first so a stale "Follow Back" from the
    // previously viewed profile never flashes while the refetch lands.
    setIncomingRequest(false);
    try {
      const res = await fetchOtherProfile(session.token, targetId);
      setProfile(res.profile);
      setPosts(res.posts ?? []);
      setCounts(res.counts ?? {});
      if (res.relationship) setRel(res.relationship);
      setError(null);
    } catch (err) {
      setError(err);
    }
    // Best-effort incoming-request check for the "Follow Back" state. A
    // failure here must never break the profile screen.
    try {
      const reqs = await fetchConnectionRequests(session.token);
      setIncomingRequest((reqs.incoming ?? []).some((r) => r.requester_id === targetId));
    } catch {
      setIncomingRequest(false);
    }
  }

  useEffect(() => { void load(); }, [session?.token, targetId]);

  async function act(fn: (t: string) => Promise<unknown>, done?: string) {
    if (!session) return;
    setBusy(true);
    setInfo('');
    try {
      await fn(session.token);
      await invalidateSocialCaches();
      if (done) setInfo(done);
      await load();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function onBlockToggle() {
    if (!session) return;
    setBusy(true);
    setInfo('');
    try {
      const res = await blockUser(session.token, targetId, blocked ? 'unblock' : 'block');
      await invalidateSocialCaches();
      if (res.blocked) {
        // Blocked profiles disappear from every surface; leave this screen so
        // stale profile data is never shown.
        setBlocked(true);
        setInfo('Blocked. Their posts and profile are hidden from you.');
      } else {
        setBlocked(false);
        setInfo('Unblocked.');
        await load();
      }
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function onMuteToggle() {
    if (!session) return;
    setBusy(true);
    setInfo('');
    try {
      const res = await muteUser(session.token, targetId, muted ? 'unmute' : 'mute');
      setMuted(res.muted);
      await invalidateSocialCaches();
      setInfo(res.muted ? 'Muted. Their posts will not appear in your feed.' : 'Unmuted.');
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  // Instagram-style follow states: Follow / Requested / Following / Follow Back.
  // "Follow Back" shows when they sent us a request but we have not connected
  // yet. Every follow still needs parent approval server-side.
  const followState: 'following' | 'requested' | 'followBack' | 'none' =
    rel.connected ? 'following' : rel.pending ? 'requested' : incomingRequest ? 'followBack' : 'none';
  const followLabel =
    followState === 'following' ? 'Following'
    : followState === 'requested' ? 'Requested'
    : followState === 'followBack' ? 'Follow Back'
    : 'Follow';
  const followIsPrimary = followState === 'none' || followState === 'followBack';
  const displayName = String(profile?.full_name ?? 'this account');

  async function onFollowPress() {
    if (!session || busy) return;
    const doToggle = async (done: string) => {
      setBusy(true);
      setInfo('');
      try {
        await toggleFollow(session.token, targetId);
        await invalidateSocialCaches();
        setInfo(done);
        await load();
      } catch (err) {
        setError(err);
      } finally {
        setBusy(false);
      }
    };
    if (followState === 'following') {
      // Instagram confirms before unfollowing; avoids accidental taps.
      Alert.alert('Unfollow', `Unfollow ${displayName}?`, [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Unfollow', style: 'destructive', onPress: () => void doToggle('Unfollowed.') },
      ]);
      return;
    }
    if (followState === 'requested') {
      await doToggle('Follow request cancelled.');
      return;
    }
    await doToggle('Request sent! A parent needs to approve it.');
  }

  if (blocked) {
    return (
      <Screen>
        <ScrollView>
          <Card>
            <Text style={styles.blockedTitle}>Blocked</Text>
            <Text style={styles.bio}>You blocked this account. Their posts, profile and messages are hidden.</Text>
            <View style={styles.safetyBtns}>
              <Pressable style={[styles.primaryBtn, busy && styles.btnDisabled]} disabled={busy} onPress={() => void onBlockToggle()}>
                <Text style={styles.primaryBtnText}>{busy ? 'Working…' : 'Unblock'}</Text>
              </Pressable>
              <Pressable style={styles.greyBtn} onPress={() => nav.goBack()}>
                <Text style={styles.greyBtnText}>Back</Text>
              </Pressable>
            </View>
            {info ? <Notice tone="info" message={info} /> : null}
            {error ? <GateNotice error={error} /> : null}
          </Card>
        </ScrollView>
      </Screen>
    );
  }

  if (error instanceof ApiError && error.status === 404) {
    return (
      <Screen>
        <EmptyState
          title="Profile unavailable"
          body="This profile cannot be shown. It may have been removed, or you may have blocked this account."
        />
        <Button label="Back" variant="secondary" onPress={() => nav.goBack()} />
      </Screen>
    );
  }
  if (error && !profile) return <Screen><GateNotice error={error} /><ErrorState message="Could not load this profile." onRetry={() => void load()} /></Screen>;
  if (!profile) return <Screen><LoadingState message="Loading profile…" /></Screen>;

  const avatar = (
    <Avatar
      uri={typeof profile.avatar_url === 'string' ? profile.avatar_url : null}
      name={String(profile.full_name ?? 'F')}
      size={AVATAR}
    />
  );

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
      {error ? <GateNotice error={error} /> : null}
      {info ? <Notice tone="info" message={info} /> : null}

      {/* Instagram-style profile header */}
      <View style={styles.header}>
        <View style={styles.headRow}>
          {stories.length > 0 ? (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={`Open ${String(profile.full_name ?? 'friend')}'s stories`}
              onPress={() => openStory(stories.find((s) => !(s.viewed === true || s.seen === true)) ?? stories[0])}
              hitSlop={8}
            >
              {hasUnviewedStories ? <StoryRing size={STORY_RING}>{avatar}</StoryRing> : avatar}
            </Pressable>
          ) : (
            avatar
          )}
          <View style={styles.statsRow}>
            <View style={styles.statItem}>
              <Text style={styles.statNum}>{Number(counts.posts ?? 0)}</Text>
              <Text style={styles.statLabel}>Posts</Text>
            </View>
            <View style={styles.statItem}>
              <Text style={styles.statNum}>{Number(counts.followers ?? 0)}</Text>
              <Text style={styles.statLabel}>Friends</Text>
            </View>
            <View style={styles.statItem}>
              <Text style={styles.statNum}>{totalLikes}</Text>
              <Text style={styles.statLabel}>Likes</Text>
            </View>
          </View>
        </View>

        <View style={styles.bioSection}>
          <Text style={styles.profileName}>{String(profile.full_name ?? 'Friend')}</Text>
          {typeof profile.bio === 'string' && profile.bio ? (
            <Text style={styles.bio}>{profile.bio}</Text>
          ) : null}
          <Text style={styles.rel}>
            {rel.connected
              ? 'Friends'
              : rel.pending
                ? 'Friend request sent — needs parent approval'
                : incomingRequest
                  ? 'They sent you a friend request — follow back to connect'
                  : 'Not connected yet'}
          </Text>
        </View>

        {/* Story highlights */}
        {stories.length > 0 ? (
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.highlights}>
            {stories.map((s, i) => {
              const label = typeof s.caption === 'string' && s.caption ? s.caption : 'Story';
              return (
                <Pressable
                  key={String(s.post_id ?? s.id ?? i)}
                  style={styles.highlight}
                  accessibilityRole="button"
                  accessibilityLabel={`Open story: ${label}`}
                  onPress={() => openStory(s)}
                  hitSlop={6}
                >
                  <StoryRing size={64} seen={s.viewed === true || s.seen === true}>
                    <Avatar
                      uri={typeof s.poster_url === 'string' ? s.poster_url : (typeof s.media_url === 'string' ? s.media_url : null)}
                      name={label}
                      size={52}
                    />
                  </StoryRing>
                </Pressable>
              );
            })}
          </ScrollView>
        ) : null}

        {/* Action buttons: Instagram order — follow action primary, message secondary */}
        <View style={styles.actionsRow}>
          <Pressable
            style={[followIsPrimary ? styles.primaryBtn : styles.greyBtn, busy && styles.btnDisabled]}
            disabled={busy}
            onPress={() => void onFollowPress()}
          >
            <Text style={followIsPrimary ? styles.primaryBtnText : styles.greyBtnText}>
              {busy ? 'Working…' : followLabel}
            </Text>
          </Pressable>
          <Pressable
            style={[styles.greyBtn, !canMessageRelationship(rel) && styles.btnDisabled]}
            disabled={!canMessageRelationship(rel)}
            onPress={() => nav.navigate('Chat', { peerId: targetId })}
          >
            <Text style={styles.greyBtnText}>Message</Text>
          </Pressable>
        </View>
        {!canMessageRelationship(rel) ? (
          <Text style={styles.rel}>Messaging is available after the friendship is approved.</Text>
        ) : null}

        {/* Safety actions */}
        <View style={styles.safetyBtns}>
          <Pressable style={[styles.smallGreyBtn, busy && styles.btnDisabled]} disabled={busy} onPress={() => void onMuteToggle()}>
            <Text style={styles.smallGreyBtnText}>{muted ? 'Unmute' : 'Mute'}</Text>
          </Pressable>
          <Pressable style={[styles.smallGreyBtn, busy && styles.btnDisabled]} disabled={busy} onPress={() => void onBlockToggle()}>
            <Text style={styles.smallGreyBtnText}>Block</Text>
          </Pressable>
          <Pressable
            style={[styles.smallGreyBtn, busy && styles.btnDisabled]}
            disabled={busy}
            onPress={() => void act((t) => submitReport(t, 'USER', targetId, 'Unsafe behavior'), 'Report sent for safety review.')}
          >
            <Text style={[styles.smallGreyBtnText, styles.reportText]}>Report</Text>
          </Pressable>
        </View>
      </View>

      {/* Tab switcher: single grid tab */}
      <View style={styles.tabBar}>
        <View style={[styles.tabItem, styles.tabItemActive]}>
          <Feather name="grid" size={22} color={colors.ink} />
        </View>
      </View>

      {/* 3-column square media grid */}
      {posts.length > 0 ? (
        <View style={styles.grid}>
          {posts.map((p) => {
            const isVid = String(p.media_type ?? '').toUpperCase() === 'VIDEO';
            const imgUrl = isVid ? p.poster_url || p.media_url : p.media_url;
            return (
              <Pressable
                key={p.post_id}
                style={styles.gridCell}
                onPress={() => nav.navigate('PostDetail', { postId: p.post_id })}
              >
                {imgUrl ? (
                  <Image source={{ uri: imgUrl }} style={styles.gridThumb} resizeMode="cover" />
                ) : (
                  <View style={styles.gridPlaceholder}>
                    <Feather name={isVid ? 'play' : 'image'} size={22} color={colors.muted} />
                  </View>
                )}
                {isVid ? (
                  <View style={styles.videoBadge}>
                    <Feather name="play" size={11} color="#FFFFFF" />
                  </View>
                ) : null}
              </Pressable>
            );
          })}
        </View>
      ) : (
        <View style={styles.noPosts}>
          <Text style={styles.rel}>No posts yet</Text>
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.surface,
  },
  scrollContent: {
    paddingBottom: 40,
  },
  header: {
    backgroundColor: colors.surface,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.lg,
    paddingBottom: spacing.md,
  },
  headRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 20,
  },
  statsRow: {
    flex: 1,
    flexDirection: 'row',
    justifyContent: 'space-around',
    alignItems: 'center',
  },
  statItem: {
    alignItems: 'center',
    minWidth: 64,
  },
  statNum: {
    fontSize: 17,
    fontWeight: '700',
    color: colors.ink,
  },
  statLabel: {
    fontSize: 13,
    color: colors.muted,
    marginTop: 2,
  },
  bioSection: {
    marginTop: 10,
  },
  profileName: {
    fontSize: 15,
    fontWeight: '800',
    color: colors.ink,
  },
  bio: {
    fontSize: 14,
    color: colors.ink,
    marginTop: 3,
    lineHeight: 19,
  },
  rel: {
    marginTop: 4,
    color: colors.muted,
    fontSize: 13,
  },
  highlights: {
    gap: spacing.md,
    paddingVertical: spacing.md,
  },
  highlight: {
    alignItems: 'center',
  },
  actionsRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 12,
  },
  primaryBtn: {
    flex: 1,
    backgroundColor: colors.brand,
    borderRadius: radius.sm,
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 8,
  },
  primaryBtnText: {
    fontSize: 14,
    fontWeight: '700',
    color: '#FFFFFF',
  },
  greyBtn: {
    flex: 1,
    backgroundColor: '#EFEFEF',
    borderRadius: radius.sm,
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 8,
  },
  greyBtnText: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.ink,
  },
  btnDisabled: {
    opacity: 0.5,
  },
  safetyBtns: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 10,
  },
  smallGreyBtn: {
    flex: 1,
    backgroundColor: '#EFEFEF',
    borderRadius: radius.sm,
    minHeight: 36,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 8,
  },
  smallGreyBtnText: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.ink,
  },
  reportText: {
    color: colors.danger,
  },
  tabBar: {
    flexDirection: 'row',
    backgroundColor: colors.surface,
    borderBottomWidth: 1,
    borderBottomColor: colors.line,
  },
  tabItem: {
    flex: 1,
    paddingVertical: 10,
    alignItems: 'center',
    borderBottomWidth: 1,
    borderBottomColor: 'transparent',
  },
  tabItemActive: {
    borderBottomColor: colors.ink,
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: GAP,
  },
  gridCell: {
    width: cellSize,
    height: cellSize,
    backgroundColor: '#F5F5F5',
    overflow: 'hidden',
  },
  gridThumb: {
    width: '100%',
    height: '100%',
  },
  gridPlaceholder: {
    width: '100%',
    height: '100%',
    justifyContent: 'center',
    alignItems: 'center',
  },
  videoBadge: {
    position: 'absolute',
    top: 6,
    right: 6,
    backgroundColor: 'rgba(0,0,0,0.55)',
    borderRadius: radius.pill,
    width: 22,
    height: 22,
    alignItems: 'center',
    justifyContent: 'center',
  },
  noPosts: {
    paddingVertical: 32,
    alignItems: 'center',
  },
  blockedTitle: {
    fontSize: 17,
    fontWeight: '800',
    color: colors.ink,
  },
});
