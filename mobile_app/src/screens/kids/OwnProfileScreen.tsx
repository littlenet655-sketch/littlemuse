import { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Dimensions, Image, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Feather } from '@expo/vector-icons';
import { useQuery } from '@tanstack/react-query';
import { fetchOwnProfile, updateOwnProfile } from '../../api/kidsProfiles';
import { fetchSaved } from '../../api/kidsSocial';
import { useAuth } from '../../auth/AuthProvider';
import type { ChildScreenProps } from '../../navigation/types';
import { queryClient } from '../../query/client';
import { invalidateSocialCaches, kidsKeys } from '../../query/keys';
import { Avatar, StoryRing } from '../../ui/social';
import { Button, Card, EmptyState, ErrorState, Field, GateNotice, Notice, Screen } from '../../ui/components';
import { colors, radius, spacing } from '../../ui/tokens';

type Tab = 'posts' | 'reels' | 'saved' | 'edit';

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

export function OwnProfileScreen({ navigation }: ChildScreenProps<'KidsTabs'>) {
  const { session, signOut } = useAuth();
  const [tab, setTab] = useState<Tab>('posts');
  const [bio, setBio] = useState('');
  const [name, setName] = useState('');
  const [saving, setSaving] = useState(false);
  const [savedMsg, setSavedMsg] = useState('');
  const [saveError, setSaveError] = useState<unknown>(null);
  const nav = navigation as unknown as { navigate: (r: string, p: object) => void };
  const profileQuery = useQuery({
    queryKey: [...kidsKeys.ownProfile, session?.token ?? 'signed-out'],
    enabled: Boolean(session),
    queryFn: () => fetchOwnProfile(session!.token),
  });
  const savedQuery = useQuery({
    queryKey: [...kidsKeys.saved, session?.token ?? 'signed-out'],
    enabled: Boolean(session),
    queryFn: () => fetchSaved(session!.token),
  });
  const profile = profileQuery.data?.profile ?? null;
  const posts = profileQuery.data?.posts ?? [];
  const counts = profileQuery.data?.counts ?? {};
  const saved = [...(savedQuery.data?.posts ?? []), ...(savedQuery.data?.reels ?? [])];
  const error = profileQuery.error ?? savedQuery.error ?? saveError;
  const [refreshing, setRefreshing] = useState(false);

  // Instagram parity: reels live in their own tab, filtered client-side from the
  // already-fetched profile posts. No API change.
  const reels = useMemo(
    () => posts.filter((p) => p.media_type?.toUpperCase() === 'VIDEO'),
    [posts],
  );

  const onRefresh = () => {
    setRefreshing(true);
    Promise.allSettled([profileQuery.refetch(), savedQuery.refetch()]).finally(() =>
      setRefreshing(false),
    );
  };

  // Visual-only aggregates from already-fetched data.
  const totalLikes = useMemo(
    () => posts.reduce((sum, p) => sum + (typeof p.likes === 'number' ? p.likes : 0), 0),
    [posts],
  );
  const stories = readStories(profile);
  const hasUnviewedStories = stories.some((s) => !(s.viewed === true || s.seen === true));

  useEffect(() => {
    if (!profile) return;
    setBio(String(profile.bio ?? ''));
    setName(String(profile.full_name ?? ''));
  }, [profile]);

  if (profileQuery.isPending && !profile) {
    return (
      <View style={styles.centerLoading}>
        <ActivityIndicator size="large" color={colors.brand} />
      </View>
    );
  }
  if (profileQuery.error && !profile) return <Screen><GateNotice error={profileQuery.error} /><ErrorState message="Could not load your profile." onRetry={() => void profileQuery.refetch()} /></Screen>;

  const list = tab === 'saved' ? saved : tab === 'reels' ? reels : posts;

  const emptyCopy: Record<Exclude<Tab, 'edit'>, { icon: 'image' | 'film' | 'bookmark'; title: string; body: string }> = {
    posts: {
      icon: 'image',
      title: 'No posts yet',
      body: 'Share safe moments with friends using the + button!',
    },
    reels: {
      icon: 'film',
      title: 'No reels yet',
      body: 'Video posts you share will appear here.',
    },
    saved: {
      icon: 'bookmark',
      title: 'No saved posts yet',
      body: 'Posts and reels you bookmark will appear here.',
    },
  };

  const avatar = (
    <Avatar
      uri={typeof profile?.avatar_url === 'string' ? profile.avatar_url : null}
      name={String(profile?.full_name ?? 'Kid')}
      size={AVATAR}
    />
  );

  return (
    <View style={styles.container}>
      <ScrollView
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            colors={[colors.brand]}
            tintColor={colors.brand}
          />
        }
      >
        {error ? <GateNotice error={error} /> : null}

        {/* Instagram-style profile header */}
        <View style={styles.header}>
          <View style={styles.headRow}>
            {hasUnviewedStories ? (
              <StoryRing size={STORY_RING}>{avatar}</StoryRing>
            ) : (
              avatar
            )}
            <View style={styles.statsRow}>
              <View style={styles.statItem}>
                <Text style={styles.statNum}>{posts.length}</Text>
                <Text style={styles.statLabel}>Posts</Text>
              </View>
              <Pressable
                style={styles.statItem}
                accessibilityRole="button"
                accessibilityLabel="View friends"
                onPress={() => nav.navigate('Connections', { mode: 'followers' })}
              >
                <Text style={styles.statNum}>{Number(counts.followers ?? 0)}</Text>
                <Text style={styles.statLabel}>Friends</Text>
              </Pressable>
              <View style={styles.statItem}>
                <Text style={styles.statNum}>{totalLikes}</Text>
                <Text style={styles.statLabel}>Likes</Text>
              </View>
            </View>
          </View>

          <View style={styles.bioSection}>
            <Text style={styles.profileName}>{String(profile?.full_name || 'LittleNet Explorer')}</Text>
            {typeof profile?.bio === 'string' && profile.bio ? (
              <Text style={styles.bioText}>{profile.bio}</Text>
            ) : (
              <Text style={styles.bioPlaceholder}>Learning, sharing kindness, and exploring safely ✨</Text>
            )}
          </View>

          {/* Story highlights (Instagram-style: ring + label) */}
          {stories.length > 0 ? (
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.highlights}>
              {stories.map((s, i) => {
                const label =
                  typeof s.title === 'string' && s.title
                    ? s.title
                    : typeof s.caption === 'string' && s.caption
                      ? s.caption
                      : 'Story';
                return (
                  <View key={String(s.post_id ?? s.id ?? i)} style={styles.highlight}>
                    <StoryRing size={64} seen={s.viewed === true || s.seen === true}>
                      <Avatar
                        uri={typeof s.poster_url === 'string' ? s.poster_url : (typeof s.media_url === 'string' ? s.media_url : null)}
                        name={label}
                        size={52}
                      />
                    </StoryRing>
                    <Text style={styles.highlightLabel} numberOfLines={1}>
                      {label}
                    </Text>
                  </View>
                );
              })}
            </ScrollView>
          ) : null}

          {/* Action buttons */}
          <View style={styles.actionsRow}>
            <Pressable
              style={styles.greyBtn}
              onPress={() => setTab(tab === 'edit' ? 'posts' : 'edit')}
            >
              <Text style={styles.greyBtnText}>{tab === 'edit' ? 'Close Edit' : 'Edit Profile'}</Text>
            </Pressable>
            <Pressable
              style={styles.greyBtn}
              onPress={() => nav.navigate('SavedContent', {})}
            >
              <Text style={styles.greyBtnText}>Saved</Text>
            </Pressable>
            <Pressable
              style={[styles.greyBtn, styles.logOutBtn]}
              onPress={() => void signOut()}
            >
              <Text style={[styles.greyBtnText, styles.logOutText]}>Log Out</Text>
            </Pressable>
          </View>
        </View>

        {/* Tab switcher: Instagram-style icon tabs, 1px active underline */}
        <View style={styles.tabBar}>
          {(['posts', 'reels', 'saved'] as const).map((t) => {
            const active = tab === t;
            const icon = t === 'posts' ? 'grid' : t === 'reels' ? 'film' : 'bookmark';
            const label = t === 'posts' ? 'Posts' : t === 'reels' ? 'Reels' : 'Saved';
            return (
              <Pressable
                key={t}
                onPress={() => setTab(t)}
                style={[styles.tabItem, active && styles.tabItemActive]}
                accessibilityRole="tab"
                accessibilityState={{ selected: active }}
                accessibilityLabel={`${label} tab`}
              >
                <Feather
                  name={icon}
                  size={22}
                  color={active ? colors.ink : colors.muted}
                />
              </Pressable>
            );
          })}
        </View>

        {/* Edit form */}
        {tab === 'edit' ? (
          <Card style={styles.editCard}>
            <Field label="Full name" value={name} onChangeText={setName} />
            <Field label="Bio" value={bio} onChangeText={setBio} multiline placeholder="Tell your friends what you like…" />
            {savedMsg ? <Notice tone="ok" message={savedMsg} /> : null}
            <Button
              label={saving ? 'Saving…' : 'Save changes'}
              disabled={saving}
              onPress={() => {
                if (!session) return;
                setSaving(true);
                setSaveError(null);
                updateOwnProfile(session.token, { full_name: name, bio })
                  .then((updated) => {
                    queryClient.setQueryData([...kidsKeys.ownProfile, session.token], updated);
                    setSavedMsg('Profile updated!');
                    void invalidateSocialCaches();
                  })
                  .catch((reason: unknown) => setSaveError(reason))
                  .finally(() => setSaving(false));
              }}
            />
          </Card>
        ) : null}

        {/* Empty state */}
        {tab !== 'edit' && !list.length ? (
          <EmptyState
            icon={emptyCopy[tab as Exclude<Tab, 'edit'>].icon}
            title={emptyCopy[tab as Exclude<Tab, 'edit'>].title}
            body={emptyCopy[tab as Exclude<Tab, 'edit'>].body}
          />
        ) : null}

        {/* 3-column square media grid */}
        {tab !== 'edit' && list.length > 0 ? (
          <View style={styles.grid}>
            {list.map((post) => {
              const isVid = post.media_type?.toUpperCase() === 'VIDEO';
              const imgUrl = isVid ? post.poster_url || post.media_url : post.media_url;
              return (
                <Pressable
                  key={post.post_id}
                  style={styles.gridCell}
                  accessibilityRole="button"
                  accessibilityLabel={isVid ? `Open reel ${post.post_id}` : `Open post ${post.post_id}`}
                  onPress={() => nav.navigate('PostDetail', { postId: post.post_id })}
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
        ) : null}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.surface,
  },
  centerLoading: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
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
  bioText: {
    fontSize: 14,
    color: colors.ink,
    marginTop: 3,
    lineHeight: 19,
  },
  bioPlaceholder: {
    fontSize: 14,
    color: colors.muted,
    fontStyle: 'italic',
    marginTop: 3,
  },
  highlights: {
    gap: spacing.md,
    paddingVertical: spacing.md,
  },
  highlight: {
    alignItems: 'center',
    maxWidth: 72,
  },
  highlightLabel: {
    fontSize: 11,
    color: colors.ink,
    marginTop: 4,
    textAlign: 'center',
  },
  actionsRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 12,
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
  logOutBtn: {},
  logOutText: {
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
  editCard: {
    margin: 16,
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
});
