import { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Dimensions, Image, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { FlashList } from '@shopify/flash-list';
import { useQuery } from '@tanstack/react-query';
import { fetchOwnProfile, updateOwnProfile } from '../../api/kidsProfiles';
import { fetchSaved } from '../../api/kidsSocial';
import { useAuth } from '../../auth/AuthProvider';
import type { ChildScreenProps } from '../../navigation/types';
import { queryClient } from '../../query/client';
import { invalidateSocialCaches, kidsKeys } from '../../query/keys';
import { Avatar, StoryRing } from '../../ui/social';
import { Button, Card, EmptyState, ErrorState, Field, GateNotice, Notice, Screen } from '../../ui/components';
import { IgIcon } from '../../components/IgIcon';
import { colors, radius, spacing } from '../../ui/tokens';

type Tab = 'posts' | 'reels' | 'saved' | 'edit';

const AVATAR = 80;
const STORY_RING = AVATAR + 12;
const GAP = 1;
const GRID_COLS = 3;
const cellSize = (Dimensions.get('window').width - GAP * (GRID_COLS - 1)) / GRID_COLS;

/** Kit-style 3x3 grid glyph for the posts tab — drawn with Views. */
function GridGlyph({ size = 24, color = colors.ink }: { size?: number; color?: string }) {
  const cell = (size - 2) / 3;
  return (
    <View style={{ width: size, height: size, flexDirection: 'row', flexWrap: 'wrap', gap: 1 }}>
      {Array.from({ length: 9 }, (_, i) => (
        <View key={i} style={{ width: cell, height: cell, backgroundColor: color, borderRadius: 1 }} />
      ))}
    </View>
  );
}

/** Kit-style down chevron drawn with Views (no chevron glyph in IgIcon). */
function ChevronDown({ color = colors.ink }: { color?: string }) {
  return (
    <View
      style={{
        width: 9,
        height: 9,
        borderRightWidth: 2,
        borderBottomWidth: 2,
        borderColor: color,
        transform: [{ rotate: '45deg' }],
        marginBottom: 3,
      }}
    />
  );
}

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

  const stories = readStories(profile);
  const hasUnviewedStories = stories.some((s) => !(s.viewed === true || s.seen === true));
  const openStory = (story?: Record<string, unknown>) => {
    const initialStoryId = Number(story?.post_id ?? story?.id ?? stories[0]?.post_id ?? stories[0]?.id ?? 0);
    const initialChildId = Number(story?.child_id ?? session?.user?.user_id ?? 0);
    nav.navigate('Stories', {
      ...(initialStoryId > 0 ? { initialStoryId } : {}),
      ...(initialChildId > 0 ? { initialChildId } : {}),
    });
  };

  const handle =
    typeof profile?.username === 'string' && profile.username
      ? `@${profile.username}`
      : String(profile?.full_name ?? 'You');

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
  const currentEmpty = tab === 'edit' ? null : emptyCopy[tab];

  return (
    <View style={styles.container}>
      <FlashList
        key={tab}
        data={tab === 'edit' ? [] : list}
        keyExtractor={(post) => String(post.post_id)}
        numColumns={GRID_COLS}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
        drawDistance={600}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            colors={[colors.brand]}
            tintColor={colors.brand}
          />
        }
        ListHeaderComponent={
          <>
            {error ? <GateNotice error={error} /> : null}

            {/* Kit top bar: @username + verified + chevron, left; create icon, right */}
            <View style={styles.topBar}>
              <View style={styles.userRow}>
                <Text style={styles.username} numberOfLines={1}>
                  {handle}
                </Text>
                <IgIcon name="verified" size={17} color={colors.brand} />
                <ChevronDown />
              </View>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Create post"
                hitSlop={8}
                onPress={() => nav.navigate('KidsTabs', { tab: 'CreateTab' })}
              >
                <IgIcon name="create" size={27} color={colors.ink} />
              </Pressable>
            </View>

            {/* Instagram-style profile header */}
            <View style={styles.header}>
              <View style={styles.headRow}>
                {stories.length > 0 ? (
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel="Open your stories"
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
                  <Pressable
                    style={styles.statItem}
                    accessibilityRole="button"
                    accessibilityLabel="View friends"
                    onPress={() => nav.navigate('Connections', { mode: 'followers' })}
                  >
                    <Text style={styles.statNum}>{Number(counts.followers ?? 0)}</Text>
                    <Text style={styles.statLabel}>Classmates</Text>
                  </Pressable>
                  <View style={styles.statItem}>
                    <Text style={styles.statNum}>{Number(counts.following ?? 0)}</Text>
                    <Text style={styles.statLabel}>Following</Text>
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

              {/* Story highlights (kit: ring + grey label underneath) */}
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
                        <Text style={styles.highlightLabel} numberOfLines={1}>
                          {label}
                        </Text>
                      </Pressable>
                    );
                  })}
                </ScrollView>
              ) : null}

              {/* Action buttons: kit light-grey rounded buttons, existing handlers untouched */}
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

            {/* Tab switcher: kit icon tabs, active tab has ink icon + top border indicator */}
            <View style={styles.tabBar}>
              {(['posts', 'reels', 'saved'] as const).map((t) => {
                const active = tab === t;
                const label = t === 'posts' ? 'Posts' : t === 'reels' ? 'Reels' : 'Saved';
                const color = active ? colors.ink : colors.muted;
                return (
                  <Pressable
                    key={t}
                    onPress={() => setTab(t)}
                    style={[styles.tabItem, active && styles.tabItemActive]}
                    accessibilityRole="tab"
                    accessibilityState={{ selected: active }}
                    accessibilityLabel={`${label} tab`}
                  >
                    {t === 'posts' ? (
                      <GridGlyph size={24} color={color} />
                    ) : (
                      <IgIcon name={t === 'reels' ? 'reels' : 'bookmark'} size={24} color={color} />
                    )}
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
          </>
        }
        ListEmptyComponent={
          currentEmpty ? (
            <EmptyState icon={currentEmpty.icon} title={currentEmpty.title} body={currentEmpty.body} />
          ) : null
        }
        renderItem={({ item: post, index }) => {
          const isVid = post.media_type?.toUpperCase() === 'VIDEO';
          const imgUrl = isVid ? post.poster_url || post.media_url : post.media_url;
          return (
            <Pressable
              style={[styles.gridCell, index % GRID_COLS < GRID_COLS - 1 ? { marginRight: GAP } : null]}
              accessibilityRole="button"
              accessibilityLabel={isVid ? `Open reel ${post.post_id}` : `Open post ${post.post_id}`}
              onPress={() => nav.navigate('PostDetail', { postId: post.post_id })}
            >
              {imgUrl ? (
                <Image source={{ uri: imgUrl }} style={styles.gridThumb} resizeMode="cover" />
              ) : (
                <View style={styles.gridPlaceholder}>
                  {isVid ? (
                    <IgIcon name="reels" size={26} color={colors.muted} />
                  ) : (
                    <GridGlyph size={26} color={colors.muted} />
                  )}
                </View>
              )}
              {isVid ? (
                <View style={styles.videoMark}>
                  <IgIcon name="reels" size={18} color="#FFFFFF" />
                </View>
              ) : null}
              {typeof post.likes === 'number' ? (
                <View style={styles.likeOverlay}>
                  <IgIcon name="heart" size={15} color="#FFFFFF" />
                  <Text style={styles.likeCount}>{post.likes}</Text>
                </View>
              ) : null}
            </Pressable>
          );
        }}
      />
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
  topBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: colors.surface,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    paddingBottom: spacing.sm,
  },
  userRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    flexShrink: 1,
  },
  username: {
    fontSize: 20,
    fontWeight: '800',
    color: colors.ink,
  },
  header: {
    backgroundColor: colors.surface,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
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
    fontSize: 18,
    fontWeight: '800',
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
    color: colors.muted,
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
  },
  tabItem: {
    flex: 1,
    paddingVertical: 10,
    alignItems: 'center',
    borderTopWidth: 1,
    borderTopColor: 'transparent',
  },
  tabItemActive: {
    borderTopColor: colors.ink,
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
  videoMark: {
    position: 'absolute',
    top: 6,
    right: 6,
  },
  likeOverlay: {
    position: 'absolute',
    left: 8,
    bottom: 6,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
  },
  likeCount: {
    fontSize: 13,
    fontWeight: '700',
    color: '#FFFFFF',
    textShadowColor: 'rgba(0,0,0,0.6)',
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 3,
  },
});
