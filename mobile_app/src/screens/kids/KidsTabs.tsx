import { Image, Pressable, StatusBar, StyleSheet, Text, View } from 'react-native';
import { Feather } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';
import { fetchNotifications } from '../../api/kidsChat';
import { fetchOwnProfile } from '../../api/kidsProfiles';
import { useAuth } from '../../auth/AuthProvider';
import type { ChildScreenProps } from '../../navigation/types';
import { kidsKeys } from '../../query/keys';
import { colors } from '../../ui/tokens';
import { IgIcon, type IgIconName } from '../../components/IgIcon';
import { LnWordmark } from '../../components/LnWordmark';

const TABS: {
  key: string;
  label: string;
  icon: IgIconName | 'avatar';
}[] = [
  { key: 'FeedTab', label: 'Home', icon: 'home-outline' },
  { key: 'DiscoverTab', label: 'Search', icon: 'search' },
  { key: 'CreateTab', label: 'Create', icon: 'create' },
  { key: 'ReelsTab', label: 'Reels', icon: 'reels' },
  { key: 'ProfileTab', label: 'Profile', icon: 'avatar' },
];

export function KidsTabsShell({ navigation, route, render }: ChildScreenProps<'KidsTabs'> & { render: (tab: string) => React.ReactNode }) {
  const insets = useSafeAreaInsets();
  const { session } = useAuth();
  const active = String((route.params as { tab?: string } | undefined)?.tab ?? 'FeedTab');
  const nav = navigation as unknown as { navigate: (r: string, p: object) => void };
  const isReels = active === 'ReelsTab';
  // Shared cache with NotificationsScreen: the badge reflects server state.
  const notificationsQuery = useQuery({
    queryKey: [...kidsKeys.notifications, session?.token ?? 'signed-out'],
    enabled: Boolean(session),
    staleTime: 30_000,
    queryFn: () => fetchNotifications(session!.token),
  });
  const unread = (notificationsQuery.data?.notifications ?? []).filter((n) => !n.is_read).length;
  // Shared cache with OwnProfileScreen: the tab avatar reflects server state.
  const profileQuery = useQuery({
    queryKey: [...kidsKeys.ownProfile, session?.token ?? 'signed-out'],
    enabled: Boolean(session),
    staleTime: 30_000,
    queryFn: () => fetchOwnProfile(session!.token),
  });
  const tabProfile = profileQuery.data?.profile ?? null;
  const avatarUrl = typeof tabProfile?.avatar_url === 'string' ? tabProfile.avatar_url : null;

  return (
    <View style={[styles.root, isReels && styles.rootDark]}>
      <StatusBar barStyle={isReels ? 'light-content' : 'dark-content'} backgroundColor={isReels ? '#000000' : colors.surface} />
      {!isReels ? (
        <View style={[styles.top, { paddingTop: insets.top, height: 52 + insets.top }]}>
          <View style={styles.topInner}>
            <View style={styles.brandRow}>
              <LnWordmark width={128} />
            </View>
            <View style={styles.utilities}>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Stories"
                onPress={() => nav.navigate('Stories', {})}
                hitSlop={10}
                style={styles.utilityBtn}
              >
                <Feather name="camera" size={22} color={colors.ink} />
              </Pressable>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={`Notifications${unread > 0 ? `, ${unread} unread` : ''}`}
                onPress={() => nav.navigate('NotificationsTab', {})}
                hitSlop={10}
                style={styles.utilityBtn}
              >
                <IgIcon name="heart" size={24} color={colors.ink} />
                {unread > 0 ? (
                  <View style={styles.badge}>
                    <Text style={styles.badgeText}>{unread > 9 ? '9+' : String(unread)}</Text>
                  </View>
                ) : null}
              </Pressable>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Messages"
                onPress={() => nav.navigate('Conversations', {})}
                hitSlop={10}
                style={styles.utilityBtn}
              >
                <IgIcon name="send" size={23} color={colors.ink} />
              </Pressable>
            </View>
          </View>
        </View>
      ) : null}
      <View style={styles.body}>{render(active)}</View>
      {/* Instagram parity: the composer is a full-screen flow — the tab bar
          stays hidden while creating so media/caption steps own the screen. */}
      {active !== 'CreateTab' ? (
      <View
        style={[
          styles.tabs,
          isReels && styles.tabsDark,
          {
            paddingBottom: Math.max(insets.bottom, 8),
            height: 54 + Math.max(insets.bottom, 8),
          },
        ]}
      >
        {TABS.map((t) => {
          const isOn = active === t.key;
          const isAvatar = t.icon === 'avatar';
          // Kit: active home is the filled glyph in #262626 (never blue).
          const iconName: IgIconName =
            t.key === 'FeedTab' ? (isOn ? 'home-filled' : 'home-outline') : (t.icon as IgIconName);
          const iconColor = isReels ? (isOn ? '#FFFFFF' : '#94A3B8') : colors.ink;

          return (
            <Pressable
              key={t.key}
              accessibilityRole="tab"
              accessibilityState={{ selected: isOn }}
              accessibilityLabel={t.label}
              onPress={() => nav.navigate('KidsTabs', { tab: t.key })}
              style={styles.tab}
              hitSlop={6}
            >
              {isAvatar ? (
                avatarUrl ? (
                  <Image
                    source={{ uri: avatarUrl }}
                    style={[
                      styles.tabAvatar,
                      isOn ? styles.tabAvatarActive : styles.tabAvatarIdle,
                    ]}
                  />
                ) : (
                  <View
                    style={[
                      styles.tabAvatar,
                      styles.tabAvatarFallback,
                      isOn ? styles.tabAvatarActive : styles.tabAvatarIdle,
                    ]}
                  />
                )
              ) : (
                <IgIcon name={iconName} size={26} color={iconColor} />
              )}
            </Pressable>
          );
        })}
      </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.background,
  },
  rootDark: {
    backgroundColor: '#000000',
  },
  top: {
    backgroundColor: colors.surface,
    borderBottomWidth: 1,
    borderBottomColor: '#F0F0F0',
  },
  topInner: {
    height: 52,
    paddingHorizontal: 16,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  brandRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  utilities: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 18,
  },
  utilityBtn: {
    padding: 2,
  },
  badge: {
    position: 'absolute',
    top: -4,
    right: -6,
    minWidth: 16,
    height: 16,
    borderRadius: 8,
    backgroundColor: '#FF3040',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 3,
  },
  badgeText: {
    color: '#FFFFFF',
    fontSize: 10,
    fontWeight: '800',
  },
  body: {
    flex: 1,
  },
  tabs: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderTopWidth: 1,
    borderTopColor: '#F0F0F0',
    paddingTop: 4,
  },
  tabsDark: {
    backgroundColor: '#000000',
    borderTopColor: '#1E293B',
  },
  tab: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    height: '100%',
  },
  tabAvatar: {
    width: 28,
    height: 28,
    borderRadius: 14,
    borderWidth: 1.5,
  },
  tabAvatarActive: {
    borderColor: colors.ink,
  },
  tabAvatarIdle: {
    borderColor: colors.line,
  },
  tabAvatarFallback: {
    backgroundColor: '#EFEFEF',
  },
});
