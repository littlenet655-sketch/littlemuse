import { useRef, useState } from 'react';
import { Image, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Feather } from '@expo/vector-icons';
import { login } from '../api/auth';
import type { LoginMode } from '../api/auth';
import { ApiError } from '../api/client';
import { useAuth } from '../auth/AuthProvider';
import { BrandHeader, Button, Card, Field, Notice, Screen, errorText } from '../ui/components';
import type { AuthScreenProps } from '../navigation/types';
import { colors, radius, spacing, type } from '../ui/tokens';

type FeatherIconName = keyof typeof Feather.glyphMap;

const MODES: {
  label: string;
  icon: FeatherIconName;
  value: LoginMode;
  subtitle: string;
}[] = [
  {
    label: 'Kids Mode',
    icon: 'smile',
    value: 'kids',
    subtitle: 'A safe, AI-guided social world for children',
  },
  {
    label: 'Parent Mode',
    icon: 'user-check',
    value: 'parent',
    subtitle: 'Parent supervision, screen-time & safety controls',
  },
  {
    label: 'Admin',
    icon: 'shield',
    value: 'admin',
    subtitle: 'Safety moderator & platform admin sign-in',
  },
];

// Admin sign-in stays available through the API, but it is not a peer login
// choice for parents and children: only kids/parent appear as mode pills.
const PILL_MODES = MODES.filter((m) => m.value !== 'admin');

export function WelcomeScreen({ navigation }: AuthScreenProps<'Welcome'>) {
  return (
    <Screen hasNativeHeader={false}>
      <ScrollView contentContainerStyle={styles.welcomeScroll}>
        <View style={styles.welcomeHero}>
          <View style={styles.logoBadge}>
            <Image
              source={require('../../assets/app_logo.png')}
              style={styles.logoImage}
              resizeMode="cover"
            />
          </View>
          <Text style={styles.wordmark}>LittleNet</Text>
          <Text style={styles.heroTitle}>A kinder place to learn and share.</Text>
          <Text style={styles.heroBody}>Parents verify first. Kids explore, create, and connect with safety built in.</Text>
        </View>
        <View style={styles.authActions}>
          <Text style={styles.chooseRoleTitle}>Choose how you are entering LittleNet</Text>
          {MODES.map((item) => (
            <Pressable
              key={item.value}
              accessibilityRole="button"
              accessibilityLabel={`${item.label} sign in`}
              onPress={() => navigation.navigate('Login', { mode: item.value })}
              style={styles.roleCard}
            >
              <View style={styles.roleIcon}>
                <Feather name={item.icon} size={20} color={colors.brand} />
              </View>
              <View style={styles.roleCopy}>
                <Text style={styles.roleTitle}>{item.label}</Text>
                <Text style={styles.roleSubtitle}>{item.subtitle}</Text>
              </View>
              <Feather name="chevron-right" size={20} color={colors.muted} />
            </Pressable>
          ))}
          <Button label="Parent sign-up" variant="secondary" onPress={() => navigation.navigate('ParentRegister')} />
          <Button label="Kids face login" variant="secondary" onPress={() => navigation.navigate('FaceLogin')} />
        </View>
      </ScrollView>
    </Screen>
  );
}

export function LoginScreen({ navigation, route }: AuthScreenProps<'Login'>) {
  const { signIn } = useAuth();
  const [mode, setMode] = useState<LoginMode>(route.params?.mode ?? 'kids');
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  /**
   * Synchronous double-tap guard: the `busy` render state does not stop a
   * rapid second tap dispatched before re-render. This ref check-and-sets
   * synchronously at the top of submit().
   */
  const submitBusyRef = useRef(false);

  const currentSubtitle =
    MODES.find((m) => m.value === mode)?.subtitle ?? 'A safe, AI-guided social world for children';

  async function submit() {
    if (submitBusyRef.current) return;
    submitBusyRef.current = true;
    try {
      if (!identifier.trim() || !password) {
        setError('Enter your username/email and password.');
        return;
      }
      setBusy(true);
      setError('');
      try {
        const response = await login(identifier.trim(), password, mode);
        await signIn(response);
      } catch (err) {
        if (err instanceof ApiError && err.code === 'parent_verification_required') {
          const pendingToken = typeof err.details.pending_token === 'string' ? err.details.pending_token : '';
          navigation.navigate('OtpVerify', { pendingToken });
          return;
        }
        setError(errorText(err));
      } finally {
        setBusy(false);
      }
    } finally {
      submitBusyRef.current = false;
    }
  }

  const identifierLabel =
    mode === 'parent'
      ? 'Parent Email Address'
      : mode === 'admin'
        ? 'Admin Email Address'
        : 'Username or Child Email';

  const identifierPlaceholder =
    mode === 'parent'
      ? 'parent@example.com'
      : mode === 'admin'
        ? 'admin@example.com'
        : 'Enter username or child email';

  return (
    <Screen>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 64 : 30}
        style={{ flex: 1 }}
      >
        <ScrollView
          keyboardShouldPersistTaps="handled"
          keyboardDismissMode="on-drag"
          automaticallyAdjustKeyboardInsets={true}
          contentContainerStyle={styles.scrollContent}
        >
        <View style={styles.headerHero}>
          <View style={styles.heroLogoBadge}>
            <Image
              source={require('../../assets/app_logo.png')}
              style={styles.heroLogo}
              resizeMode="cover"
            />
          </View>
          <Text style={styles.heroBrandName}>LittleNet</Text>
          <Text style={styles.heroSubtitle}>{currentSubtitle}</Text>
        </View>

        <Card>
          <View style={styles.modePillContainer} accessibilityRole="radiogroup">
            {PILL_MODES.map((item) => {
              const active = item.value === mode;
              return (
                <Pressable
                  key={item.value}
                  accessibilityRole="radio"
                  accessibilityState={{ selected: active }}
                  accessibilityLabel={`${item.label} login`}
                  onPress={() => {
                    setMode(item.value);
                    setError('');
                  }}
                  style={[styles.modePill, active && styles.modePillActive]}
                >
                  <Feather name={item.icon} size={14} color={active ? '#FFFFFF' : colors.muted} />
                  <Text style={[styles.modePillText, active && styles.modePillTextActive]}>
                    {item.label}
                  </Text>
                </Pressable>
              );
            })}
          </View>

          <Field
            label={identifierLabel}
            placeholder={identifierPlaceholder}
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType={mode === 'kids' ? 'default' : 'email-address'}
            value={identifier}
            onChangeText={setIdentifier}
          />

          <Field
            label="Password"
            placeholder="Enter your password"
            secureTextEntry={!showPassword}
            value={password}
            onChangeText={setPassword}
            rightAction={
              <Pressable onPress={() => setShowPassword((prev) => !prev)} hitSlop={12} style={styles.linkHit}>
                <Text style={styles.pwdToggle}>{showPassword ? 'Hide' : 'Show'}</Text>
              </Pressable>
            }
          />

          {error ? <Notice message={error} /> : null}

          <Button label={busy ? 'Logging in…' : 'Log In'} onPress={submit} loading={busy} disabled={busy} />

          {mode === 'kids' ? (
            <>
              <View style={styles.orDivider}>
                <View style={styles.dividerLine} />
                <Text style={styles.dividerText}>OR</Text>
                <View style={styles.dividerLine} />
              </View>

              <Pressable
                accessibilityRole="button"
                onPress={() => navigation.navigate('FaceLogin')}
                style={styles.faceLoginPill}
              >
                <Feather name="camera" size={18} color="#0095F6" />
                <Text style={styles.faceLoginText}>Kids Face ID Login</Text>
              </Pressable>
            </>
          ) : null}

          <View style={styles.authLinksContainer}>
            <Pressable onPress={() => navigation.navigate('ForgotPassword')} hitSlop={12} style={styles.linkHit}>
              <Text style={styles.forgotPwdLink}>Forgot your password?</Text>
            </Pressable>

            {mode !== 'admin' ? (
              <View style={styles.signupBox}>
                <Text style={styles.signupMuted}>
                  {mode === 'parent' ? 'New to LittleNet?' : 'Need an account?'}
                </Text>
                <Pressable onPress={() => navigation.navigate('ParentRegister')} hitSlop={12} style={styles.linkHit}>
                  <Text style={styles.signupLinkText}>Parent Sign Up →</Text>
                </Pressable>
              </View>
            ) : null}

            {mode !== 'admin' ? (
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Admin sign-in"
                onPress={() => {
                  setMode('admin');
                  setError('');
                }}
                hitSlop={12}
                style={styles.linkHit}
              >
                <Text style={styles.adminLinkText}>Admin sign-in</Text>
              </Pressable>
            ) : null}
          </View>
        </Card>
      </ScrollView>
    </KeyboardAvoidingView>
  </Screen>
  );
}

const styles = StyleSheet.create({
  welcomeScroll: { flexGrow: 1, justifyContent: 'center', paddingBottom: spacing.xl },
  scrollContent: { paddingBottom: spacing.xl },
  welcomeHero: { paddingHorizontal: spacing.lg, paddingTop: spacing.xl, paddingBottom: spacing.lg, alignItems: 'center' },
  headerHero: { alignItems: 'center', paddingTop: spacing.lg, paddingBottom: spacing.md, paddingHorizontal: spacing.lg },
  heroLogoBadge: {
    width: 60,
    height: 60,
    borderRadius: 16,
    shadowColor: '#0095F6',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.26,
    shadowRadius: 14,
    elevation: 5,
    marginBottom: spacing.xs,
  },
  heroLogo: { width: 60, height: 60, borderRadius: 16 },
  heroBrandName: { color: colors.ink, fontSize: 26, fontWeight: '900', letterSpacing: -0.5, marginTop: 4 },
  heroSubtitle: { color: colors.muted, fontSize: 13, textAlign: 'center', marginTop: 4, lineHeight: 18, maxWidth: 300 },
  logoBadge: {
    width: 68,
    height: 68,
    borderRadius: 18,
    shadowColor: '#0095F6',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.28,
    shadowRadius: 16,
    elevation: 6,
    marginBottom: spacing.md,
  },
  logoImage: { width: 68, height: 68, borderRadius: 18 },
  wordmark: { color: colors.ink, fontSize: 32, fontWeight: '900', letterSpacing: -1 },
  heroTitle: { color: colors.ink, fontSize: type.hero, lineHeight: 30, fontWeight: '800', textAlign: 'center', marginTop: spacing.md },
  heroBody: { color: colors.muted, fontSize: type.body, lineHeight: 21, textAlign: 'center', marginTop: spacing.sm, maxWidth: 310 },
  authActions: { paddingHorizontal: spacing.md, marginTop: spacing.sm, gap: 12 },
  chooseRoleTitle: { color: colors.ink, fontSize: 15, fontWeight: '800', textAlign: 'center', marginBottom: 2 },
  roleCard: {
    minHeight: 74,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#E2E8F0',
    backgroundColor: colors.surface,
  },
  roleIcon: {
    width: 42,
    height: 42,
    borderRadius: 21,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#EFF6FF',
  },
  roleCopy: { flex: 1 },
  roleTitle: { color: colors.ink, fontSize: 15, fontWeight: '800' },
  roleSubtitle: { color: colors.muted, fontSize: 12, lineHeight: 17, marginTop: 2 },
  modePillContainer: {
    flexDirection: 'row',
    backgroundColor: '#F3F4F6',
    borderRadius: radius.pill,
    padding: 3,
    marginBottom: spacing.md,
    gap: 3,
  },
  modePill: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 5,
    minHeight: 44,
    paddingVertical: 9,
    borderRadius: radius.pill,
  },
  modePillActive: {
    backgroundColor: colors.brand,
    shadowColor: colors.brand,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.25,
    shadowRadius: 4,
    elevation: 2,
  },
  modePillText: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.muted,
  },
  modePillTextActive: {
    color: '#FFFFFF',
    fontWeight: '800',
  },
  pwdToggle: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.brand,
  },
  orDivider: {
    flexDirection: 'row',
    alignItems: 'center',
    marginVertical: spacing.md,
    gap: spacing.sm,
  },
  dividerLine: {
    flex: 1,
    height: 1,
    backgroundColor: '#E5E7EB',
  },
  dividerText: {
    fontSize: 11,
    fontWeight: '700',
    color: colors.muted,
    letterSpacing: 1,
  },
  faceLoginPill: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    backgroundColor: '#EFF6FF',
    borderWidth: 1,
    borderColor: '#BFDBFE',
    borderRadius: 12,
    paddingVertical: 12,
  },
  faceLoginText: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.brand,
  },
  linkHit: {
    paddingVertical: 10,
    paddingHorizontal: 12,
  },
  adminLinkText: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.muted,
  },
  authLinksContainer: {
    marginTop: spacing.md,
    alignItems: 'center',
    gap: 12,
  },
  forgotPwdLink: {
    fontSize: 13,
    color: colors.muted,
    fontWeight: '600',
  },
  signupBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: '#F3F4F6',
    width: '100%',
    justifyContent: 'center',
  },
  signupMuted: {
    fontSize: 13,
    color: colors.muted,
  },
  signupLinkText: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.brand,
  },
});
