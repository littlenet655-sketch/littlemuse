import { Image, Pressable, StatusBar, StyleSheet, Text, View } from 'react-native';
import { Feather } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useQuery } from '@tanstack/react-query';
import { fetchNotifications } from '../../api/kidsChat';
import { useAuth } from '../../auth/AuthProvider';
import type { ChildScreenProps } from '../../navigation/types';
import { kidsKeys } from '../../query/keys';
import { colors } from '../../ui/tokens';

const TABS: {
  key: string;
  label: string;
  icon: keyof typeof Feather.glyphMap;
}[] = [
  { key: 'FeedTab', label: 'Home', icon: 'home' },
  { key: 'DiscoverTab', label: 'Search', icon: 'search' },
  { key: 'CreateTab', label: 'Create', icon: 'plus-square' },
  { key: 'ReelsTab', label: 'Reels', icon: 'film' },
  { key: 'ProfileTab', label: 'Profile', icon: 'user' },
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

  return (
    <View style={[styles.root, isReels && styles.rootDark]}>
      <StatusBar barStyle={isReels ? 'light-content' : 'dark-content'} backgroundColor={isReels ? '#000000' : colors.surface} />
      {!isReels ? (
        <View style={[styles.top, { paddingTop: insets.top, height: 52 + insets.top }]}>
          <View style={styles.topInner}>
            <View style={styles.brandRow}>
              <Image
                source={require('../../../assets/app_logo.png')}
                style={styles.topLogo}
                resizeMode="cover"
              />
              <Text style={styles.wordmark}>LittleNet</Text>
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
                <Feather name="bell" size={22} color={colors.ink} />
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
                <Feather name="send" size={21} color={colors.ink} />
              </Pressable>
            </View>
          </View>
        </View>
      ) : null}
      <View style={styles.body}>{render(active)}</View>
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
          const isCreate = t.key === 'CreateTab';
          const iconColor = isReels
            ? isOn
              ? '#FFFFFF'
              : '#94A3B8'
            : isOn
              ? colors.ink
              : '#8E8E8E';

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
              {isCreate ? (
                <View style={[styles.createIconBox, isReels && styles.createIconBoxDark]}>
                  <Feather name="plus" size={18} color={isReels ? '#000000' : '#FFFFFF'} />
                </View>
              ) : (
                <Feather
                  name={t.icon}
                  size={isOn ? 24 : 23}
                  color={iconColor}
                />
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
    gap: 8,
  },
  topLogo: {
    width: 28,
    height: 28,
    borderRadius: 7,
  },
  wordmark: {
    color: colors.ink,
    fontSize: 22,
    fontWeight: '900',
    letterSpacing: -0.5,
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
    backgroundColor: colors.brand,
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
  createIconBox: {
    width: 32,
    height: 26,
    borderRadius: 8,
    backgroundColor: colors.brand,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1.5,
    borderColor: colors.brand,
  },
  createIconBoxDark: {
    backgroundColor: '#FFFFFF',
    borderColor: '#FFFFFF',
  },
});
