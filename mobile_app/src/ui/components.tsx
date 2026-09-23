import { useEffect, useRef, type ReactNode } from 'react';
import type { StyleProp, TextInputProps, ViewStyle } from 'react-native';
import { ActivityIndicator, Animated, Image, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Feather } from '@expo/vector-icons';
import { ApiError } from '../api/client';
import { colors, radius, spacing, type } from './tokens';

/**
 * Screen scaffold. `hasNativeHeader = true` (default) means the screen
 * renders under a native stack header or equivalent top chrome (the kids
 * tab shell's custom top bar), which already clears the notch — so Screen
 * skips the top safe-area inset and only applies the bottom one.
 */
export function Screen({ children, hasNativeHeader = true }: { children: ReactNode; hasNativeHeader?: boolean }) {
  const insets = useSafeAreaInsets();
  return (
    <View style={[styles.screen, { paddingTop: hasNativeHeader ? 0 : insets.top, paddingBottom: insets.bottom }]}>
      {children}
    </View>
  );
}

export function Card({ children, style }: { children: ReactNode; style?: StyleProp<ViewStyle> }) {
  return <View style={[styles.card, style]}>{children}</View>;
}

export function BrandHeader({
  title,
  subtitle,
  showLogo = true,
  onBack,
}: {
  title: string;
  subtitle?: string;
  showLogo?: boolean;
  /** When set, renders a back chevron (screen owns its header; no native header). */
  onBack?: () => void;
}) {
  const isBrandTitle = title.trim().toLowerCase() === 'littlenet';

  return (
    <View style={styles.header}>
      <View style={styles.brandRow}>
        {onBack ? (
          <Pressable
            onPress={onBack}
            accessibilityRole="button"
            accessibilityLabel="Back"
            hitSlop={10}
            style={styles.backBtn}
          >
            <Feather name="chevron-left" size={24} color={colors.ink} />
          </Pressable>
        ) : null}
        {showLogo ? (
          <Image
            source={require('../../assets/app_logo.png')}
            style={styles.headerLogo}
            resizeMode="cover"
          />
        ) : null}
        <Text style={styles.brand}>LittleNet</Text>
      </View>
      {!isBrandTitle ? <Text style={styles.title}>{title}</Text> : null}
      {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}
    </View>
  );
}

interface ButtonProps {
  label: string;
  onPress: () => void;
  disabled?: boolean;
  loading?: boolean;
  variant?: 'primary' | 'secondary';
}

export function Button({ label, onPress, disabled, loading, variant = 'primary' }: ButtonProps) {
  const isDisabled = disabled || loading;
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      disabled={isDisabled}
      style={({ pressed }) => [
        styles.button,
        variant === 'secondary' && styles.buttonSecondary,
        isDisabled && styles.buttonDisabled,
        pressed && !isDisabled && styles.buttonPressed,
      ]}
    >
      {loading ? <ActivityIndicator color={variant === 'secondary' ? colors.ink : '#fff'} /> : <Text style={[styles.buttonText, variant === 'secondary' && styles.buttonTextSecondary]}>{label}</Text>}
    </Pressable>
  );
}

interface FieldProps extends TextInputProps {
  label: string;
  error?: string;
  helper?: string;
  rightAction?: ReactNode;
}

export function Field({ label, error, helper, rightAction, style, ...rest }: FieldProps) {
  return (
    <View style={styles.field}>
      <View style={styles.labelRow}>
        <Text style={styles.label}>{label}</Text>
        {rightAction}
      </View>
      <TextInput
        placeholderTextColor={colors.muted}
        style={[styles.input, error ? styles.inputError : null, style]}
        {...rest}
      />
      {error ? <Text style={styles.fieldError}>{error}</Text> : null}
      {helper && !error ? <Text style={styles.fieldHelper}>{helper}</Text> : null}
    </View>
  );
}

export function StepIndicator({
  step,
  total = 2,
  label,
  steps = ['Guardian', 'Verify Email'],
}: {
  step: number;
  total?: number;
  label?: string;
  steps?: string[];
}) {
  return (
    <View style={styles.stepContainer}>
      <View style={styles.stepTracker}>
        {steps.map((name, idx) => {
          const stepNum = idx + 1;
          const isDone = stepNum < step;
          const isActive = stepNum === step;
          const isUpcoming = stepNum > step;
          return (
            <View key={idx} style={styles.stepItemWrapper}>
              <View style={styles.stepBadgeRow}>
                {idx > 0 ? (
                  <View
                    style={[
                      styles.stepConnector,
                      (isDone || isActive) && styles.stepConnectorFilled,
                    ]}
                  />
                ) : (
                  <View style={styles.stepConnectorSpacer} />
                )}
                <View
                  style={[
                    styles.stepBadge,
                    isActive && styles.stepBadgeActive,
                    isDone && styles.stepBadgeDone,
                    isUpcoming && styles.stepBadgeUpcoming,
                  ]}
                >
                  {isDone ? (
                    <Feather name="check" size={12} color="#FFFFFF" strokeWidth={3} />
                  ) : (
                    <Text
                      style={[
                        styles.stepBadgeNum,
                        isActive && styles.stepBadgeNumActive,
                        isUpcoming && styles.stepBadgeNumUpcoming,
                      ]}
                    >
                      {stepNum}
                    </Text>
                  )}
                </View>
                {idx < steps.length - 1 ? (
                  <View
                    style={[
                      styles.stepConnector,
                      isDone && styles.stepConnectorFilled,
                    ]}
                  />
                ) : (
                  <View style={styles.stepConnectorSpacer} />
                )}
              </View>
              <Text
                style={[
                  styles.stepTitle,
                  isActive && styles.stepTitleActive,
                  isDone && styles.stepTitleDone,
                ]}
                numberOfLines={1}
              >
                {name}
              </Text>
            </View>
          );
        })}
      </View>
      {label ? (
        <View style={styles.stepCurrentPill}>
          <Text style={styles.stepCurrentText}>
            STEP {step} OF {total} • {label.toUpperCase()}
          </Text>
        </View>
      ) : null}
    </View>
  );
}

type FeatherIconName = keyof typeof Feather.glyphMap;

export function GuidelineChips({
  chips,
}: {
  chips: { icon?: string; iconName?: FeatherIconName; text: string }[];
}) {
  return (
    <View style={styles.chipsRow}>
      {chips.map((chip, idx) => {
        const isFeather = chip.iconName || (chip.icon && chip.icon in Feather.glyphMap);
        const iconName = (chip.iconName || chip.icon) as FeatherIconName;
        return (
          <View key={idx} style={styles.chip}>
            {isFeather ? (
              <Feather name={iconName} size={13} color={colors.brand} />
            ) : chip.icon ? (
              <Text style={styles.chipIcon}>{chip.icon}</Text>
            ) : null}
            <Text style={styles.chipText}>{chip.text}</Text>
          </View>
        );
      })}
    </View>
  );
}

export function Notice({ message, tone = 'error' }: { message: string; tone?: 'error' | 'info' | 'ok' }) {
  if (!message) return null;
  return (
    <View style={[styles.notice, tone === 'info' && styles.noticeInfo, tone === 'ok' && styles.noticeOk]}>
      <Text style={styles.noticeText}>{message}</Text>
    </View>
  );
}

export function errorText(error: unknown, fallback = 'Something went wrong. Please try again.'): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

/** Explicit UX for backend gates: 401/403/423/428/503. */
export function GateNotice({ error }: { error: unknown }) {
  if (!(error instanceof ApiError)) return <Notice message={errorText(error)} />;
  const gateLabel =
    error.status === 0
      ? error.code === 'request_timeout'
        ? 'Connection timed out'
        : 'Connection required'
      : error.gate === 'quiz'
        ? 'Quiz needed'
        : error.gate === 'quiet_hours'
          ? 'Quiet hours'
          : error.gate === 'screen_time'
            ? 'Screen-time limit'
            : error.gate === 'parent_verification'
              ? 'Parent verification'
              : error.gate === 'email_verification'
                ? 'Email check'
                : `Code ${error.status}`;
  return (
    <View style={styles.notice}>
      <Text style={styles.gateLabel}>{gateLabel}</Text>
      <Text style={styles.noticeText}>{error.message}</Text>
    </View>
  );
}

export function LoadingState({ message = 'Loading…' }: { message?: string }) {
  return (
    <View style={styles.loadingCenter}>
      <ActivityIndicator size="large" color={colors.brand} />
      {message ? <Text style={styles.centerText}>{message}</Text> : null}
    </View>
  );
}

export function EmptyState({
  title,
  body,
  icon = 'compass',
  actionLabel,
  onAction,
}: {
  title: string;
  body?: string;
  icon?: keyof typeof Feather.glyphMap;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <View style={styles.center}>
      <View style={styles.emptyIconBox}>
        <Feather name={icon} size={30} color={colors.brand} />
      </View>
      <Text style={styles.emptyTitle}>{title}</Text>
      {body ? <Text style={styles.centerText}>{body}</Text> : null}
      {actionLabel && onAction ? <Button label={actionLabel} onPress={onAction} variant="secondary" /> : null}
    </View>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <View style={styles.center}>
      <View style={styles.errorIconBox}>
        <Feather name="alert-circle" size={28} color={colors.muted} />
      </View>
      <Text style={styles.emptyTitle}>Something needs attention</Text>
      <Text style={styles.centerText}>{message}</Text>
      {onRetry ? <Button label="Try again" onPress={onRetry} variant="secondary" /> : null}
    </View>
  );
}

export function OfflineBanner({ online }: { online: boolean }) {
  if (online) return null;
  return (
    <View style={styles.offline}>
      <Text style={styles.offlineText}>You are offline. Changes will wait until you reconnect.</Text>
    </View>
  );
}

/** Shown when parent controls disable a feature instead of broken navigation. */
export function DisabledFeature({ feature }: { feature: string }) {
  return (
    <View style={styles.center}>
      <Text style={styles.emptyTitle}>{feature} is off</Text>
      <Text style={styles.centerText}>Your parent turned this off in controls. Ask them to enable it.</Text>
    </View>
  );
}

export function Skeleton({ lines = 3 }: { lines?: number }) {
  const shimmer = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(shimmer, { toValue: 1, duration: 900, useNativeDriver: true }),
        Animated.timing(shimmer, { toValue: 0, duration: 900, useNativeDriver: true }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [shimmer]);
  const opacity = shimmer.interpolate({ inputRange: [0, 1], outputRange: [0.4, 1] });
  return (
    <View style={styles.skeletonWrap}>
      {Array.from({ length: lines }).map((_, index) => (
        <Animated.View key={index} style={[styles.skeletonLine, { opacity }]} />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  card: {
    backgroundColor: colors.surface,
    borderRadius: 18,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: '#EFEFEF',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.04,
    shadowRadius: 10,
    elevation: 2,
    marginHorizontal: spacing.md,
    marginBottom: spacing.md,
  },
  header: { paddingHorizontal: spacing.md, paddingTop: spacing.md, paddingBottom: spacing.xs, marginBottom: spacing.xs },
  brandRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4 },
  backBtn: { marginLeft: -8, padding: 4 },
  headerLogo: { width: 28, height: 28, borderRadius: 8 },
  brand: { fontSize: 22, fontWeight: '800', color: colors.ink, letterSpacing: -0.5 },
  title: { fontSize: type.hero, fontWeight: '800', color: colors.ink, marginTop: 4 },
  subtitle: { fontSize: type.subtitle, color: colors.muted, marginTop: 6, lineHeight: 22 },
  button: {
    backgroundColor: colors.brand,
    borderRadius: 12,
    minHeight: 46,
    paddingHorizontal: spacing.lg,
    paddingVertical: 12,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: spacing.sm,
    shadowColor: colors.brand,
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.18,
    shadowRadius: 6,
    elevation: 2,
  },
  buttonSecondary: {
    backgroundColor: '#F8F9FA',
    borderWidth: 1,
    borderColor: '#E5E7EB',
    shadowOpacity: 0,
    elevation: 0,
  },
  buttonPressed: { opacity: 0.85, transform: [{ scale: 0.98 }] },
  buttonDisabled: { opacity: 0.55 },
  buttonText: { color: '#fff', fontWeight: '700', fontSize: type.body },
  buttonTextSecondary: { color: colors.ink },
  field: { marginTop: spacing.sm },
  labelRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 5 },
  label: { fontSize: type.caption, fontWeight: '700', color: colors.ink },
  input: {
    backgroundColor: '#F8F9FA',
    borderWidth: 1,
    borderColor: '#E5E7EB',
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 11,
    fontSize: 15,
    color: colors.ink,
  },
  inputError: { borderColor: colors.danger },
  fieldError: { color: colors.danger, fontSize: type.caption, marginTop: 4 },
  fieldHelper: { color: colors.muted, fontSize: 11, marginTop: 4 },
  stepContainer: { marginBottom: spacing.md },
  stepTracker: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    marginBottom: 6,
  },
  stepItemWrapper: { flex: 1, alignItems: 'center' },
  stepBadgeRow: { flexDirection: 'row', alignItems: 'center', width: '100%', justifyContent: 'center' },
  stepConnector: { flex: 1, height: 2, backgroundColor: '#E5E7EB' },
  stepConnectorSpacer: { flex: 1, height: 2, backgroundColor: 'transparent' },
  stepConnectorFilled: { backgroundColor: colors.brand },
  stepBadge: {
    width: 24,
    height: 24,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1,
  },
  stepBadgeActive: {
    backgroundColor: colors.brand,
    shadowColor: colors.brand,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.35,
    shadowRadius: 4,
    elevation: 3,
  },
  stepBadgeDone: { backgroundColor: '#10B981' },
  stepBadgeUpcoming: { backgroundColor: '#F3F4F6', borderWidth: 1, borderColor: '#E5E7EB' },
  stepBadgeNum: { fontSize: 11, fontWeight: '800' },
  stepBadgeNumActive: { color: '#FFFFFF' },
  stepBadgeNumUpcoming: { color: colors.muted },
  stepTitle: { fontSize: 11, fontWeight: '600', color: colors.muted, marginTop: 4, textAlign: 'center' },
  stepTitleActive: { color: colors.brand, fontWeight: '800' },
  stepTitleDone: { color: '#10B981', fontWeight: '700' },
  stepCurrentPill: {
    alignSelf: 'center',
    backgroundColor: '#EFF6FF',
    paddingHorizontal: 10,
    paddingVertical: 3,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: '#DBEAFE',
    marginTop: 4,
  },
  stepCurrentText: { fontSize: 10, fontWeight: '800', color: colors.brand, letterSpacing: 0.8 },
  chipsRow: { flexDirection: 'row', gap: 8, marginVertical: spacing.sm, justifyContent: 'center' },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: '#F3F4F6',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: radius.pill,
  },
  chipIcon: { fontSize: 13 },
  chipText: { fontSize: 12, fontWeight: '600', color: colors.ink },
  notice: { backgroundColor: '#FDECEC', borderRadius: 12, padding: spacing.sm + 2, marginTop: spacing.sm },
  noticeInfo: { backgroundColor: '#EFF6FF', borderWidth: 1, borderColor: '#DBEAFE' },
  noticeOk: { backgroundColor: '#ECFDF5', borderWidth: 1, borderColor: '#D1FAE5' },
  noticeText: { color: colors.ink, fontSize: type.body, lineHeight: 21 },
  gateLabel: { fontWeight: '800', fontSize: type.caption, color: colors.danger, marginBottom: 2, textTransform: 'uppercase', letterSpacing: 1 },
  center: { alignItems: 'center', justifyContent: 'center', padding: spacing.lg, gap: 8, minHeight: 140 },
  loadingCenter: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.lg,
    gap: 12,
    minHeight: 200,
  },
  emptyIconBox: {
    width: 68,
    height: 68,
    borderRadius: 34,
    backgroundColor: '#EFF6FF',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 8,
    borderWidth: 1,
    borderColor: '#DBEAFE',
  },
  errorIconBox: {
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: '#F3F4F6',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 4,
  },
  centerText: { color: colors.muted, fontSize: type.body, textAlign: 'center', lineHeight: 22 },
  emptyTitle: { fontSize: type.title, fontWeight: '800', color: colors.ink, textAlign: 'center' },
  offline: { backgroundColor: colors.ink, paddingVertical: 8, paddingHorizontal: spacing.md },
  offlineText: { color: '#fff', textAlign: 'center', fontSize: type.caption, fontWeight: '600' },
  skeletonWrap: { gap: 8, marginTop: spacing.sm },
  skeletonLine: { height: 16, borderRadius: 8, backgroundColor: colors.line },
});
