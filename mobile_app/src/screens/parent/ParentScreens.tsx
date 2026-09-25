import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Alert, FlatList, Image, KeyboardAvoidingView, Platform, Pressable, RefreshControl, ScrollView, StyleSheet, Switch, Text, View } from 'react-native';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useVideoPlayer } from 'expo-video';
import { Feather } from '@expo/vector-icons';
import {
  extendChildScreenTime,
  fetchFollowRequests,
  fetchParentActivity,
  fetchParentControls,
  fetchParentDashboard,
  fetchParentNotifications,
  fetchParentSafety,
  fetchViewingInsights,
  markParentNotificationsRead,
  resetChildPassword,
  resetChildScreenTime,
  resolveFollowRequest,
  resolveParentReview,
  unlinkChild,
  updateParentControls,
  updateTimeLimit,
  type ParentChild,
  type ParentControls,
  type ParentNotification,
  type ReviewPreview,
  type ViewingInsights,
} from '../../api/parentAdmin';
import { useAuth } from '../../auth/AuthProvider';
import { NativeVideoView } from '../../ui/nativeViews';
import { ensureParentAuthForAction } from '../../components/ParentModeGate';
import type { ParentScreenProps } from '../../navigation/types';
import { useIsOnline } from '../../query/client';
import { parentKeys } from '../../query/keys';
import { BrandHeader, Button, Card, EmptyState, ErrorState, Field, LoadingState, Notice, OfflineBanner, Screen, errorText } from '../../ui/components';
import { Avatar, CategoryBadge, TimeAgo } from '../../ui/social';
import { colors, radius, spacing, type } from '../../ui/tokens';

type FeatherIconName = keyof typeof Feather.glyphMap;

const MENU: {
  label: string;
  body: string;
  icon: FeatherIconName;
  iconColor: string;
  badgeBg: string;
  route: 'Children' | 'ParentSafety' | 'ScreenTime' | 'ParentControls' | 'FollowRequests' | 'ParentActivity' | 'ParentNotifications' | 'ParentSettings';
}[] = [
  { label: 'Children', body: 'Profiles, progress and account state', icon: 'users', iconColor: '#2563EB', badgeBg: '#EFF6FF', route: 'Children' },
  { label: 'Safety Review', body: 'Items that need your decision', icon: 'shield', iconColor: '#DC2626', badgeBg: '#FEF2F2', route: 'ParentSafety' },
  { label: 'Screen Time', body: 'Daily usage and limits', icon: 'clock', iconColor: '#059669', badgeBg: '#ECFDF5', route: 'ScreenTime' },
  { label: 'Feature Controls', body: 'Permissions, quiet hours and categories', icon: 'sliders', iconColor: '#4F46E5', badgeBg: '#EEF2FF', route: 'ParentControls' },
  { label: 'Follow Requests', body: 'Two-parent friendship approvals', icon: 'user-check', iconColor: '#DB2777', badgeBg: '#FDF2F8', route: 'FollowRequests' },
  { label: 'Activity History', body: 'Recent child activity and logs', icon: 'activity', iconColor: '#7C3AED', badgeBg: '#F5F3FF', route: 'ParentActivity' },
  { label: 'Notifications', body: 'Safety and account updates', icon: 'bell', iconColor: '#D97706', badgeBg: '#FFFBEB', route: 'ParentNotifications' },
  { label: 'Parent Settings', body: 'Account and sign out', icon: 'settings', iconColor: '#475569', badgeBg: '#F1F5F9', route: 'ParentSettings' },
];

function useDashboard(token?: string) {
  return useQuery({
    queryKey: parentKeys.dashboard,
    queryFn: ({ signal }) => fetchParentDashboard(token ?? '', signal),
    enabled: Boolean(token),
  });
}

function RefreshingScroll({ refreshing, onRefresh, children }: { refreshing: boolean; onRefresh: () => void; children: React.ReactNode }) {
  return (
    <ScrollView
      style={styles.flex}
      keyboardShouldPersistTaps="handled"
      keyboardDismissMode="on-drag"
      automaticallyAdjustKeyboardInsets={Platform.OS === 'ios'}
      contentContainerStyle={styles.refreshScrollContent}
      showsVerticalScrollIndicator={true}
      nestedScrollEnabled={true}
      bounces={true}
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
    >
      {children}
    </ScrollView>
  );
}

function GuardianBanner() {
  return (
    <View style={styles.guardianBanner}>
      <View style={styles.guardianRow}>
        <View style={styles.guardianIconWrap}>
          <Feather name="shield" size={22} color="#38BDF8" />
        </View>
        <View style={styles.flex}>
          <View style={styles.guardianTitleRow}>
            <Text style={styles.guardianTitle}>LittleNet Guardian Protection</Text>
            <View style={styles.guardianLiveChip}>
              <View style={styles.livePulseDot} />
              <Text style={styles.guardianLiveText}>LIVE</Text>
            </View>
          </View>
          <Text style={styles.guardianSub}>
            Real-time AI moderation, private quarantine storage, and dual-parent approvals.
          </Text>
        </View>
      </View>
      <View style={styles.guardianPillsRow}>
        <View style={styles.guardianPill}>
          <Feather name="check-circle" size={11} color="#38BDF8" />
          <Text style={styles.guardianPillText}>AI Content Shield</Text>
        </View>
        <View style={styles.guardianPill}>
          <Feather name="lock" size={11} color="#38BDF8" />
          <Text style={styles.guardianPillText}>Quarantine Pipeline</Text>
        </View>
        <View style={styles.guardianPill}>
          <Feather name="users" size={11} color="#38BDF8" />
          <Text style={styles.guardianPillText}>Dual Consent</Text>
        </View>
      </View>
    </View>
  );
}

function ChildCard({
  child,
  onPress,
  onScreenTime,
  onControls,
  onActivity,
}: {
  child: ParentChild;
  onPress?: () => void;
  onScreenTime?: () => void;
  onControls?: () => void;
  onActivity?: () => void;
}) {
  const limit = child.limit?.daily_limit_minutes;
  // Guard: a malformed minutes_today (NaN/undefined from the server) would
  // produce a NaN ratio and a broken "NaN%" gauge width. Coerce to 0.
  const usageRatio = limit && Number.isFinite(child.minutes_today / limit)
    ? Math.min(child.minutes_today / limit, 1)
    : 0;
  const isOnline = Boolean(child.presence?.online);
  const hasReviews = (child.open_reviews || 0) > 0;
  const isLocked = Boolean(child.limit?.strict_mode && limit && child.minutes_today >= limit);

  return (
    <Pressable
      accessibilityRole={onPress ? 'button' : undefined}
      disabled={!onPress}
      onPress={onPress}
      style={styles.childCard}
    >
      {/* Top row: Avatar, Name, Username, Age, Safety Pill */}
      <View style={styles.childTopRow}>
        <View style={styles.avatarWrapper}>
          <Avatar uri={child.avatar_url} name={child.full_name} size={50} />
          <View style={[styles.presenceIndicator, isOnline ? styles.onlineIndicator : styles.offlineIndicator]} />
        </View>

        <View style={styles.childMetaCol}>
          <View style={styles.childNameRow}>
            <Text style={styles.childFullName} numberOfLines={1}>
              {child.full_name}
            </Text>
            {child.age ? (
              <View style={styles.agePill}>
                <Text style={styles.agePillText}>Age {child.age}</Text>
              </View>
            ) : null}
          </View>
          <Text style={styles.childHandleText}>@{child.username}</Text>
        </View>

        <View style={styles.childStatusBadge}>
          {hasReviews ? (
            <View style={styles.alertPill}>
              <Feather name="alert-circle" size={12} color={colors.danger} />
              <Text style={styles.alertText}>{child.open_reviews} review</Text>
            </View>
          ) : isLocked ? (
            <View style={[styles.alertPill, { backgroundColor: '#FEF2F2', borderColor: '#FCA5A5' }]}>
              <Feather name="lock" size={12} color="#DC2626" />
              <Text style={[styles.alertText, { color: '#DC2626' }]}>Locked</Text>
            </View>
          ) : (
            <View style={styles.safePill}>
              <Feather name="shield" size={12} color="#059669" />
              <Text style={styles.safeText}>Safe</Text>
            </View>
          )}
        </View>
      </View>

      {/* Middle row: Screen Time Bar & Quiz Score */}
      <View style={styles.childStatsSection}>
        <View style={styles.usageRow}>
          <View style={styles.usageLabelRow}>
            <View style={styles.statIconLabel}>
              <Feather name="clock" size={12} color={isLocked ? '#DC2626' : '#64748B'} />
              <Text style={[styles.usageStatText, isLocked && { color: '#DC2626', fontWeight: '700' }]}>
                {child.minutes_today} {limit ? `/ ${limit} min today` : 'min used today'}
                {isLocked ? ' (Limit reached)' : ''}
              </Text>
            </View>
            {limit ? (
              <Text style={[styles.usagePercentText, (usageRatio >= 0.9 || isLocked) && styles.usageDangerText]}>
                {Math.round(usageRatio * 100)}%
              </Text>
            ) : null}
          </View>
          {limit ? (
            <View style={styles.usageTrack}>
              <View
                style={[
                  styles.usageFill,
                  usageRatio >= 1 && styles.usageDanger,
                  usageRatio >= 0.8 && usageRatio < 1 && styles.usageWarning,
                  { width: `${Math.max(usageRatio * 100, 3)}%` },
                ]}
              />
            </View>
          ) : null}
        </View>

        <View style={styles.chipsRow}>
          <View style={styles.quizScoreChip}>
            <Feather name="award" size={12} color="#2563EB" />
            <Text style={styles.quizScoreText}>
              Quiz: {child.quiz_7d?.accuracy ?? 0}% ({child.quiz_7d?.correct ?? 0}/{child.quiz_7d?.attempted ?? 0})
            </Text>
          </View>
          <View style={styles.behaviorChip}>
            <Feather name="check" size={12} color="#059669" />
            <Text style={styles.behaviorChipText}>
              {child.safety?.safety_level ?? 'STRICT'} Filter
            </Text>
          </View>
        </View>
      </View>

      {/* Bottom quick actions */}
      {(onScreenTime || onControls || onActivity) ? (
        <View style={styles.childQuickActionsRow}>
          {onScreenTime ? (
            <Pressable
              accessibilityRole="button"
              onPress={onScreenTime}
              style={[styles.quickActionPill, isLocked && { borderColor: '#FCA5A5', backgroundColor: '#FEF2F2' }]}
              hitSlop={6}
            >
              <Feather name="clock" size={12} color={isLocked ? '#DC2626' : '#2563EB'} />
              <Text style={[styles.quickActionText, isLocked && { color: '#DC2626', fontWeight: '800' }]}>
                {isLocked ? 'Reset / Add Time' : 'Limits'}
              </Text>
            </Pressable>
          ) : null}
          {onControls ? (
            <Pressable
              accessibilityRole="button"
              onPress={onControls}
              style={styles.quickActionPill}
              hitSlop={6}
            >
              <Feather name="sliders" size={12} color="#4F46E5" />
              <Text style={styles.quickActionText}>Controls</Text>
            </Pressable>
          ) : null}
          {onActivity ? (
            <Pressable
              accessibilityRole="button"
              onPress={onActivity}
              style={styles.quickActionPill}
              hitSlop={6}
            >
              <Feather name="activity" size={12} color="#7C3AED" />
              <Text style={styles.quickActionText}>Activity</Text>
            </Pressable>
          ) : null}
          <View style={styles.cardChevronWrap}>
            <Text style={styles.detailsPromptText}>Details</Text>
            <Feather name="chevron-right" size={14} color="#94A3B8" />
          </View>
        </View>
      ) : null}
    </Pressable>
  );
}

function AsyncBody({ query, emptyTitle, emptyBody, children }: { query: { isPending: boolean; isError: boolean; error: unknown; refetch: () => Promise<unknown> }; emptyTitle?: string; emptyBody?: string; children: React.ReactNode }) {
  if (query.isPending) return <LoadingState />;
  if (query.isError) return <ErrorState message={errorText(query.error)} onRetry={() => void query.refetch()} />;
  return <>{children || <EmptyState title={emptyTitle ?? 'Nothing here'} body={emptyBody} />}</>;
}

export function ParentHomeScreen({ navigation }: ParentScreenProps<'ParentHome'>) {
  const { session } = useAuth();
  const online = useIsOnline();
  const dashboard = useDashboard(session?.token);
  const children = dashboard.data?.children ?? [];
  const reviews = children.reduce((sum, child) => sum + Number(child.open_reviews || 0), 0);
  const unreadAlerts = dashboard.data?.unread ?? 0;

  return (
    <Screen>
      <RefreshingScroll refreshing={dashboard.isRefetching} onRefresh={() => void dashboard.refetch()}>
        <OfflineBanner online={online} />

        {/* Parent Welcome Banner */}
        <View style={styles.parentWelcomeBanner}>
          <View style={styles.parentWelcomeMeta}>
            <View style={styles.parentGreetingRow}>
              <View style={styles.parentAvatarInitial}>
                <Text style={styles.parentAvatarInitialText}>
                  {(session?.user.full_name ?? 'P').charAt(0).toUpperCase()}
                </Text>
              </View>
              <View style={styles.flex}>
                <Text style={styles.parentGreetingName}>
                  Hello, {session?.user.full_name ?? 'Parent'}
                </Text>
                <View style={styles.parentRoleBadgeRow}>
                  <View style={styles.parentRoleBadge}>
                    <Feather name="shield" size={10} color="#2563EB" />
                    <Text style={styles.parentRoleBadgeText}>Family Administrator</Text>
                  </View>
                </View>
              </View>
            </View>
            <Text style={styles.parentWelcomeSub}>
              Active oversight & server-enforced safety rules for your family.
            </Text>
          </View>
        </View>

        {/* Guardian Security Status */}
        <GuardianBanner />

        {/* High-Level Metric Tiles */}
        <View style={styles.metrics}>
          <Metric
            value={String(children.length)}
            label="Children"
            icon="users"
            iconColor="#2563EB"
            bgTone="#EFF6FF"
            onPress={() => navigation.navigate('Children')}
          />
          <Metric
            value={reviews ? `${reviews} Open` : '0 Open'}
            label="Reviews"
            icon="shield"
            iconColor={reviews ? '#DC2626' : '#059669'}
            bgTone={reviews ? '#FEF2F2' : '#ECFDF5'}
            tone={reviews ? 'alert' : 'normal'}
            onPress={() => navigation.navigate('ParentSafety')}
          />
          <Metric
            value={String(unreadAlerts)}
            label="Alerts"
            icon="bell"
            iconColor="#7C3AED"
            bgTone="#F5F3FF"
            onPress={() => navigation.navigate('ParentNotifications')}
          />
        </View>

        {/* CHILD OVERSIGHT SECTION */}
        <View style={styles.sectionWrap}>
          <View style={styles.sectionHeaderRow}>
            <View style={styles.sectionHeaderLeft}>
              <Text style={styles.sectionHeaderLabel}>CHILD OVERSIGHT</Text>
              <View style={styles.sectionCountPill}>
                <Text style={styles.sectionCountText}>{children.length}</Text>
              </View>
            </View>
            <Pressable
              accessibilityRole="button"
              onPress={() => navigation.navigate('CreateChild')}
              hitSlop={8}
              style={styles.addInlineButton}
            >
              <Feather name="plus" size={13} color={colors.brand} />
              <Text style={styles.addInlineText}>Add Child</Text>
            </Pressable>
          </View>

          {dashboard.isPending ? (
            <LoadingState message="Loading child oversight data…" />
          ) : dashboard.isError ? (
            <Card style={styles.oversightErrorCard}>
              <View style={styles.errorIconCircle}>
                <Feather name="refresh-cw" size={20} color="#DC2626" />
              </View>
              <Text style={styles.errorCardTitle}>Could not load family oversight</Text>
              <Text style={styles.errorCardSub}>
                Unable to sync live child accounts. Please tap retry to refresh.
              </Text>
              <Button
                label="Retry Sync"
                onPress={() => void dashboard.refetch()}
                variant="secondary"
              />
            </Card>
          ) : children.length ? (
            <>
              {children.map((child) => (
                <ChildCard
                  key={child.user_id}
                  child={child}
                  onPress={() => navigation.navigate('ChildSummary', { childId: child.user_id })}
                  onScreenTime={() => navigation.navigate('ScreenTime', { childId: child.user_id })}
                  onControls={() => navigation.navigate('ParentControls', { childId: child.user_id })}
                  onActivity={() => navigation.navigate('ParentActivity', { childId: child.user_id })}
                />
              ))}

            </>
          ) : (
            <Card>
              <View style={styles.emptyChildContainer}>
                <View style={styles.emptyChildBadge}>
                  <Feather name="user-plus" size={24} color={colors.brand} />
                </View>
                <Text style={styles.emptyChildTitle}>No Child Accounts Yet</Text>
                <Text style={styles.emptyChildBody}>
                  Add your child's profile to activate AI safety monitoring, age-tailored quizzes, and daily screen time limits.
                </Text>
                <Button label="+ Add First Child" onPress={() => navigation.navigate('CreateChild')} />
              </View>
            </Card>
          )}
        </View>

        {/* VIEWING INSIGHTS SECTION — per-child read-only watch aggregates */}
        {children.length ? (
          <View style={styles.sectionWrap}>
            <Text style={styles.sectionHeaderLabel}>VIEWING INSIGHTS</Text>
            {children.map((child) => (
              <ViewingInsightsCard key={child.user_id} token={session?.token} child={child} />
            ))}
          </View>
        ) : null}

        {/* CONTROLS & SUPERVISION SECTION */}
        <View style={styles.sectionWrap}>
          <Text style={styles.sectionHeaderLabel}>CONTROLS & SUPERVISION</Text>
          <View style={styles.menuGroupCard}>
            {MENU.slice(0, 4).map((item, idx) => (
              <Pressable
                key={item.route}
                accessibilityRole="button"
                style={[styles.menuRowItem, idx < MENU.slice(0, 4).length - 1 && styles.menuRowBorder]}
                onPress={() => navigation.navigate(item.route as never)}
              >
                <View style={[styles.menuIconBadge, { backgroundColor: item.badgeBg }]}>
                  <Feather name={item.icon} size={20} color={item.iconColor} />
                </View>
                <View style={styles.flex}>
                  <Text style={styles.menuTitle}>{item.label}</Text>
                  <Text style={styles.muted}>{item.body}</Text>
                </View>
                <Feather name="chevron-right" size={18} color="#9CA3AF" />
              </Pressable>
            ))}
          </View>
        </View>

        {/* COMMUNITY & ACCOUNT SECTION */}
        <View style={styles.sectionWrap}>
          <Text style={styles.sectionHeaderLabel}>COMMUNITY & ACCOUNT</Text>
          <View style={styles.menuGroupCard}>
            {MENU.slice(4).map((item, idx) => (
              <Pressable
                key={item.route}
                accessibilityRole="button"
                style={[styles.menuRowItem, idx < MENU.slice(4).length - 1 && styles.menuRowBorder]}
                onPress={() => navigation.navigate(item.route as never)}
              >
                <View style={[styles.menuIconBadge, { backgroundColor: item.badgeBg }]}>
                  <Feather name={item.icon} size={20} color={item.iconColor} />
                </View>
                <View style={styles.flex}>
                  <Text style={styles.menuTitle}>{item.label}</Text>
                  <Text style={styles.muted}>{item.body}</Text>
                </View>
                <Feather name="chevron-right" size={18} color="#9CA3AF" />
              </Pressable>
            ))}
          </View>
        </View>

      </RefreshingScroll>
    </Screen>
  );
}

function formatWatchDuration(seconds: number): string {
  const minutes = Math.round(seconds / 60);
  if (minutes < 1) return '0m';
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours}h ${rest}m` : `${hours}h`;
}

/** Per-child read-only watch summary, rendered inside the parent dashboard.
    Data comes from GET /api/parent/child/<id>/viewing-insights (server
    aggregates content_impressions; the parent-owns-child gate is enforced
    server-side). States: loading / error / empty / data. */
function ViewingInsightsCard({ token, child }: { token?: string; child: ParentChild }) {
  const insights = useQuery({
    queryKey: parentKeys.insights(child.user_id),
    queryFn: () => fetchViewingInsights(token as string, child.user_id),
    enabled: !!token,
    staleTime: 5 * 60 * 1000,
  });

  const data: ViewingInsights | undefined = insights.data;
  const top = (data?.by_category ?? []).slice(0, 3);
  const maxViews = top.reduce((m, c) => Math.max(m, c.views), 0) || 1;
  const topReel = data?.top_reels?.[0];

  return (
    <Card style={styles.insightCard}>
      <View style={styles.insightHeader}>
        <Avatar uri={child.avatar_url} name={child.full_name ?? child.username} size={36} />
        <View style={styles.flex}>
          <Text style={styles.insightChildName}>{child.full_name ?? child.username}</Text>
          <Text style={styles.muted}>Viewing insights</Text>
        </View>
        <Feather name="eye" size={16} color={colors.muted} />
      </View>

      {insights.isPending ? (
        <ActivityIndicator size="small" color={colors.muted} style={styles.insightPad} />
      ) : insights.isError || !data ? (
        <Text style={[styles.muted, styles.insightPad]}>Watch insights unavailable right now.</Text>
      ) : data.windows['30d'].views === 0 ? (
        <Text style={[styles.muted, styles.insightPad]}>No watch activity recorded yet.</Text>
      ) : (
        <>
          <View style={styles.insightStatRow}>
            <View style={styles.insightStat}>
              <Text style={styles.insightStatValue}>{formatWatchDuration(data.windows['7d'].watch_seconds)}</Text>
              <Text style={styles.muted}>This week</Text>
            </View>
            <View style={styles.insightStat}>
              <Text style={styles.insightStatValue}>{formatWatchDuration(data.windows['30d'].watch_seconds)}</Text>
              <Text style={styles.muted}>Last 30 days</Text>
            </View>
          </View>
          {top.map((c) => (
            <View key={c.category} style={styles.insightBarRow}>
              <Text style={styles.insightBarLabel} numberOfLines={1}>{c.category}</Text>
              <View style={styles.insightBarTrack}>
                <View style={[styles.insightBarFill, { width: `${Math.max(4, (c.views / maxViews) * 100)}%` }]} />
              </View>
              <Text style={styles.insightBarValue}>{c.views}</Text>
            </View>
          ))}
          {topReel ? (
            <Text style={styles.insightTopReel} numberOfLines={2}>
              Most watched: {topReel.title} · {topReel.views} views
            </Text>
          ) : null}
        </>
      )}
    </Card>
  );
}

function Metric({
  value,
  label,
  icon,
  iconColor,
  bgTone = '#FFFFFF',
  tone = 'normal',
  onPress,
}: {
  value: string;
  label: string;
  icon: FeatherIconName;
  iconColor: string;
  bgTone?: string;
  tone?: 'normal' | 'alert';
  onPress?: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      style={[styles.metric, { backgroundColor: bgTone }, tone === 'alert' && styles.metricAlert]}
    >
      <View style={styles.metricTop}>
        <View style={[styles.metricIconWrap, { backgroundColor: `${iconColor}15` }]}>
          <Feather name={icon} size={16} color={iconColor} />
        </View>
        <Text style={[styles.metricValue, tone === 'alert' && styles.metricValueAlert]}>{value}</Text>
      </View>
      <Text style={styles.metricLabel}>{label}</Text>
    </Pressable>
  );
}

function SubScreenHero({
  kicker,
  title,
  subtitle,
  icon,
  iconColor = '#2563EB',
  iconBg = '#EFF6FF',
}: {
  kicker?: string;
  title: string;
  subtitle: string;
  icon: FeatherIconName;
  iconColor?: string;
  iconBg?: string;
}) {
  return (
    <View style={styles.subHeroContainer}>
      <View style={styles.subHeroTopRow}>
        <View style={styles.flex}>
          {kicker ? (
            <View style={styles.subHeroKickerRow}>
              <Text style={styles.subHeroKickerText}>{kicker.toUpperCase()}</Text>
            </View>
          ) : null}
          <Text style={styles.subHeroTitle}>{title}</Text>
        </View>
        <View style={[styles.subHeroIconBadge, { backgroundColor: iconBg }]}>
          <Feather name={icon} size={22} color={iconColor} />
        </View>
      </View>
      <Text style={styles.subHeroSubtitle}>{subtitle}</Text>
    </View>
  );
}

export function ParentChildrenScreen({ navigation }: ParentScreenProps<'Children'>) {
  const { session } = useAuth();
  const query = useDashboard(session?.token);
  const children = query.data?.children ?? [];

  return (
    <Screen>
      <RefreshingScroll refreshing={query.isRefetching} onRefresh={() => void query.refetch()}>
        <SubScreenHero
          kicker="Controls & Supervision"
          title="Children Profiles"
          subtitle="Manage your family's connected child accounts, view safety state, and configure limits."
          icon="users"
          iconColor="#2563EB"
          iconBg="#EFF6FF"
        />

        {query.isPending ? (
          <LoadingState message="Loading child profiles…" />
        ) : query.isError ? (
          <Card style={styles.oversightErrorCard}>
            <View style={styles.errorIconCircle}>
              <Feather name="refresh-cw" size={20} color="#DC2626" />
            </View>
            <Text style={styles.errorCardTitle}>Could not load child profiles</Text>
            <Text style={styles.errorCardSub}>
              Unable to sync live child accounts. Please tap retry to refresh.
            </Text>
            <Button
              label="Retry Sync"
              onPress={() => void query.refetch()}
              variant="secondary"
            />
          </Card>
        ) : children.length ? (
          <>
            <View style={styles.sectionHeaderRow}>
              <View style={styles.sectionHeaderLeft}>
                <Text style={styles.sectionHeaderLabel}>CONNECTED PROFILES</Text>
                <View style={styles.sectionCountPill}>
                  <Text style={styles.sectionCountText}>{children.length}</Text>
                </View>
              </View>
            </View>
            {children.map((child) => (
              <ChildCard
                key={child.user_id}
                child={child}
                onPress={() => navigation.navigate('ChildSummary', { childId: child.user_id })}
                onScreenTime={() => navigation.navigate('ScreenTime', { childId: child.user_id })}
                onControls={() => navigation.navigate('ParentControls', { childId: child.user_id })}
                onActivity={() => navigation.navigate('ParentActivity', { childId: child.user_id })}
              />
            ))}
            <Pressable
              accessibilityRole="button"
              onPress={() => navigation.navigate('CreateChild')}
              style={styles.addChildCard}
            >
              <View style={styles.addChildCardPlusWrap}>
                <Feather name="user-plus" size={18} color={colors.brand} />
              </View>
              <View style={styles.flex}>
                <Text style={styles.addChildCardTitle}>Add Another Child</Text>
                <Text style={styles.addChildCardSub}>Configure individual safety shields and screen limits</Text>
              </View>
              <Feather name="chevron-right" size={18} color="#9CA3AF" />
            </Pressable>
          </>
        ) : (
          <Card>
            <View style={styles.emptyChildContainer}>
              <View style={styles.emptyChildBadge}>
                <Feather name="user-plus" size={24} color={colors.brand} />
              </View>
              <Text style={styles.emptyChildTitle}>No Child Accounts Yet</Text>
              <Text style={styles.emptyChildBody}>
                Add your child's profile to activate AI safety monitoring, age-tailored quizzes, and daily screen time limits.
              </Text>
              <Button label="+ Add First Child" onPress={() => navigation.navigate('CreateChild')} />
            </View>
          </Card>
        )}
      </RefreshingScroll>
    </Screen>
  );
}

export function ParentChildSummaryScreen({ navigation, route }: ParentScreenProps<'ChildSummary'>) {
  const { session } = useAuth();
  const client = useQueryClient();
  const query = useDashboard(session?.token);
  const childId = route.params.childId;
  const child = query.data?.children.find((item) => item.user_id === childId);

  const [panel, setPanel] = useState<'password' | null>(null);
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [accountBusy, setAccountBusy] = useState(false);
  const [accountError, setAccountError] = useState('');
  const [accountDone, setAccountDone] = useState('');

  const refreshFamily = () => client.invalidateQueries({ queryKey: parentKeys.dashboard });

  async function submitPassword() {
    if (newPassword.length < 8) {
      setAccountError('The new password must be at least 8 characters.');
      return;
    }
    if (newPassword !== confirmPassword) {
      setAccountError('The new passwords do not match.');
      return;
    }
    // Sensitive action: require a fresh parent device authentication.
    if (!(await ensureParentAuthForAction())) return;
    setAccountBusy(true);
    setAccountError('');
    setAccountDone('');
    try {
      const result = await resetChildPassword(session?.token ?? '', childId, newPassword);
      setNewPassword('');
      setConfirmPassword('');
      setPanel(null);
      setAccountDone(result.message);
      await refreshFamily();
    } catch (err) {
      setAccountError(errorText(err));
    } finally {
      setAccountBusy(false);
    }
  }

  function confirmUnlink() {
    Alert.alert(
      'Unlink Child Account?',
      `This removes ${child?.full_name ?? 'your child'} from your family oversight and deactivates their Kids Mode account. You can contact support to restore it.`,
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Unlink Account', style: 'destructive', onPress: () => void doUnlink() },
      ],
    );
  }

  async function doUnlink() {
    // Sensitive action: require a fresh parent device authentication.
    if (!(await ensureParentAuthForAction())) return;
    setAccountBusy(true);
    setAccountError('');
    setAccountDone('');
    try {
      await unlinkChild(session?.token ?? '', childId);
      await refreshFamily();
      navigation.goBack();
    } catch (err) {
      setAccountError(errorText(err));
    } finally {
      setAccountBusy(false);
    }
  }

  if (query.isPending) return <Screen><LoadingState message="Loading child summary…" /></Screen>;
  if (query.isError) return <Screen><ErrorState message={errorText(query.error)} onRetry={() => void query.refetch()} /></Screen>;
  if (!child) return <Screen><EmptyState title="Child unavailable" body="This child is not linked to your active parent account." /></Screen>;

  const limitMinutes = child.limit?.daily_limit_minutes ?? 60;
  // Guard: malformed minutes_today would produce a NaN ratio and a broken
  // "NaN%" gauge width. Coerce to 0.
  const rawUsageRatio = Math.min(child.minutes_today / Math.max(limitMinutes, 1), 1);
  const usageRatio = Number.isFinite(rawUsageRatio) ? rawUsageRatio : 0;
  const isOnline = Boolean(child.presence?.online);

  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.refreshScrollContent}>
        {/* Child Profile Header Card */}
        <View style={styles.summaryProfileCard}>
          <View style={styles.summaryProfileTopRow}>
            <View style={styles.avatarWrapper}>
              <Avatar uri={child.avatar_url} size={56} />
              <View
                style={[
                  styles.presenceIndicatorLarge,
                  isOnline ? styles.onlineIndicator : styles.offlineIndicator,
                ]}
              />
            </View>
            <View style={styles.flex}>
              <View style={styles.childNameRow}>
                <Text style={styles.summaryProfileName}>{child.full_name}</Text>
                {child.age ? (
                  <View style={styles.agePill}>
                    <Text style={styles.agePillText}>Age {child.age}</Text>
                  </View>
                ) : null}
              </View>
              <Text style={styles.childHandleText}>@{child.username}</Text>
              <View style={styles.summaryStatusRow}>
                <View style={[styles.statusDot, isOnline ? styles.onlineDot : styles.offlineDot]} />
                <Text style={styles.summaryStatusText}>{isOnline ? 'Active on LittleNet' : 'Offline'}</Text>
              </View>
            </View>
          </View>
        </View>

        {/* 2x2 Stats Grid — honest labels: screen time is today, quiz is 7-day */}
        <Text style={styles.sectionHeaderLabelStandalone}>SAFETY & USAGE OVERVIEW</Text>
        <View style={styles.statsGrid2x2}>
          {/* Screen Time Stat */}
          <View style={styles.gridStatCard}>
            <View style={[styles.statIconBadge, { backgroundColor: '#EFF6FF' }]}>
              <Feather name="clock" size={16} color="#2563EB" />
            </View>
            <Text style={styles.gridStatNumber}>{child.minutes_today}m</Text>
            <Text style={styles.gridStatLabel}>Today · of {limitMinutes}m limit</Text>
            <View style={styles.gridUsageTrack}>
              <View
                style={[
                  styles.usageFill,
                  usageRatio >= 1 ? styles.usageDanger : usageRatio >= 0.8 ? styles.usageWarning : null,
                  { width: `${Math.max(usageRatio * 100, 4)}%` },
                ]}
              />
            </View>
          </View>

          {/* Safety Shield Stat */}
          <View style={styles.gridStatCard}>
            <View style={[styles.statIconBadge, { backgroundColor: '#ECFDF5' }]}>
              <Feather name="shield" size={16} color="#059669" />
            </View>
            <Text style={styles.gridStatNumber}>{child.safety?.safety_level ?? 'STRICT'}</Text>
            <Text style={styles.gridStatLabel}>AI Content Shield</Text>
            <Text style={styles.gridStatSub}>Active Real-Time</Text>
          </View>

          {/* Quiz Score Stat */}
          <View style={styles.gridStatCard}>
            <View style={[styles.statIconBadge, { backgroundColor: '#F5F3FF' }]}>
              <Feather name="award" size={16} color="#7C3AED" />
            </View>
            <Text style={styles.gridStatNumber}>{child.quiz_7d?.accuracy ?? 0}%</Text>
            <Text style={styles.gridStatLabel}>Quiz Mastery · 7 days</Text>
            <Text style={styles.gridStatSub}>{child.quiz_7d?.correct ?? 0} of {child.quiz_7d?.attempted ?? 0} correct</Text>
          </View>

          {/* Behavior / Well-being Stat */}
          <View style={styles.gridStatCard}>
            <View style={[styles.statIconBadge, { backgroundColor: '#FEF3C7' }]}>
              <Feather name="smile" size={16} color="#D97706" />
            </View>
            <Text style={styles.gridStatNumber}>{child.behavior?.level ?? 'STABLE'}</Text>
            <Text style={styles.gridStatLabel}>Behavior Trend</Text>
            <Text style={styles.gridStatSub}>{child.behavior?.trend ?? 'Healthy balance'}</Text>
          </View>
        </View>

        {/* Quick Management Tiles */}
        <Text style={styles.sectionHeaderLabelStandalone}>MANAGE CHILD CONTROLS</Text>
        <View style={styles.actionTilesGroup}>
          <Pressable
            accessibilityRole="button"
            style={styles.actionTileRow}
            onPress={() => navigation.navigate('ScreenTime', { childId: child.user_id })}
          >
            <View style={[styles.menuIconBadge, { backgroundColor: '#EFF6FF' }]}>
              <Feather name="clock" size={20} color="#2563EB" />
            </View>
            <View style={styles.flex}>
              <Text style={styles.menuTitle}>Screen Time & Daily Limits</Text>
              <Text style={styles.muted}>Configure daily minute allowance and strict lockouts</Text>
            </View>
            <Feather name="chevron-right" size={18} color="#9CA3AF" />
          </Pressable>

          <Pressable
            accessibilityRole="button"
            style={styles.actionTileRow}
            onPress={() => navigation.navigate('ParentControls', { childId: child.user_id })}
          >
            <View style={[styles.menuIconBadge, { backgroundColor: '#EEF2FF' }]}>
              <Feather name="sliders" size={20} color="#4F46E5" />
            </View>
            <View style={styles.flex}>
              <Text style={styles.menuTitle}>Feature & Routine Controls</Text>
              <Text style={styles.muted}>Permissions, quiet hours, and allowed content topics</Text>
            </View>
            <Feather name="chevron-right" size={18} color="#9CA3AF" />
          </Pressable>

          <Pressable
            accessibilityRole="button"
            style={styles.actionTileRow}
            onPress={() => navigation.navigate('ParentSafety')}
          >
            <View style={[styles.menuIconBadge, { backgroundColor: '#FEF2F2' }]}>
              <Feather name="shield" size={20} color="#DC2626" />
            </View>
            <View style={styles.flex}>
              <Text style={styles.menuTitle}>Safety & Moderation Reviews</Text>
              <Text style={styles.muted}>{child.open_reviews ? `${child.open_reviews} items need your decision` : 'Safety queue clear'}</Text>
            </View>
            <Feather name="chevron-right" size={18} color="#9CA3AF" />
          </Pressable>

          <Pressable
            accessibilityRole="button"
            style={[styles.actionTileRow, { borderBottomWidth: 0 }]}
            onPress={() => navigation.navigate('ParentActivity', { childId: child.user_id })}
          >
            <View style={[styles.menuIconBadge, { backgroundColor: '#F5F3FF' }]}>
              <Feather name="activity" size={20} color="#7C3AED" />
            </View>
            <View style={styles.flex}>
              <Text style={styles.menuTitle}>Activity History & Logs</Text>
              <Text style={styles.muted}>View chronological safety and account events</Text>
            </View>
            <Feather name="chevron-right" size={18} color="#9CA3AF" />
          </Pressable>
        </View>

        {/* Child Account Management */}
        <Text style={styles.sectionHeaderLabelStandalone}>CHILD ACCOUNT</Text>
        <View style={styles.actionTilesGroup}>
          <Pressable
            accessibilityRole="button"
            style={styles.actionTileRow}
            onPress={() => setPanel(panel === 'password' ? null : 'password')}
          >
            <View style={[styles.menuIconBadge, { backgroundColor: '#EFF6FF' }]}>
              <Feather name="lock" size={20} color="#2563EB" />
            </View>
            <View style={styles.flex}>
              <Text style={styles.menuTitle}>Reset Child Password</Text>
              <Text style={styles.muted}>Set a new 8+ character sign-in password</Text>
            </View>
            <Feather name={panel === 'password' ? 'chevron-down' : 'chevron-right'} size={18} color="#9CA3AF" />
          </Pressable>
          {panel === 'password' ? (
            <View style={styles.accountPanel}>
              <Field
                label="New password (min 8)"
                placeholder="Minimum 8 characters"
                secureTextEntry
                autoCapitalize="none"
                autoCorrect={false}
                value={newPassword}
                onChangeText={setNewPassword}
              />
              <Field
                label="Confirm new password"
                placeholder="Repeat the new password"
                secureTextEntry
                autoCapitalize="none"
                autoCorrect={false}
                value={confirmPassword}
                onChangeText={setConfirmPassword}
              />
              <Button
                label={accountBusy ? 'Saving…' : 'Set New Password'}
                loading={accountBusy}
                disabled={accountBusy}
                onPress={() => void submitPassword()}
              />
            </View>
          ) : null}

          <Pressable
            accessibilityRole="button"
            style={[styles.actionTileRow, { borderBottomWidth: 0 }]}
            onPress={confirmUnlink}
            disabled={accountBusy}
          >
            <View style={[styles.menuIconBadge, { backgroundColor: '#FEF2F2' }]}>
              <Feather name="user-x" size={20} color="#DC2626" />
            </View>
            <View style={styles.flex}>
              <Text style={[styles.menuTitle, styles.dangerText]}>Unlink Child Account</Text>
              <Text style={styles.muted}>Remove from your family and deactivate Kids Mode</Text>
            </View>
            <Feather name="chevron-right" size={18} color="#9CA3AF" />
          </Pressable>

          {accountError ? (
            <View style={styles.accountNoticeWrap}>
              <Notice message={accountError} />
            </View>
          ) : null}
          {accountDone ? (
            <View style={styles.accountNoticeWrap}>
              <Notice tone="ok" message={accountDone} />
            </View>
          ) : null}
        </View>
      </ScrollView>
    </Screen>
  );
}

export function ParentSafetyScreen({ navigation }: ParentScreenProps<'ParentSafety'>) {
  const { session } = useAuth();
  const query = useQuery({ queryKey: parentKeys.safety, queryFn: () => fetchParentSafety(session?.token ?? ''), enabled: Boolean(session) });
  const events = query.data?.events ?? [];

  return (
    <Screen>
      <FlatList
        data={events}
        keyExtractor={(event) => String(event.event_id)}
        contentContainerStyle={styles.refreshScrollContent}
        refreshControl={<RefreshControl refreshing={query.isRefetching} onRefresh={() => void query.refetch()} />}
        ListHeaderComponent={
          <SubScreenHero
            kicker="Controls & Supervision"
            title="Safety Review Queue"
            subtitle="Flagged content and media held in private quarantine pending your decision."
            icon="shield"
            iconColor="#DC2626"
            iconBg="#FEF2F2"
          />
        }
        ListEmptyComponent={
          query.isPending ? (
            <LoadingState message="Checking safety review queue…" />
          ) : query.isError ? (
            <ErrorState message={errorText(query.error)} onRetry={() => void query.refetch()} />
          ) : (
            <Card>
              <View style={styles.emptyChildContainer}>
                <View style={[styles.emptyChildBadge, { backgroundColor: '#ECFDF5' }]}>
                  <Feather name="shield" size={24} color="#059669" />
                </View>
                <Text style={styles.emptyChildTitle}>Review Queue Clear</Text>
                <Text style={styles.emptyChildBody}>
                  No posts, comments, or media currently require parental review. All child activity meets LittleNet's safety standards.
                </Text>
              </View>
            </Card>
          )
        }
        renderItem={({ item: event }) => (
          <Pressable
            accessibilityRole="button"
            style={styles.safetyCard}
            onPress={() => navigation.navigate('ParentReview', { eventId: event.event_id })}
          >
            <View style={styles.safetyCardHeader}>
              <RiskBadge score={event.risk_score} />
              <TimeAgo value={event.created_at} />
            </View>
            <Text style={styles.safetyChildName}>{event.full_name ?? 'Your Child'}</Text>
            <View style={styles.safetyReasonBox}>
              <Feather name="alert-triangle" size={14} color="#D97706" style={{ marginTop: 2 }} />
              <Text style={styles.safetyReasonText}>{event.reason || 'LittleNet AI detected content that requires parental review.'}</Text>
            </View>
            <View style={styles.safetyCardFooter}>
              <Text style={styles.safetyFooterMeta}>
                Type: {event.preview?.media_type ? humanize(event.preview.media_type) : 'Text Summary'} · Status: {humanize(event.status)}
              </Text>
              <View style={styles.safetyReviewPrompt}>
                <Text style={styles.safetyPromptText}>Decide</Text>
                <Feather name="chevron-right" size={14} color={colors.brand} />
              </View>
            </View>
          </Pressable>
        )}
      />
    </Screen>
  );
}

/** Risk scores at or above this are shown blurred until the parent reveals them. */
const HIGH_RISK_THRESHOLD = 0.7;

/**
 * Controlled quarantine video player (expo-video, the project's video
 * component). No autoplay: playback starts only from the explicit play
 * gesture, then native controls provide play/pause/seek.
 */
function ReviewVideo({ mediaUrl, posterUrl, token }: { mediaUrl: string; posterUrl?: string | null; token: string }) {
  const player = useVideoPlayer(
    { uri: mediaUrl, headers: { Authorization: `Bearer ${token}` } },
    (instance) => {
      instance.loop = false;
    },
  );
  const [started, setStarted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const subscription = player.addListener('statusChange', ({ status, error: playbackError }) => {
      if (status === 'error') setError(playbackError?.message ?? 'This video could not play.');
    });
    return () => subscription.remove();
  }, [player]);

  // Never autoplay; pause on unmount so audio can't leak past navigation.
  useEffect(() => () => player.pause(), [player]);

  function start() {
    setStarted(true);
    setError(null);
    try {
      player.play();
    } catch {
      setError('This video could not play.');
    }
  }

  return (
    <View style={styles.reviewVideoShell}>
      <NativeVideoView
        player={player}
        style={styles.reviewVideo}
        contentFit="contain"
        nativeControls={started}
        onFirstFrameRender={() => setStarted(true)}
      />
      {!started ? (
        <Pressable
          style={styles.reviewVideoVeil}
          onPress={start}
          accessibilityRole="button"
          accessibilityLabel="Play quarantined video"
        >
          {posterUrl ? (
            <Image
              source={{ uri: posterUrl, headers: { Authorization: `Bearer ${token}` } }}
              style={styles.reviewVideoPoster}
              resizeMode="cover"
            />
          ) : null}
          <View style={styles.reviewVideoPlayBadge}>
            <Feather name="play" size={28} color="#FFFFFF" />
          </View>
          <Text style={styles.reviewVideoHint}>Tap to play — stays paused until you do</Text>
        </Pressable>
      ) : null}
      {error ? (
        <View style={styles.reviewVideoError}>
          <Text style={styles.reviewVideoErrorText}>{error}</Text>
        </View>
      ) : null}
    </View>
  );
}

/** High-risk quarantined images render blurred until the parent explicitly reveals them (confirm step). */
function ReviewImage({ imageUrl, token, riskScore }: { imageUrl: string; token: string; riskScore?: number | string | null }) {
  const numeric = Number(riskScore);
  const highRisk = Number.isFinite(numeric) && numeric >= HIGH_RISK_THRESHOLD;
  const [revealed, setRevealed] = useState(false);
  const blurred = highRisk && !revealed;

  function requestReveal() {
    if (!blurred) return;
    Alert.alert(
      'Reveal this image?',
      'This image was quarantined as high risk. Reveal it only if you are comfortable viewing it.',
      [
        { text: 'Keep hidden', style: 'cancel' },
        { text: 'Reveal', onPress: () => setRevealed(true) },
      ],
    );
  }

  return (
    <View>
      <Pressable
        onPress={requestReveal}
        disabled={!blurred}
        accessibilityRole={blurred ? 'button' : undefined}
        accessibilityLabel={blurred ? 'Reveal quarantined image' : 'Quarantined image'}
      >
        <Image
          source={{ uri: imageUrl, headers: { Authorization: `Bearer ${token}` } }}
          resizeMode="cover"
          style={styles.reviewImage}
          blurRadius={blurred ? 28 : 0}
        />
        {blurred ? (
          <View style={styles.blurVeil} pointerEvents="none">
            <Feather name="eye-off" size={26} color="#FFFFFF" />
            <Text style={styles.blurTitle}>Sensitive content hidden</Text>
            <Text style={styles.blurBody}>High-risk image held in quarantine. Tap to review it.</Text>
          </View>
        ) : null}
      </Pressable>
      {revealed && highRisk ? (
        <Pressable
          onPress={() => setRevealed(false)}
          style={styles.rehide}
          accessibilityRole="button"
          accessibilityLabel="Hide image again"
        >
          <Feather name="eye-off" size={14} color={colors.muted} />
          <Text style={styles.rehideText}>Hide again</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

function ReviewMedia({ preview, token, riskScore }: { preview?: ReviewPreview | null; token: string; riskScore?: number | string | null }) {
  const mediaType = (preview?.media_type ?? '').toUpperCase();
  const imageUrl = mediaType === 'IMAGE' ? preview?.media_url : preview?.poster_url;
  if (mediaType === 'VIDEO' && preview?.media_url) {
    return <ReviewVideo mediaUrl={preview.media_url} posterUrl={preview?.poster_url} token={token} />;
  }
  if (imageUrl) {
    if (mediaType === 'IMAGE') return <ReviewImage imageUrl={imageUrl} token={token} riskScore={riskScore} />;
    // Video poster without playable media: unchanged thumbnail behavior.
    return <Image source={{ uri: imageUrl, headers: { Authorization: `Bearer ${token}` } }} resizeMode="cover" style={styles.reviewImage} />;
  }
  if (preview?.media_url) return <Notice tone="info" message="This video remains in the private review area. Use its moderation summary for this decision." />;
  return null;
}

export function ParentReviewScreen({ navigation, route }: ParentScreenProps<'ParentReview'>) {
  const { session } = useAuth();
  const client = useQueryClient();
  const query = useQuery({ queryKey: parentKeys.safety, queryFn: () => fetchParentSafety(session?.token ?? ''), enabled: Boolean(session) });
  const event = query.data?.events.find((item) => item.event_id === route.params.eventId);
  const mutation = useMutation({
    mutationFn: (action: 'APPROVE' | 'BLOCK') => resolveParentReview(session?.token ?? '', route.params.eventId, action),
    onSuccess: async () => {
      await Promise.all([client.invalidateQueries({ queryKey: parentKeys.safety }), client.invalidateQueries({ queryKey: parentKeys.dashboard })]);
      navigation.goBack();
    },
  });

  if (query.isPending) return <Screen><LoadingState message="Loading review details…" /></Screen>;
  if (query.isError) return <Screen><ErrorState message={errorText(query.error)} onRetry={() => void query.refetch()} /></Screen>;
  if (!event) return <Screen><EmptyState title="Review unavailable" body="It may already be resolved or no longer belongs to your queue." /></Screen>;

  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.refreshScrollContent}>
        {/* Quarantine notice banner */}
        <View style={styles.quarantineReviewBanner}>
          <Feather name="lock" size={16} color="#38BDF8" />
          <Text style={styles.quarantineBannerText}>QUARANTINE PREVIEW • Private Parent Decision</Text>
        </View>

        <Card>
          <View style={styles.rowBetween}>
            <CategoryBadge label={event.content_type} />
            <TimeAgo value={event.created_at} />
          </View>
          <Text style={styles.reviewChildTitle}>{event.full_name ?? 'Your Child'}</Text>

          <ReviewMedia preview={event.preview} token={session?.token ?? ''} riskScore={event.risk_score} />

          {event.preview?.caption ? (
            <View style={styles.quotedContentBox}>
              <Text style={styles.quotedContentText}>{event.preview.caption}</Text>
            </View>
          ) : null}
          {event.preview?.comment_text ? (
            <View style={styles.quotedContentBox}>
              <Text style={styles.quotedContentText}>{event.preview.comment_text}</Text>
            </View>
          ) : null}
          {event.preview?.message_text ? (
            <View style={styles.quotedContentBox}>
              <Text style={styles.quotedContentText}>{event.preview.message_text}</Text>
            </View>
          ) : null}

          <View style={styles.reviewFlagSection}>
            <View style={styles.reviewFlagRow}>
              <Text style={styles.reviewFlagLabel}>Flag Reason:</Text>
              <Text style={styles.reviewFlagValue}>{event.reason || 'Held for parent approval'}</Text>
            </View>
            <View style={styles.reviewFlagRow}>
              <Text style={styles.reviewFlagLabel}>Risk Score:</Text>
              <RiskBadge score={event.risk_score} />
            </View>
          </View>

          {mutation.error ? <Notice message={errorText(mutation.error)} /> : null}

          <View style={styles.reviewActionButtonsRow}>
            <View style={styles.flex}>
              <Button
                label="Approve Safely"
                loading={mutation.isPending}
                onPress={() => {
                  void (async () => {
                    if (await ensureParentAuthForAction()) mutation.mutate('APPROVE');
                  })();
                }}
              />
            </View>
            <View style={styles.flex}>
              <Button
                label="Block & Remove"
                variant="secondary"
                disabled={mutation.isPending}
                onPress={() => {
                  void (async () => {
                    if (await ensureParentAuthForAction()) mutation.mutate('BLOCK');
                  })();
                }}
              />
            </View>
          </View>
        </Card>
      </ScrollView>
    </Screen>
  );
}

function SelectChild({ children, onPick }: { children: ParentChild[]; onPick: (id: number) => void }) {
  return (
    <>
      <View style={styles.sectionHeaderRow}>
        <View style={styles.sectionHeaderLeft}>
          <Text style={styles.sectionHeaderLabel}>SELECT A CHILD PROFILE</Text>
        </View>
      </View>
      {children.map((child) => (
        <ChildCard key={child.user_id} child={child} onPress={() => onPick(child.user_id)} />
      ))}
    </>
  );
}

export function ParentScreenTimeScreen({ route }: ParentScreenProps<'ScreenTime'>) {
  const { session } = useAuth();
  const client = useQueryClient();
  const dashboard = useDashboard(session?.token);
  const [childId, setChildId] = useState<number | null>(route.params?.childId ?? null);
  const child = dashboard.data?.children.find((item) => item.user_id === childId);
  const [minutes, setMinutes] = useState('60');
  const [strict, setStrict] = useState(true);

  useEffect(() => {
    if (child?.limit) {
      setMinutes(String(child.limit.daily_limit_minutes));
      setStrict(child.limit.strict_mode);
    }
  }, [child?.limit?.daily_limit_minutes, child?.limit?.strict_mode]);

  const mutation = useMutation({
    mutationFn: () => updateTimeLimit(session?.token ?? '', childId ?? 0, Number(minutes), strict),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: parentKeys.dashboard });
    },
  });

  const resetMutation = useMutation({
    mutationFn: () => resetChildScreenTime(session?.token ?? '', childId ?? 0),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: parentKeys.dashboard });
      Alert.alert(
        'Screen Time Reset! 🎉',
        `Today's usage for ${child?.full_name ?? 'your child'} has been reset to 0 minutes. LittleNet is now unlocked for them.`,
      );
    },
    onError: (err) => {
      Alert.alert('Reset Failed', errorText(err));
    },
  });

  const extendMutation = useMutation({
    mutationFn: (extra: number) => extendChildScreenTime(session?.token ?? '', childId ?? 0, extra),
    onSuccess: async (data, extra) => {
      await client.invalidateQueries({ queryKey: parentKeys.dashboard });
      setMinutes(String(data.daily_limit_minutes));
      Alert.alert(
        'Time Extended! ✨',
        `Added ${extra} minutes. New daily allowance is ${data.daily_limit_minutes} minutes. Kids Mode is now unlocked.`,
      );
    },
    onError: (err) => {
      Alert.alert('Extension Failed', errorText(err));
    },
  });

  if (!childId) {
    return (
      <Screen>
        <ScrollView contentContainerStyle={styles.refreshScrollContent}>
          <SubScreenHero
            kicker="Controls & Supervision"
            title="Daily Screen Time"
            subtitle="Choose a child to view today's usage and configure daily minute limits."
            icon="clock"
            iconColor="#059669"
            iconBg="#ECFDF5"
          />
          <AsyncBody query={dashboard}>
            {dashboard.data?.children.length ? (
              <SelectChild children={dashboard.data.children} onPick={setChildId} />
            ) : (
              <Card>
                <View style={styles.emptyChildContainer}>
                  <View style={styles.emptyChildBadge}>
                    <Feather name="users" size={24} color={colors.brand} />
                  </View>
                  <Text style={styles.emptyChildTitle}>No Children Added Yet</Text>
                  <Text style={styles.emptyChildBody}>
                    Create a child account to set daily screen time allowances.
                  </Text>
                </View>
              </Card>
            )}
          </AsyncBody>
        </ScrollView>
      </Screen>
    );
  }

  if (dashboard.isPending) return <Screen><LoadingState message="Loading screen time…" /></Screen>;
  if (dashboard.isError) return <Screen><ErrorState message={errorText(dashboard.error)} onRetry={() => void dashboard.refetch()} /></Screen>;
  if (!child) return <Screen><EmptyState title="Child not found" body="This child is no longer on your dashboard. Pick another child to manage screen time." actionLabel="Choose another child" onAction={() => setChildId(null)} /></Screen>;

  const valid = Number.isInteger(Number(minutes)) && Number(minutes) >= 1 && Number(minutes) <= 1440;
  const limit = Number(minutes);
  // Guard: malformed minutes_today would produce a NaN ratio and a broken
  // "NaN%" gauge width. Coerce to 0.
  const rawUsage = Math.min(child.minutes_today / Math.max(limit, 1), 1);
  const usage = Number.isFinite(rawUsage) ? rawUsage : 0;
  const isLimitReached = Boolean(child.limit?.strict_mode && child.minutes_today >= limit);
  const presets = ['30', '45', '60', '90', '120'];

  return (
    <Screen>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 88 : 0}
        style={styles.flex}
      >
        <ScrollView
          keyboardShouldPersistTaps="handled"
          keyboardDismissMode="on-drag"
          contentContainerStyle={styles.formScrollContent}
        >
          <SubScreenHero
            kicker={child.full_name}
            title="Daily Screen Time"
            subtitle="Server-enforced screen allowance. Automatically pauses Kids Mode when limits are reached."
            icon="clock"
            iconColor="#059669"
            iconBg="#ECFDF5"
          />

          {/* Limit Reached Warning Card */}
          {isLimitReached ? (
            <View style={styles.limitAlertBox}>
              <View style={styles.limitAlertHeader}>
                <Feather name="alert-triangle" size={18} color="#DC2626" />
                <Text style={styles.limitAlertTitle}>Screen-Time Limit Reached Today</Text>
              </View>
              <Text style={styles.limitAlertBody}>
                {child.full_name} has consumed all {limit} minutes today and Kids Mode is currently locked. Use the quick controls below to reset or grant extra time.
              </Text>
            </View>
          ) : null}

          {/* Usage Gauge Card */}
          <Card>
            <View style={styles.usageSummary}>
              <View style={styles.usageTopRow}>
                <View>
                  <Text style={[styles.usageNumber, isLimitReached && styles.usageDangerText]}>
                    {child.minutes_today}
                  </Text>
                  <Text style={styles.muted}>minutes used today</Text>
                </View>
                <View style={[styles.allowancePill, isLimitReached && { backgroundColor: '#FEF2F2' }]}>
                  <Text style={[styles.allowancePillText, isLimitReached && { color: '#DC2626' }]}>
                    {limit || '—'} min daily allowance
                  </Text>
                </View>
              </View>
              <View style={styles.largeUsageTrack}>
                <View
                  style={[
                    styles.usageFill,
                    usage >= 1 || isLimitReached ? styles.usageDanger : usage >= 0.8 ? styles.usageWarning : null,
                    { width: `${Math.max(usage * 100, 3)}%` },
                  ]}
                />
              </View>
              <Text style={[styles.usagePercentText, isLimitReached && styles.usageDangerText]}>
                {isLimitReached
                  ? '100% of daily allowance consumed (Account Locked)'
                  : `${Math.round(usage * 100)}% of daily allowance consumed`}
              </Text>
            </View>

            {/* Quick Extension & Reset Section */}
            <View style={styles.resetSectionWrap}>
              <Text style={styles.presetHeading}>QUICK EXTENSION & RESET</Text>
              <View style={styles.extensionRow}>
                {[15, 30, 60].map((extra) => (
                  <Pressable
                    key={extra}
                    disabled={extendMutation.isPending || resetMutation.isPending}
                    onPress={() => {
                      void (async () => {
                        if (await ensureParentAuthForAction()) extendMutation.mutate(extra);
                      })();
                    }}
                    style={styles.extensionBtn}
                  >
                    <Feather name="plus-circle" size={13} color="#2563EB" />
                    <Text style={styles.extensionBtnText}>+{extra}m</Text>
                  </Pressable>
                ))}
              </View>

              <Pressable
                disabled={resetMutation.isPending || extendMutation.isPending}
                onPress={() => {
                  Alert.alert(
                    'Reset Today’s Screen Time?',
                    `Reset screen time for ${child.full_name}? Today's usage will be set back to 0 minutes and Kids Mode will unlock immediately.`,
                    [
                      { text: 'Cancel', style: 'cancel' },
                      {
                        text: 'Reset Now',
                        style: 'destructive',
                        onPress: () => {
                          void (async () => {
                            if (await ensureParentAuthForAction()) resetMutation.mutate();
                          })();
                        },
                      },
                    ],
                  );
                }}
                style={styles.resetTimeBtn}
              >
                {resetMutation.isPending ? (
                  <ActivityIndicator size="small" color="#DC2626" />
                ) : (
                  <>
                    <Feather name="rotate-ccw" size={15} color="#DC2626" />
                    <Text style={styles.resetTimeBtnText}>Reset Today's Time to 0m</Text>
                  </>
                )}
              </Pressable>
            </View>

            {/* Quick Presets */}
            <Text style={styles.presetHeading}>SET DAILY BASE LIMIT</Text>
            <View style={styles.presetsRow}>
              {presets.map((preset) => {
                const isSelected = minutes === preset;
                return (
                  <Pressable
                    key={preset}
                    onPress={() => setMinutes(preset)}
                    style={[styles.presetButton, isSelected && styles.presetButtonActive]}
                  >
                    <Text style={[styles.presetButtonText, isSelected && styles.presetButtonTextActive]}>
                      {preset}m
                    </Text>
                  </Pressable>
                );
              })}
            </View>

            <Field
              label="Custom Limit in Minutes (1–1440)"
              value={minutes}
              onChangeText={setMinutes}
              keyboardType="number-pad"
              error={valid ? undefined : 'Enter a whole number from 1 to 1440.'}
            />

            <Toggle
              label="Strict Lockout"
              body="Locks Kids Mode immediately once the daily allowance is exhausted."
              value={strict}
              onChange={setStrict}
            />

            {mutation.isSuccess ? <Notice tone="ok" message="Screen-time limit saved and active." /> : null}
            {mutation.error ? <Notice message={errorText(mutation.error)} /> : null}

            <Button
              label="Save Screen Time"
              disabled={!valid}
              loading={mutation.isPending}
              onPress={() => {
                void (async () => {
                  if (await ensureParentAuthForAction()) mutation.mutate();
                })();
              }}
            />
          </Card>

          <View style={styles.bottomInfoCard}>
            <Feather name="shield" size={16} color="#0284C7" />
            <Text style={styles.bottomInfoText}>
              Overnight bedtime windows and strict time allowances remain enforced by LittleNet backend servers even if the device restarts.
            </Text>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}

function Toggle({ label, body, value, onChange }: { label: string; body: string; value: boolean; onChange: (value: boolean) => void }) {
  return (
    <View style={styles.toggle}>
      <View style={styles.flex}>
        <Text style={styles.rowTitle}>{label}</Text>
        <Text style={styles.muted}>{body}</Text>
      </View>
      <Switch accessibilityLabel={label} value={value} onValueChange={onChange} trackColor={{ true: colors.brand }} />
    </View>
  );
}

export function ParentControlsScreen({ route }: ParentScreenProps<'ParentControls'>) {
  const { session } = useAuth();
  const client = useQueryClient();
  const dashboard = useDashboard(session?.token);
  const [childId, setChildId] = useState<number | null>(route.params?.childId ?? null);
  const child = dashboard.data?.children.find((item) => item.user_id === childId);
  const query = useQuery({
    queryKey: parentKeys.controls(childId ?? 0),
    queryFn: () => fetchParentControls(session?.token ?? '', childId ?? 0),
    enabled: Boolean(session && childId),
  });
  const [draft, setDraft] = useState<ParentControls | null>(null);

  useEffect(() => {
    if (query.data?.controls) setDraft(query.data.controls);
  }, [query.data?.controls]);

  const mutation = useMutation({
    mutationFn: () => updateParentControls(session?.token ?? '', childId ?? 0, draft!),
    onSuccess: async (data) => {
      setDraft(data.controls);
      await Promise.all([
        client.invalidateQueries({ queryKey: parentKeys.dashboard }),
        client.invalidateQueries({ queryKey: parentKeys.controls(childId ?? 0) }),
      ]);
    },
  });

  if (!childId) {
    return (
      <Screen>
        <ScrollView contentContainerStyle={styles.refreshScrollContent}>
          <SubScreenHero
            kicker="Controls & Supervision"
            title="Feature Controls"
            subtitle="Choose a child to configure permissions, quiet hours, and allowed topics."
            icon="sliders"
            iconColor="#4F46E5"
            iconBg="#EEF2FF"
          />
          <AsyncBody query={dashboard}>
            {dashboard.data?.children.length ? (
              <SelectChild children={dashboard.data.children} onPick={setChildId} />
            ) : (
              <Card>
                <View style={styles.emptyChildContainer}>
                  <View style={styles.emptyChildBadge}>
                    <Feather name="users" size={24} color={colors.brand} />
                  </View>
                  <Text style={styles.emptyChildTitle}>No Children Added Yet</Text>
                  <Text style={styles.emptyChildBody}>
                    Create a child account to configure feature permissions and bedtime windows.
                  </Text>
                </View>
              </Card>
            )}
          </AsyncBody>
        </ScrollView>
      </Screen>
    );
  }

  if (query.isPending || !draft) return <Screen><LoadingState message="Loading controls…" /></Screen>;
  if (query.isError) return <Screen><ErrorState message={errorText(query.error)} onRetry={() => void query.refetch()} /></Screen>;

  const set = <K extends keyof ParentControls>(key: K, value: ParentControls[K]) =>
    setDraft((current) => (current ? { ...current, [key]: value } : current));

  const featureRows: Array<[keyof ParentControls, string, string, FeatherIconName, string]> = [
    ['allow_reels', 'Short-form Reels', 'Educational & fun short video feeds', 'film', '#2563EB'],
    ['allow_stories', '24-hour Stories', 'Disappearing updates from approved friends', 'clock', '#7C3AED'],
    ['allow_messaging', 'Direct Messages', 'Private chat with two-parent approved friends', 'message-circle', '#059669'],
    ['allow_posting', 'Media Creation', 'Capture and upload photos and videos', 'camera', '#D97706'],
    ['allow_discover', 'Discover & Explore', 'Content exploration and search', 'compass', '#DB2777'],
    ['allow_comments', 'Social Comments', 'Allow moderated comments on approved social posts', 'message-square', '#0F766E'],
  ];

  return (
    <Screen>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 88 : 0}
        style={styles.flex}
      >
        <ScrollView
          keyboardShouldPersistTaps="handled"
          keyboardDismissMode="on-drag"
          contentContainerStyle={styles.formScrollContent}
        >
          <SubScreenHero
            kicker={child?.full_name ?? 'Child'}
            title="Feature Controls"
            subtitle="Permissions take effect instantly on your child's device without re-logging."
            icon="sliders"
            iconColor="#4F46E5"
            iconBg="#EEF2FF"
          />

          <Text style={styles.sectionHeaderLabelStandalone}>SOCIAL & CONTENT ACCESS</Text>
          <Card>
            {featureRows.map(([key, label, body, icon, iconCol], idx) => (
              <View key={key} style={[styles.controlRowItem, idx < featureRows.length - 1 && styles.menuRowBorder]}>
                <View style={[styles.controlIconWrap, { backgroundColor: `${iconCol}15` }]}>
                  <Feather name={icon} size={18} color={iconCol} />
                </View>
                <View style={styles.flex}>
                  <Text style={styles.controlRowTitle}>{label}</Text>
                  <Text style={styles.controlRowSub}>{body}</Text>
                </View>
                <Switch
                  value={Boolean(draft[key])}
                  onValueChange={(val) => set(key, val)}
                  trackColor={{ true: colors.brand }}
                />
              </View>
            ))}
          </Card>

          <Text style={styles.sectionHeaderLabelStandalone}>ROUTINES & QUIET HOURS</Text>
          <Card>
            <Toggle
              label="Educational-Only Feed"
              body="Restrict recommendations strictly to curated learning and STEM topics."
              value={draft.educational_only_feed}
              onChange={(value) => set('educational_only_feed', value)}
            />
            <Toggle
              label="Quiet Hours (Bedtime Window)"
              body="Locks Kids Mode during night or study hours."
              value={draft.quiet_hours_enabled}
              onChange={(value) => set('quiet_hours_enabled', value)}
            />
            <View style={styles.quietHoursInputSection}>
              <Text style={styles.categoryExplainer}>Reel Brain Break pacing</Text>
              <View style={styles.chipsWrap}>
                {([
                  ['FREQUENT', 'Frequent · 2–5 reels'],
                  ['BALANCED', 'Balanced · 4–7 reels'],
                  ['LIGHT', 'Light · 7–10 reels'],
                ] as const).map(([policy, label]) => {
                  const selected = draft.quiz_pacing_policy === policy;
                  return (
                    <Pressable
                      key={policy}
                      accessibilityRole="radio"
                      accessibilityState={{ selected }}
                      style={[styles.categoryPill, selected && styles.categoryPillSelected]}
                      onPress={() => set('quiz_pacing_policy', policy)}
                    >
                      {selected ? <Feather name="check" size={13} color="#FFFFFF" /> : null}
                      <Text style={[styles.categoryPillText, selected && styles.categoryPillTextSelected]}>{label}</Text>
                    </Pressable>
                  );
                })}
              </View>
              <Text style={styles.controlRowSub}>The exact next break remains random and server-persisted. Changing this setting never clears a break that is already required.</Text>
            </View>
            {draft.quiet_hours_enabled ? (
              <View style={styles.quietHoursInputSection}>
                <View style={styles.timeInputsRow}>
                  <View style={styles.flex}>
                    <Field
                      label="Starts (HH:MM)"
                      placeholder="21:00"
                      value={draft.quiet_start}
                      onChangeText={(value) => set('quiet_start', value)}
                    />
                  </View>
                  <View style={styles.flex}>
                    <Field
                      label="Ends (HH:MM)"
                      placeholder="07:00"
                      value={draft.quiet_end}
                      onChangeText={(value) => set('quiet_end', value)}
                    />
                  </View>
                </View>
                <Notice tone="info" message="Example: 21:00 to 07:00 covers the overnight bedtime window." />
              </View>
            ) : null}
          </Card>

          <Text style={styles.sectionHeaderLabelStandalone}>ALLOWED CONTENT CATEGORIES</Text>
          <Card>
            <Text style={styles.categoryExplainer}>
              Select the topics your child is allowed to browse in Reels and Feed:
            </Text>
            <View style={styles.chipsWrap}>
              {(query.data?.categories ?? []).map((category) => {
                const selected = draft.allowed_categories.includes(category);
                return (
                  <Pressable
                    key={category}
                    accessibilityRole="checkbox"
                    accessibilityState={{ checked: selected }}
                    style={[styles.categoryPill, selected && styles.categoryPillSelected]}
                    onPress={() =>
                      set(
                        'allowed_categories',
                        selected
                          ? draft.allowed_categories.filter((item) => item !== category)
                          : [...draft.allowed_categories, category]
                      )
                    }
                  >
                    {selected ? (
                      <Feather name="check" size={13} color="#FFFFFF" />
                    ) : (
                      <Feather name="plus" size={13} color="#64748B" />
                    )}
                    <Text style={[styles.categoryPillText, selected && styles.categoryPillTextSelected]}>
                      {category}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
          </Card>

          {mutation.isSuccess ? <Notice tone="ok" message="Controls successfully saved and active." /> : null}
          {mutation.error ? <Notice message={errorText(mutation.error)} /> : null}

          <View style={{ marginHorizontal: spacing.md, marginBottom: spacing.lg }}>
            <Button
              label="Save Feature Controls"
              disabled={!draft.allowed_categories.length}
              loading={mutation.isPending}
              onPress={() => {
                void (async () => {
                  if (await ensureParentAuthForAction()) mutation.mutate();
                })();
              }}
            />
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}

export function ParentFollowRequestsScreen(_props: ParentScreenProps<'FollowRequests'>) {
  const { session } = useAuth();
  const client = useQueryClient();
  const query = useQuery({ queryKey: parentKeys.follows, queryFn: () => fetchFollowRequests(session?.token ?? ''), enabled: Boolean(session) });
  const mutation = useMutation({
    mutationFn: ({ childId, targetId, action }: { childId: number; targetId: number; action: 'approve' | 'reject' }) =>
      resolveFollowRequest(session?.token ?? '', childId, targetId, action),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: parentKeys.follows }),
        client.invalidateQueries({ queryKey: parentKeys.dashboard }),
      ]);
    },
  });
  const rows = query.data?.pending ?? [];

  return (
    <Screen>
      <RefreshingScroll refreshing={query.isRefetching} onRefresh={() => void query.refetch()}>
        <SubScreenHero
          kicker="Community & Account"
          title="Friendship Approvals"
          subtitle="Both families must approve before children can connect or send direct messages."
          icon="user-check"
          iconColor="#DB2777"
          iconBg="#FDF2F8"
        />

        <AsyncBody
          query={query}
          emptyTitle="No Pending Requests"
          emptyBody="Friendship requests between children requiring your approval will appear here."
        >
          {rows.length ? (
            rows.map((row) => (
              <Card key={`${row.child_id}:${row.following_child_id}:${row.approval_stage}`}>
                <View style={styles.rowBetween}>
                  <View style={styles.friendshipStagePill}>
                    <Feather name="shield" size={11} color="#DB2777" />
                    <Text style={styles.friendshipStageText}>{row.approval_direction}</Text>
                  </View>
                  <TimeAgo value={row.created_at} />
                </View>

                <View style={styles.friendshipNamesRow}>
                  <Text style={styles.friendshipName}>{row.requester_name}</Text>
                  <Feather name="arrow-right" size={16} color="#94A3B8" />
                  <Text style={styles.friendshipName}>{row.target_name}</Text>
                </View>

                <Text style={styles.friendshipHelpText}>{row.stage_help}</Text>

                {row.actionable ? (
                  <View style={styles.friendshipActionsRow}>
                    <View style={styles.flex}>
                      <Button
                        label="Approve Friendship"
                        disabled={mutation.isPending}
                        onPress={() => {
                          void (async () => {
                            if (!(await ensureParentAuthForAction())) return;
                            mutation.mutate({
                              childId: row.child_id,
                              targetId: row.following_child_id,
                              action: 'approve',
                            });
                          })();
                        }}
                      />
                    </View>
                    <View style={styles.flex}>
                      <Button
                        label="Decline"
                        variant="secondary"
                        disabled={mutation.isPending}
                        onPress={() => {
                          void (async () => {
                            if (!(await ensureParentAuthForAction())) return;
                            mutation.mutate({
                              childId: row.child_id,
                              targetId: row.following_child_id,
                              action: 'reject',
                            });
                          })();
                        }}
                      />
                    </View>
                  </View>
                ) : (
                  <View style={styles.awaitingOtherParentPill}>
                    <Feather name="clock" size={12} color="#64748B" />
                    <Text style={styles.awaitingOtherParentText}>Awaiting approval from the other parent</Text>
                  </View>
                )}
              </Card>
            ))
          ) : (
            <Card>
              <View style={styles.emptyChildContainer}>
                <View style={[styles.emptyChildBadge, { backgroundColor: '#FDF2F8' }]}>
                  <Feather name="user-check" size={24} color="#DB2777" />
                </View>
                <Text style={styles.emptyChildTitle}>No Follow Approvals Pending</Text>
                <Text style={styles.emptyChildBody}>
                  When your child adds a classmate or friend, both sets of parents receive a mutual consent request here.
                </Text>
              </View>
            </Card>
          )}
        </AsyncBody>
        {mutation.error ? <Notice message={errorText(mutation.error)} /> : null}
      </RefreshingScroll>
    </Screen>
  );
}

export function ParentActivityScreen({ route }: ParentScreenProps<'ParentActivity'>) {
  const { session } = useAuth();
  const dashboard = useDashboard(session?.token);
  const [childId, setChildId] = useState<number | null>(route.params?.childId ?? null);
  const child = dashboard.data?.children.find((item) => item.user_id === childId);
  const query = useQuery({
    queryKey: parentKeys.activity(childId ?? 0),
    queryFn: () => fetchParentActivity(session?.token ?? '', childId ?? 0),
    enabled: Boolean(session && childId),
  });
  const [moreEvents, setMoreEvents] = useState<Array<{ log_id: number; activity_type: string; activity_data?: Record<string, unknown>; created_at?: string }>>([]);
  const [moreCursor, setMoreCursor] = useState<number | null>(null);
  const [moreHasMore, setMoreHasMore] = useState<boolean | null>(null);
  const [loadingMoreActivity, setLoadingMoreActivity] = useState(false);

  useEffect(() => {
    setMoreEvents([]);
    setMoreCursor(null);
    setMoreHasMore(null);
  }, [childId]);

  async function loadMoreActivity() {
    const cursor = moreCursor ?? query.data?.next_cursor ?? null;
    const canLoad = moreHasMore ?? query.data?.has_more ?? false;
    if (!session || !childId || !cursor || !canLoad || loadingMoreActivity) return;
    setLoadingMoreActivity(true);
    try {
      const page = await fetchParentActivity(session.token, childId, cursor);
      setMoreEvents((current) => {
        const seen = new Set(current.map((event) => event.log_id));
        return [...current, ...page.events.filter((event) => !seen.has(event.log_id))];
      });
      setMoreCursor(page.next_cursor);
      setMoreHasMore(page.has_more);
    } finally {
      setLoadingMoreActivity(false);
    }
  }

  if (!childId) {
    return (
      <Screen>
        <ScrollView contentContainerStyle={styles.refreshScrollContent}>
          <SubScreenHero
            kicker="Community & Account"
            title="Activity History"
            subtitle="Choose a child to view their high-level safety and control timeline."
            icon="activity"
            iconColor="#7C3AED"
            iconBg="#F5F3FF"
          />
          <AsyncBody query={dashboard}>
            {dashboard.data?.children.length ? (
              <SelectChild children={dashboard.data.children} onPick={setChildId} />
            ) : (
              <Card>
                <View style={styles.emptyChildContainer}>
                  <View style={styles.emptyChildBadge}>
                    <Feather name="users" size={24} color={colors.brand} />
                  </View>
                  <Text style={styles.emptyChildTitle}>No Children Added Yet</Text>
                  <Text style={styles.emptyChildBody}>
                    Activity events will appear here once child profiles are active.
                  </Text>
                </View>
              </Card>
            )}
          </AsyncBody>
        </ScrollView>
      </Screen>
    );
  }

  const rows = [...(query.data?.events ?? []), ...moreEvents];
  const recentPartners = query.data?.recent_chat_partners ?? [];
  const canLoadMoreActivity = moreHasMore ?? query.data?.has_more ?? false;

  return (
    <Screen>
      <FlatList
        data={rows}
        keyExtractor={(event) => String(event.log_id)}
        contentContainerStyle={styles.refreshScrollContent}
        refreshControl={<RefreshControl refreshing={query.isRefetching} onRefresh={() => void query.refetch()} />}
        ListHeaderComponent={
          <>
            <SubScreenHero
              kicker={child?.full_name ?? 'Child'}
              title="Activity History"
              subtitle="Chronological log of account, safety, screen time, and high-level communication activity."
              icon="activity"
              iconColor="#7C3AED"
              iconBg="#F5F3FF"
            />
            {recentPartners.length ? (
              <Card>
                <Text style={styles.rowTitle}>Recent chat partners</Text>
                <Text style={styles.muted}>Shows who your child has interacted with, not private message content.</Text>
                {recentPartners.map((partner) => (
                  <View key={partner.child_id} style={[styles.rowBetween, { marginTop: spacing.md }]}>
                    <View style={{ flex: 1, flexDirection: 'row', alignItems: 'center', gap: spacing.sm }}>
                      <Avatar uri={partner.avatar_url} name={partner.full_name ?? partner.username ?? 'Friend'} size={36} />
                      <View style={styles.flex}>
                        <Text style={styles.rowTitle}>{partner.full_name ?? partner.username ?? 'Friend'}</Text>
                        <Text style={styles.muted}>@{partner.username ?? 'friend'} · {Number(partner.messages_30d ?? 0)} messages in 30 days</Text>
                      </View>
                    </View>
                    <TimeAgo value={partner.last_interaction_at} />
                  </View>
                ))}
              </Card>
            ) : null}
          </>
        }
        ListEmptyComponent={
          query.isPending ? (
            <LoadingState message="Loading activity history…" />
          ) : query.isError ? (
            <ErrorState message={errorText(query.error)} onRetry={() => void query.refetch()} />
          ) : (
            <Card>
              <View style={styles.emptyChildContainer}>
                <View style={[styles.emptyChildBadge, { backgroundColor: '#F5F3FF' }]}>
                  <Feather name="activity" size={24} color="#7C3AED" />
                </View>
                <Text style={styles.emptyChildTitle}>No Recent Activity</Text>
                <Text style={styles.emptyChildBody}>
                  New logins, quiz attempts, and safety events will automatically be recorded in this timeline.
                </Text>
              </View>
            </Card>
          )
        }
        ListFooterComponent={canLoadMoreActivity ? (
          <View style={{ marginTop: spacing.md, marginBottom: spacing.lg }}>
            <Button
              label={loadingMoreActivity ? 'Loading older activity…' : 'Load older activity'}
              variant="secondary"
              disabled={loadingMoreActivity}
              onPress={() => void loadMoreActivity()}
            />
          </View>
        ) : null}
        renderItem={({ item: event }) => (
          <View style={styles.activityTimelineCard}>
            <View style={styles.activityIconBubble}>
              <Feather name="check-circle" size={16} color="#7C3AED" />
            </View>
            <View style={styles.flex}>
              <Text style={styles.activityTitleText}>{humanize(event.activity_type)}</Text>
              <TimeAgo value={event.created_at} />
            </View>
          </View>
        )}
      />
    </Screen>
  );
}

export function ParentNotificationsScreen({ navigation }: ParentScreenProps<'ParentNotifications'>) {
  const { session } = useAuth();
  const client = useQueryClient();
  const query = useQuery({ queryKey: parentKeys.notifications, queryFn: () => fetchParentNotifications(session?.token ?? ''), enabled: Boolean(session) });
  const read = useMutation({
    mutationFn: () => markParentNotificationsRead(session?.token ?? ''),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: parentKeys.notifications }),
        client.invalidateQueries({ queryKey: parentKeys.dashboard }),
      ]);
    },
  });
  const rows = query.data?.notifications ?? [];

  function open(row: ParentNotification) {
    const value = row.notification_type.toUpperCase();
    const childId = row.child_id;
    if (value.includes('FOLLOW')) navigation.navigate('FollowRequests');
    else if (value.includes('SCREEN_TIME')) navigation.navigate('ScreenTime', { childId });
    else if (value.includes('CONTROL') || value === 'PROFILE_APPROVAL') navigation.navigate('ParentControls', { childId });
    else if (value.includes('REVIEW') || value.includes('BLOCK') || value.includes('SAFETY') || value.includes('REPORT')) navigation.navigate('ParentSafety');
  }

  return (
    <Screen>
      <FlatList
        data={rows}
        keyExtractor={(row) => String(row.notification_id)}
        contentContainerStyle={styles.refreshScrollContent}
        refreshControl={<RefreshControl refreshing={query.isRefetching} onRefresh={() => void query.refetch()} />}
        ListHeaderComponent={
          <>
            <SubScreenHero
              kicker="Community & Account"
              title="Notifications & Alerts"
              subtitle="Real-time alerts for safety decisions, follow approvals, and account updates."
              icon="bell"
              iconColor="#D97706"
              iconBg="#FFFBEB"
            />
            {rows.some((row) => !row.is_read) ? (
              <View style={styles.markReadRow}>
                <Pressable
                  onPress={() => read.mutate()}
                  style={styles.markReadButton}
                  disabled={read.isPending}
                >
                  <Feather name="check" size={14} color={colors.brand} />
                  <Text style={styles.markReadText}>Mark all as read</Text>
                </Pressable>
              </View>
            ) : null}
          </>
        }
        ListEmptyComponent={
          query.isPending ? (
            <LoadingState message="Loading notifications…" />
          ) : query.isError ? (
            <ErrorState message={errorText(query.error)} onRetry={() => void query.refetch()} />
          ) : (
            <Card>
              <View style={styles.emptyChildContainer}>
                <View style={[styles.emptyChildBadge, { backgroundColor: '#FFFBEB' }]}>
                  <Feather name="bell" size={24} color="#D97706" />
                </View>
                <Text style={styles.emptyChildTitle}>All Caught Up</Text>
                <Text style={styles.emptyChildBody}>
                  You have no pending safety alerts or notifications at this time.
                </Text>
              </View>
            </Card>
          )
        }
        renderItem={({ item: row }) => (
          <Pressable
            accessibilityRole="button"
            style={[styles.notificationCard, !row.is_read && styles.notificationUnreadCard]}
            onPress={() => open(row)}
          >
            <View style={[styles.notificationIconWrap, !row.is_read && styles.notificationIconUnread]}>
              <Feather
                name={
                  row.notification_type.includes('SAFETY') || row.notification_type.includes('REVIEW')
                    ? 'shield'
                    : row.notification_type.includes('FOLLOW')
                    ? 'user-check'
                    : 'bell'
                }
                size={18}
                color={!row.is_read ? colors.brand : '#64748B'}
              />
            </View>
            <View style={styles.flex}>
              <View style={styles.rowBetween}>
                <Text style={[styles.notificationTitle, !row.is_read && styles.notificationTitleBold]}>
                  {humanize(row.notification_type)}
                </Text>
                <TimeAgo value={row.created_at} />
              </View>
              <Text style={styles.notificationMessage}>{row.notification_message}</Text>
            </View>
            <Feather name="chevron-right" size={16} color="#94A3B8" />
          </Pressable>
        )}
      />
    </Screen>
  );
}

export function ParentSettingsScreen(_props: ParentScreenProps<'ParentSettings'>) {
  const { session, signOut } = useAuth();

  const handleLogout = () => {
    Alert.alert(
      'Sign Out',
      'Are you sure you want to sign out of your parent account on this device?',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Sign Out', style: 'destructive', onPress: () => void signOut() },
      ]
    );
  };

  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.refreshScrollContent}>
        <SubScreenHero
          kicker="Community & Account"
          title="Parent Settings"
          subtitle="Account identity, session security, and family oversight status."
          icon="settings"
          iconColor="#475569"
          iconBg="#F1F5F9"
        />

        {/* Account Identity Card */}
        <Card>
          <View style={styles.settingsAccountRow}>
            <View style={styles.parentAvatarInitial}>
              <Text style={styles.parentAvatarInitialText}>
                {(session?.user.full_name ?? 'P').charAt(0).toUpperCase()}
              </Text>
            </View>
            <View style={styles.flex}>
              <Text style={styles.settingsName}>{session?.user.full_name}</Text>
              <Text style={styles.settingsHandle}>@{session?.user.username}</Text>
              <Text style={styles.settingsEmail}>{session?.user.email}</Text>
            </View>
            <View style={styles.adminChip}>
              <Feather name="shield" size={11} color="#2563EB" />
              <Text style={styles.adminChipText}>Verified</Text>
            </View>
          </View>
        </Card>

        {/* Session Sign Out */}
        <View style={{ marginHorizontal: spacing.md, marginTop: spacing.md, marginBottom: spacing.xl }}>
          <Button
            label="Log Out of Parent Account"
            variant="secondary"
            onPress={handleLogout}
          />
        </View>
      </ScrollView>
    </Screen>
  );
}

function humanize(value: string): string {
  return value.toLowerCase().split('_').map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(' ');
}

function RiskBadge({ score }: { score?: number | string | null }) {
  const numeric = Number(score);
  const tone = Number.isFinite(numeric) && numeric >= 0.7 ? 'danger' : Number.isFinite(numeric) && numeric >= 0.4 ? 'review' : 'safe';
  return <View style={[styles.riskBadge, tone === 'danger' ? styles.riskDanger : tone === 'review' ? styles.riskReview : styles.riskSafe]}><Text style={styles.riskText}>{tone === 'safe' ? 'Review item' : `${tone === 'danger' ? 'High' : 'Review'} risk · ${String(score ?? 'not scored')}`}</Text></View>;
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  refreshScrollContent: { flexGrow: 1, paddingBottom: spacing.xl },
  formScrollContent: { flexGrow: 1, paddingBottom: spacing.xl },
  body: { color: colors.ink, fontSize: type.body, lineHeight: 22, marginTop: spacing.xs },
  muted: { color: colors.muted, fontSize: type.caption, lineHeight: 18 },
  sectionTitle: { color: colors.ink, fontSize: type.title, fontWeight: '800', marginTop: spacing.lg, marginBottom: spacing.sm, marginHorizontal: spacing.md },
  sectionWrap: { marginTop: spacing.sm },
  sectionHeaderRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingRight: spacing.md,
    marginBottom: spacing.xs,
  },
  sectionHeaderLeft: { flexDirection: 'row', alignItems: 'center', gap: 6, marginHorizontal: spacing.md },
  sectionHeaderLabel: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 0.8,
  },
  sectionCountPill: {
    backgroundColor: '#EFF6FF',
    paddingHorizontal: 7,
    paddingVertical: 1,
    borderRadius: radius.pill,
  },
  sectionCountText: { color: '#2563EB', fontSize: 10, fontWeight: '800' },
  addInlineButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 12,
    paddingVertical: 5,
    borderRadius: radius.pill,
    backgroundColor: '#EFF6FF',
    borderWidth: 1,
    borderColor: '#BFDBFE',
  },
  addInlineText: {
    color: colors.brand,
    fontWeight: '800',
    fontSize: 12,
  },
  parentWelcomeBanner: {
    marginHorizontal: spacing.md,
    marginTop: spacing.sm,
    marginBottom: spacing.md,
    backgroundColor: '#FFFFFF',
    borderRadius: 18,
    padding: 16,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.04,
    shadowRadius: 8,
    elevation: 2,
  },
  parentWelcomeMeta: { gap: 6 },
  parentGreetingRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  parentAvatarInitial: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: '#EFF6FF',
    borderWidth: 2,
    borderColor: '#BFDBFE',
    alignItems: 'center',
    justifyContent: 'center',
  },
  parentAvatarInitialText: { color: colors.brand, fontSize: 18, fontWeight: '900' },
  parentGreetingName: { color: colors.ink, fontSize: 18, fontWeight: '900', letterSpacing: -0.3 },
  parentRoleBadgeRow: { flexDirection: 'row', marginTop: 3 },
  parentRoleBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: '#EFF6FF',
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: radius.pill,
  },
  parentRoleBadgeText: { color: '#2563EB', fontSize: 11, fontWeight: '700' },
  parentWelcomeSub: { color: colors.muted, fontSize: 12, lineHeight: 17, marginTop: 4 },
  guardianBanner: {
    backgroundColor: '#0F172A',
    borderRadius: 18,
    padding: spacing.md,
    marginHorizontal: spacing.md,
    marginBottom: spacing.md,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.12,
    shadowRadius: 10,
    elevation: 3,
  },
  guardianRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  guardianIconWrap: {
    width: 42,
    height: 42,
    borderRadius: 12,
    backgroundColor: 'rgba(56, 189, 248, 0.15)',
    borderWidth: 1,
    borderColor: 'rgba(56, 189, 248, 0.35)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  guardianTitleRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  guardianTitle: { color: '#FFFFFF', fontSize: 14, fontWeight: '800', letterSpacing: -0.2 },
  guardianLiveChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: '#1E293B',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: '#334155',
  },
  livePulseDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: '#38BDF8' },
  guardianLiveText: { color: '#38BDF8', fontSize: 9, fontWeight: '900', letterSpacing: 0.5 },
  guardianSub: { color: '#94A3B8', fontSize: 11, marginTop: 3, lineHeight: 15 },
  guardianPillsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginTop: 10,
    paddingTop: 10,
    borderTopWidth: 1,
    borderTopColor: '#1E293B',
  },
  guardianPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: '#1E293B',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: radius.pill,
  },
  guardianPillText: { color: '#E2E8F0', fontSize: 10, fontWeight: '700' },
  metrics: { flexDirection: 'row', gap: 8, marginHorizontal: spacing.md, marginBottom: spacing.md },
  metric: {
    flex: 1,
    padding: 12,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.03,
    shadowRadius: 6,
    elevation: 1,
  },
  metricAlert: { backgroundColor: '#FFF5F5', borderColor: '#FEE2E2' },
  metricTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 },
  metricIconWrap: {
    width: 28,
    height: 28,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  metricValue: { color: colors.ink, fontWeight: '900', fontSize: 18 },
  metricValueAlert: { color: colors.danger },
  metricLabel: { color: colors.muted, fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5 },
  menuGroupCard: {
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#EFEFEF',
    borderRadius: 16,
    marginHorizontal: spacing.md,
    marginTop: spacing.xs,
    marginBottom: spacing.sm,
    overflow: 'hidden',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.03,
    shadowRadius: 6,
    elevation: 1,
  },
  menuRowItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingHorizontal: 14,
    paddingVertical: 13,
  },
  menuRowBorder: {
    borderBottomWidth: 1,
    borderBottomColor: '#F3F4F6',
  },
  menuIconBadge: {
    width: 44,
    height: 44,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  menuTitle: { color: colors.ink, fontSize: 15, fontWeight: '800' },
  bottomCtaCard: {
    backgroundColor: '#F0F9FF',
    borderWidth: 1,
    borderColor: '#BAE6FD',
    borderRadius: 16,
    padding: 16,
    marginHorizontal: spacing.md,
    marginTop: spacing.md,
    marginBottom: spacing.md,
    gap: 12,
  },
  bottomCtaHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  bottomCtaIconWrap: {
    width: 40,
    height: 40,
    borderRadius: 12,
    backgroundColor: '#E0F2FE',
    alignItems: 'center',
    justifyContent: 'center',
  },
  bottomCtaTitle: { color: '#0369A1', fontSize: 15, fontWeight: '800' },
  bottomCtaSub: { color: '#0284C7', fontSize: 12, lineHeight: 16, marginTop: 2 },
  childCard: {
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#E2E8F0',
    borderRadius: 18,
    padding: 14,
    marginHorizontal: spacing.md,
    marginBottom: spacing.sm,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.03,
    shadowRadius: 6,
    elevation: 1,
  },
  childTopRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  avatarWrapper: { position: 'relative' },
  presenceIndicator: {
    position: 'absolute',
    bottom: 0,
    right: 0,
    width: 13,
    height: 13,
    borderRadius: 7,
    borderWidth: 2,
    borderColor: '#FFFFFF',
  },
  onlineIndicator: { backgroundColor: '#10B981' },
  offlineIndicator: { backgroundColor: '#9CA3AF' },
  childMetaCol: { flex: 1, gap: 2 },
  childNameRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  childFullName: { color: colors.ink, fontSize: 16, fontWeight: '800' },
  childHandleText: { color: colors.muted, fontSize: 12 },
  agePill: { backgroundColor: '#F1F5F9', paddingHorizontal: 6, paddingVertical: 2, borderRadius: radius.pill },
  agePillText: { color: '#475569', fontSize: 10, fontWeight: '700' },
  childStatusBadge: { alignItems: 'flex-end' },
  childStatsSection: { marginTop: 12, paddingTop: 10, borderTopWidth: 1, borderTopColor: '#F3F4F6', gap: 8 },
  usageRow: { gap: 4 },
  usageLabelRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  statIconLabel: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  usageStatText: { color: '#64748B', fontSize: 11, fontWeight: '600' },
  usagePercentText: { color: '#64748B', fontSize: 11, fontWeight: '700' },
  usageDangerText: { color: colors.danger, fontWeight: '800' },
  usageWarning: { backgroundColor: '#F59E0B' },
  usageTrack: { height: 6, backgroundColor: '#F1F5F9', borderRadius: 6, overflow: 'hidden', marginTop: 2 },
  usageFill: { height: 6, backgroundColor: colors.brand, borderRadius: 6 },
  usageDanger: { backgroundColor: colors.danger },
  chipsRow: { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
  quizScoreChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: '#EFF6FF',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: radius.pill,
  },
  quizScoreText: { color: '#2563EB', fontSize: 11, fontWeight: '700' },
  behaviorChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: '#ECFDF5',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: radius.pill,
  },
  behaviorChipText: { color: '#059669', fontSize: 11, fontWeight: '700' },
  childQuickActionsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginTop: 10,
    paddingTop: 10,
    borderTopWidth: 1,
    borderTopColor: '#F3F4F6',
  },
  quickActionPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: '#F8FAFC',
    borderWidth: 1,
    borderColor: '#E2E8F0',
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: radius.pill,
  },
  quickActionText: { color: '#334155', fontSize: 11, fontWeight: '700' },
  cardChevronWrap: { flex: 1, flexDirection: 'row', justifyContent: 'flex-end', alignItems: 'center', gap: 2 },
  detailsPromptText: { color: '#94A3B8', fontSize: 11, fontWeight: '600' },
  addChildCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    backgroundColor: '#F8FAFC',
    borderWidth: 1.5,
    borderColor: '#CBD5E1',
    borderStyle: 'dashed',
    borderRadius: 18,
    padding: 14,
    marginHorizontal: spacing.md,
    marginBottom: spacing.sm,
  },
  addChildCardPlusWrap: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: '#EFF6FF',
    alignItems: 'center',
    justifyContent: 'center',
  },
  addChildCardTitle: { fontSize: 14, fontWeight: '800', color: colors.ink },
  addChildCardSub: { fontSize: 11, color: colors.muted, marginTop: 2 },
  emptyChildContainer: {
    alignItems: 'center',
    paddingVertical: spacing.sm,
    gap: 6,
  },
  emptyChildBadge: {
    width: 48,
    height: 48,
    borderRadius: 14,
    backgroundColor: '#EFF6FF',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 4,
  },
  emptyChildTitle: {
    fontSize: 16,
    fontWeight: '800',
    color: colors.ink,
  },
  emptyChildBody: {
    fontSize: 12,
    color: colors.muted,
    textAlign: 'center',
    lineHeight: 18,
    maxWidth: 290,
    marginBottom: spacing.xs,
  },
  oversightErrorCard: {
    alignItems: 'center',
    paddingVertical: spacing.lg,
    paddingHorizontal: spacing.md,
    gap: 8,
    marginHorizontal: spacing.md,
    marginBottom: spacing.sm,
    borderWidth: 1,
    borderColor: '#FEE2E2',
    backgroundColor: '#FFF5F5',
  },
  errorIconCircle: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: '#FEE2E2',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 4,
  },
  errorCardTitle: { fontSize: 15, fontWeight: '800', color: colors.ink },
  errorCardSub: { fontSize: 12, color: colors.muted, textAlign: 'center', lineHeight: 17, maxWidth: 280, marginBottom: 4 },
  usageSummary: { padding: spacing.md, backgroundColor: '#EFF6FF', borderRadius: 14, marginBottom: spacing.sm },
  usageNumber: { color: colors.brand, fontSize: 32, fontWeight: '900' },
  largeUsageTrack: { height: 8, backgroundColor: '#DBEAFE', borderRadius: 8, overflow: 'hidden', marginVertical: spacing.sm },
  sectionKicker: { color: colors.violet, fontSize: 11, fontWeight: '900', letterSpacing: 1.3, marginHorizontal: spacing.md, marginTop: spacing.sm, marginBottom: spacing.xs },
  riskBadge: { paddingHorizontal: spacing.sm, paddingVertical: spacing.xs, borderRadius: radius.pill },
  riskSafe: { backgroundColor: '#E7F6EC' },
  riskReview: { backgroundColor: '#FFF4D6' },
  riskDanger: { backgroundColor: '#FDECEC' },
  riskText: { color: colors.ink, fontSize: 11, fontWeight: '800' },
  listCard: { backgroundColor: colors.surface, borderWidth: 1, borderColor: '#EFEFEF', borderRadius: 14, padding: spacing.md, marginHorizontal: spacing.md, marginBottom: spacing.sm },
  rowTitle: { color: colors.ink, fontWeight: '800', fontSize: type.body },
  rowBetween: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: spacing.sm },
  alertPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: '#FDECEC',
    borderRadius: radius.pill,
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  alertText: { color: colors.danger, fontWeight: '800', fontSize: 11 },
  // Viewing insights cards (parent dashboard)
  insightCard: { marginBottom: spacing.sm },
  insightHeader: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: spacing.sm },
  insightChildName: { color: colors.ink, fontWeight: '800', fontSize: type.body },
  insightPad: { paddingVertical: spacing.sm },
  insightStatRow: { flexDirection: 'row', gap: spacing.md, marginBottom: spacing.sm },
  insightStat: { flex: 1, backgroundColor: '#F8FAFC', borderRadius: radius.md, padding: spacing.sm },
  insightStatValue: { color: colors.ink, fontWeight: '800', fontSize: 18 },
  insightBarRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 },
  insightBarLabel: { width: 110, color: colors.ink, fontSize: 13 },
  insightBarTrack: { flex: 1, height: 8, borderRadius: 4, backgroundColor: '#EDEFF3' },
  insightBarFill: { height: 8, borderRadius: 4, backgroundColor: '#2563EB' },
  insightBarValue: { width: 32, textAlign: 'right', color: colors.muted, fontSize: 13, fontWeight: '700' },
  insightTopReel: { marginTop: spacing.sm, color: colors.ink, fontSize: 13 },
  safePill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: '#ECFDF5',
    borderRadius: radius.pill,
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderWidth: 1,
    borderColor: '#A7F3D0',
  },
  safeText: { color: '#047857', fontWeight: '800', fontSize: 11 },
  reviewImage: { width: '100%', height: 280, borderRadius: 12, backgroundColor: colors.line, marginVertical: spacing.sm },
  reviewVideoShell: {
    width: '100%',
    height: 280,
    borderRadius: 12,
    overflow: 'hidden',
    backgroundColor: '#0F172A',
    marginVertical: spacing.sm,
  },
  reviewVideo: { width: '100%', height: '100%' },
  reviewVideoVeil: { ...StyleSheet.absoluteFill, alignItems: 'center', justifyContent: 'center', gap: 10 },
  reviewVideoPoster: { ...StyleSheet.absoluteFill, width: '100%', height: '100%' },
  reviewVideoPlayBadge: {
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: 'rgba(0,0,0,0.6)',
    alignItems: 'center',
    justifyContent: 'center',
    paddingLeft: 4,
  },
  reviewVideoHint: { color: '#FFFFFF', fontWeight: '700', fontSize: 13 },
  reviewVideoError: {
    ...StyleSheet.absoluteFill,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(15,23,42,0.85)',
    padding: spacing.md,
  },
  reviewVideoErrorText: { color: '#FCA5A5', fontWeight: '700', textAlign: 'center' },
  blurVeil: {
    ...StyleSheet.absoluteFill,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    backgroundColor: 'rgba(15,23,42,0.55)',
    borderRadius: 12,
    padding: spacing.md,
  },
  blurTitle: { color: '#FFFFFF', fontWeight: '800', fontSize: 15 },
  blurBody: { color: 'rgba(255,255,255,0.85)', fontWeight: '600', fontSize: 12, textAlign: 'center' },
  rehide: { flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-end', paddingVertical: 8, paddingHorizontal: 4 },
  rehideText: { color: colors.muted, fontWeight: '700', fontSize: 13 },
  toggle: { minHeight: 64, flexDirection: 'row', alignItems: 'center', gap: spacing.md, borderBottomWidth: 1, borderBottomColor: '#F3F4F6', paddingVertical: spacing.sm },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginHorizontal: spacing.md },
  chip: { borderWidth: 1, borderColor: '#E5E7EB', borderRadius: radius.pill, paddingVertical: 8, paddingHorizontal: 14, backgroundColor: colors.surface },
  chipSelected: { backgroundColor: colors.teal, borderColor: colors.teal },
  chipText: { color: colors.ink, fontWeight: '700', fontSize: 13 },
  chipTextSelected: { color: colors.surface },
  actions: { flexDirection: 'row', gap: spacing.sm },
  activityRow: { flexDirection: 'row', gap: spacing.sm, minHeight: 62, paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: '#F3F4F6', alignItems: 'center', marginHorizontal: spacing.md },
  timelineDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: colors.teal },
  notification: { minHeight: 72, flexDirection: 'row', gap: spacing.sm, alignItems: 'center', borderBottomWidth: 1, borderBottomColor: '#F3F4F6', padding: spacing.md },
  unread: { backgroundColor: '#F0F9FF' },

  /* Sub-Screen Hero Header */
  subHeroContainer: {
    marginHorizontal: spacing.md,
    marginTop: spacing.sm,
    marginBottom: spacing.md,
    backgroundColor: '#FFFFFF',
    borderRadius: 18,
    padding: 16,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.04,
    shadowRadius: 8,
    elevation: 2,
  },
  subHeroTopRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 },
  subHeroKickerRow: { marginBottom: 2 },
  subHeroKickerText: { color: colors.brand, fontSize: 10, fontWeight: '800', letterSpacing: 0.8 },
  subHeroTitle: { color: colors.ink, fontSize: 20, fontWeight: '900', letterSpacing: -0.4 },
  subHeroSubtitle: { color: colors.muted, fontSize: 12, lineHeight: 18, marginTop: 4 },
  subHeroIconBadge: { width: 44, height: 44, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },

  /* Child Summary Profile Card */
  summaryProfileCard: {
    marginHorizontal: spacing.md,
    marginTop: spacing.sm,
    marginBottom: spacing.md,
    backgroundColor: '#FFFFFF',
    borderRadius: 18,
    padding: 16,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.04,
    shadowRadius: 8,
    elevation: 2,
  },
  summaryProfileTopRow: { flexDirection: 'row', alignItems: 'center', gap: 14 },
  summaryProfileName: { color: colors.ink, fontSize: 18, fontWeight: '900' },
  presenceIndicatorLarge: {
    position: 'absolute',
    bottom: 0,
    right: 0,
    width: 15,
    height: 15,
    borderRadius: 8,
    borderWidth: 2.5,
    borderColor: '#FFFFFF',
  },
  summaryStatusRow: { flexDirection: 'row', alignItems: 'center', gap: 5, marginTop: 3 },
  statusDot: { width: 7, height: 7, borderRadius: 4 },
  onlineDot: { backgroundColor: '#10B981' },
  offlineDot: { backgroundColor: '#94A3B8' },
  summaryStatusText: { color: colors.muted, fontSize: 11, fontWeight: '600' },

  /* Standalone Section Labels */
  sectionHeaderLabelStandalone: {
    color: colors.muted,
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 0.8,
    marginHorizontal: spacing.md,
    marginTop: spacing.sm,
    marginBottom: spacing.xs,
  },

  /* Stats 2x2 Grid */
  statsGrid2x2: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginHorizontal: spacing.md,
    marginBottom: spacing.md,
  },
  gridStatCard: {
    width: '48.5%',
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    padding: 12,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.03,
    shadowRadius: 4,
    elevation: 1,
    gap: 2,
  },
  statIconBadge: {
    width: 32,
    height: 32,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 4,
  },
  gridStatNumber: { color: colors.ink, fontSize: 18, fontWeight: '900' },
  gridStatLabel: { color: colors.muted, fontSize: 11, fontWeight: '600' },
  gridStatSub: { color: colors.brand, fontSize: 10, fontWeight: '700', marginTop: 2 },
  gridUsageTrack: { height: 5, backgroundColor: '#F1F5F9', borderRadius: 4, overflow: 'hidden', marginTop: 6 },

  /* Action Tiles */
  actionTilesGroup: {
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    marginHorizontal: spacing.md,
    marginBottom: spacing.xl,
    overflow: 'hidden',
  },
  actionTileRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingHorizontal: 14,
    paddingVertical: 13,
    borderBottomWidth: 1,
    borderBottomColor: '#F3F4F6',
  },

  /* Safety Review Cards */
  safetyCard: {
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#E2E8F0',
    borderRadius: 16,
    padding: 14,
    marginHorizontal: spacing.md,
    marginBottom: spacing.sm,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.03,
    shadowRadius: 6,
    elevation: 1,
    gap: 8,
  },
  safetyCardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  safetyChildName: { color: colors.ink, fontSize: 15, fontWeight: '800' },
  safetyReasonBox: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 6,
    backgroundColor: '#FFFBEB',
    borderWidth: 1,
    borderColor: '#FDE68A',
    borderRadius: 10,
    padding: 8,
  },
  safetyReasonText: { flex: 1, color: '#92400E', fontSize: 12, lineHeight: 16 },
  safetyCardFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: '#F3F4F6',
  },
  safetyFooterMeta: { color: colors.muted, fontSize: 11 },
  safetyReviewPrompt: { flexDirection: 'row', alignItems: 'center', gap: 2 },
  safetyPromptText: { color: colors.brand, fontSize: 12, fontWeight: '700' },

  /* Quarantine Review Detail */
  quarantineReviewBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: '#0F172A',
    borderRadius: 14,
    padding: 12,
    marginHorizontal: spacing.md,
    marginTop: spacing.sm,
    marginBottom: spacing.sm,
  },
  quarantineBannerText: { color: '#38BDF8', fontSize: 11, fontWeight: '800', letterSpacing: 0.5 },
  reviewChildTitle: { color: colors.ink, fontSize: 18, fontWeight: '900', marginTop: 4 },
  quotedContentBox: {
    backgroundColor: '#F8FAFC',
    borderLeftWidth: 3,
    borderLeftColor: colors.brand,
    borderRadius: 8,
    padding: 10,
    marginVertical: spacing.xs,
  },
  quotedContentText: { color: colors.ink, fontSize: 13, lineHeight: 18, fontStyle: 'italic' },
  reviewFlagSection: {
    backgroundColor: '#FFFBEB',
    borderRadius: 12,
    padding: 12,
    marginVertical: spacing.sm,
    gap: 6,
    borderWidth: 1,
    borderColor: '#FEF3C7',
  },
  reviewFlagRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  reviewFlagLabel: { color: '#92400E', fontSize: 12, fontWeight: '700' },
  reviewFlagValue: { color: '#B45309', fontSize: 12, fontWeight: '600', maxWidth: '60%', textAlign: 'right' },
  reviewActionButtonsRow: { flexDirection: 'row', gap: 10, marginTop: spacing.sm },

  /* Screen Time Details */
  usageTopRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' },
  allowancePill: {
    backgroundColor: '#EFF6FF',
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: '#BFDBFE',
  },
  allowancePillText: { color: '#2563EB', fontSize: 11, fontWeight: '700' },
  presetHeading: { color: colors.muted, fontSize: 10, fontWeight: '800', letterSpacing: 0.8, marginBottom: 8 },
  presetsRow: { flexDirection: 'row', gap: 8, marginBottom: spacing.md },
  presetButton: {
    flex: 1,
    paddingVertical: 8,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    backgroundColor: '#F8FAFC',
    alignItems: 'center',
    justifyContent: 'center',
  },
  presetButtonActive: { backgroundColor: colors.brand, borderColor: colors.brand },
  presetButtonText: { color: '#475569', fontSize: 12, fontWeight: '700' },
  presetButtonTextActive: { color: '#FFFFFF' },
  bottomInfoCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    backgroundColor: '#F0F9FF',
    borderWidth: 1,
    borderColor: '#BAE6FD',
    borderRadius: 14,
    padding: 12,
    marginHorizontal: spacing.md,
    marginTop: spacing.sm,
    marginBottom: spacing.xl,
  },
  bottomInfoText: { flex: 1, color: '#0369A1', fontSize: 11, lineHeight: 16 },

  /* Controls Rows */
  controlRowItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingVertical: 12,
  },
  controlIconWrap: {
    width: 36,
    height: 36,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  controlRowTitle: { color: colors.ink, fontSize: 14, fontWeight: '800' },
  controlRowSub: { color: colors.muted, fontSize: 11, lineHeight: 15, marginTop: 1 },
  quietHoursInputSection: { marginTop: 10, gap: 8 },
  timeInputsRow: { flexDirection: 'row', gap: 10 },
  categoryExplainer: { color: colors.muted, fontSize: 12, marginBottom: spacing.sm },
  chipsWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  categoryPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    borderRadius: radius.pill,
    paddingVertical: 6,
    paddingHorizontal: 12,
    backgroundColor: '#F8FAFC',
  },
  categoryPillSelected: { backgroundColor: colors.brand, borderColor: colors.brand },
  categoryPillText: { color: '#334155', fontWeight: '700', fontSize: 12 },
  categoryPillTextSelected: { color: '#FFFFFF' },

  /* Follow Requests */
  friendshipStagePill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: '#FDF2F8',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: radius.pill,
  },
  friendshipStageText: { color: '#DB2777', fontSize: 10, fontWeight: '700' },
  friendshipNamesRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginVertical: spacing.xs },
  friendshipName: { color: colors.ink, fontSize: 16, fontWeight: '800' },
  friendshipHelpText: { color: colors.muted, fontSize: 12, lineHeight: 17, marginBottom: spacing.xs },
  friendshipActionsRow: { flexDirection: 'row', gap: 10, marginTop: spacing.xs },
  awaitingOtherParentPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: '#F8FAFC',
    borderRadius: 8,
    padding: 8,
    marginTop: spacing.xs,
  },
  awaitingOtherParentText: { color: '#64748B', fontSize: 11, fontWeight: '600' },

  /* Activity Timeline */
  activityTimelineCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#E2E8F0',
    borderRadius: 14,
    padding: 12,
    marginHorizontal: spacing.md,
    marginBottom: spacing.xs,
  },
  activityIconBubble: {
    width: 34,
    height: 34,
    borderRadius: 10,
    backgroundColor: '#F5F3FF',
    alignItems: 'center',
    justifyContent: 'center',
  },
  activityTitleText: { color: colors.ink, fontSize: 13, fontWeight: '700' },

  /* Notifications */
  markReadRow: { flexDirection: 'row', justifyContent: 'flex-end', marginHorizontal: spacing.md, marginBottom: spacing.xs },
  markReadButton: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingVertical: 4, paddingHorizontal: 8 },
  markReadText: { color: colors.brand, fontSize: 12, fontWeight: '700' },
  notificationCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: '#E2E8F0',
    borderRadius: 14,
    padding: 12,
    marginHorizontal: spacing.md,
    marginBottom: spacing.xs,
  },
  notificationUnreadCard: {
    backgroundColor: '#F8FAFC',
    borderColor: '#BFDBFE',
    borderLeftWidth: 3,
    borderLeftColor: colors.brand,
  },
  notificationIconWrap: {
    width: 38,
    height: 38,
    borderRadius: 12,
    backgroundColor: '#F1F5F9',
    alignItems: 'center',
    justifyContent: 'center',
  },
  notificationIconUnread: { backgroundColor: '#EFF6FF' },
  notificationTitle: { color: colors.ink, fontSize: 13, fontWeight: '700' },
  notificationTitleBold: { color: colors.ink, fontWeight: '900' },
  notificationMessage: { color: colors.muted, fontSize: 12, marginTop: 2, lineHeight: 16 },

  /* Settings Screen */
  settingsAccountRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  settingsName: { color: colors.ink, fontSize: 17, fontWeight: '900' },
  settingsHandle: { color: colors.muted, fontSize: 12 },
  settingsEmail: { color: colors.brand, fontSize: 12, fontWeight: '600', marginTop: 2 },
  adminChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: '#EFF6FF',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: radius.pill,
  },
  adminChipText: { color: '#2563EB', fontSize: 10, fontWeight: '800' },
  settingsSecItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#F3F4F6',
  },
  settingsSecTitle: { color: colors.ink, fontSize: 13, fontWeight: '800' },
  settingsSecSub: { color: colors.muted, fontSize: 11, marginTop: 1 },

  /* Screen Time Alerts and Reset Controls */
  limitAlertBox: {
    backgroundColor: '#FEF2F2',
    borderWidth: 1,
    borderColor: '#FECACA',
    borderRadius: 14,
    padding: 14,
    marginBottom: 16,
  },
  limitAlertHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 4,
  },
  limitAlertTitle: {
    color: '#DC2626',
    fontSize: 14,
    fontWeight: '800',
  },
  limitAlertBody: {
    color: '#991B1B',
    fontSize: 12,
    lineHeight: 17,
  },
  resetSectionWrap: {
    marginVertical: 14,
    paddingTop: 14,
    borderTopWidth: 1,
    borderTopColor: '#F1F5F9',
  },
  extensionRow: {
    flexDirection: 'row',
    gap: 8,
    marginBottom: 12,
  },
  extensionBtn: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 10,
    borderRadius: 10,
    backgroundColor: '#EFF6FF',
    borderWidth: 1,
    borderColor: '#BFDBFE',
  },
  extensionBtnText: {
    color: '#2563EB',
    fontSize: 13,
    fontWeight: '800',
  },
  resetTimeBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    paddingVertical: 11,
    borderRadius: 10,
    backgroundColor: '#FEF2F2',
    borderWidth: 1,
    borderColor: '#FECACA',
  },
  resetTimeBtnText: {
    color: '#DC2626',
    fontSize: 13,
    fontWeight: '800',
  },

  /* Child Account Management */
  accountPanel: {
    paddingHorizontal: 14,
    paddingBottom: 14,
    borderBottomWidth: 1,
    borderBottomColor: '#F3F4F6',
  },
  accountNoticeWrap: {
    paddingHorizontal: 14,
    paddingBottom: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#F3F4F6',
  },
  dangerText: { color: '#DC2626' },
});
