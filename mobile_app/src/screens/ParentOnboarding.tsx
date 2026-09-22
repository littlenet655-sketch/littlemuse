import { useEffect, useRef, useState } from 'react';
import { Image, Keyboard, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { Feather } from '@expo/vector-icons';
import { fetchParentEmailStatus, registerParent, resendParentEmail, verifyParentEmail } from '../api/auth';
import { useAuth } from '../auth/AuthProvider';
import type { AuthScreenProps } from '../navigation/types';
import { Button, Card, Field, Notice, Screen, StepIndicator, errorText } from '../ui/components';
import { colors, radius, spacing, type } from '../ui/tokens';

export function ParentRegisterScreen({ navigation }: AuthScreenProps<'ParentRegister'>) {
  const [username, setUsername] = useState('');
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [dob, setDob] = useState('');
  const [guardianAgreed, setGuardianAgreed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [submittedToken, setSubmittedToken] = useState<string | null>(null);
  /**
   * Synchronous double-tap guard: the `busy` render state does not stop a
   * rapid second tap dispatched before re-render. This ref check-and-sets
   * synchronously at the top of submit().
   */
  const registerBusyRef = useRef(false);
  const [error, setError] = useState('');
  const [fieldErrors, setFieldErrors] = useState<{
    fullName?: string;
    username?: string;
    email?: string;
    password?: string;
    dob?: string;
  }>({});
  const [keyboardHeight, setKeyboardHeight] = useState(0);

  const clearFieldError = (key: 'fullName' | 'username' | 'email' | 'password' | 'dob') =>
    setFieldErrors((prev) => (prev[key] ? { ...prev, [key]: undefined } : prev));

  /** Client-side validation before the register call; the server re-validates. */
  function validateRegister(): typeof fieldErrors {
    const errors: typeof fieldErrors = {};
    if (fullName.trim().length < 2) errors.fullName = 'Enter your full name.';
    if (!/^[A-Za-z0-9_.]{3,30}$/.test(username.trim()))
      errors.username = 'Use 3–30 letters, numbers, _ or .';
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim()))
      errors.email = 'Enter a valid email address.';
    if (password.length < 8) errors.password = 'Password must be at least 8 characters.';
    const dobMatch = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dob.trim());
    if (!dobMatch) {
      errors.dob = 'Use the format YYYY-MM-DD.';
    } else {
      const year = Number(dobMatch[1]);
      const month = Number(dobMatch[2]);
      const day = Number(dobMatch[3]);
      const birth = new Date(year, month - 1, day);
      const validDate =
        birth.getFullYear() === year && birth.getMonth() === month - 1 && birth.getDate() === day;
      if (!validDate) {
        errors.dob = 'Enter a valid date.';
      } else {
        const today = new Date();
        let age = today.getFullYear() - birth.getFullYear();
        const hadBirthday =
          today.getMonth() > birth.getMonth() ||
          (today.getMonth() === birth.getMonth() && today.getDate() >= birth.getDate());
        if (!hadBirthday) age -= 1;
        if (age < 18) errors.dob = 'You must be at least 18 years old.';
      }
    }
    return errors;
  }

  const scrollRef = useRef<ScrollView>(null);

  useEffect(() => {
    const showSub = Keyboard.addListener(
      Platform.OS === 'ios' ? 'keyboardWillShow' : 'keyboardDidShow',
      (e) => {
        setKeyboardHeight(e.endCoordinates.height);
      }
    );
    const hideSub = Keyboard.addListener(
      Platform.OS === 'ios' ? 'keyboardWillHide' : 'keyboardDidHide',
      () => {
        setKeyboardHeight(0);
      }
    );
    return () => {
      showSub.remove();
      hideSub.remove();
    };
  }, []);

  const scrollToInput = (offsetY: number) => {
    setTimeout(() => {
      scrollRef.current?.scrollTo({ y: offsetY, animated: true });
    }, 120);
  };

  async function submit() {
    if (registerBusyRef.current) return;
    registerBusyRef.current = true;
    try {
      if (busy || submitted) return;
      if (!guardianAgreed) {
        setError('You must certify that you are the legal adult guardian.');
        return;
      }
      const validation = validateRegister();
      setFieldErrors(validation);
      if (Object.keys(validation).length > 0) {
        setError('Please fix the highlighted fields.');
        return;
      }
      setBusy(true);
      setError('');
      try {
        const response = await registerParent({
          username: username.trim(),
          full_name: fullName.trim(),
          email: email.trim(),
          password,
          dob: dob.trim(),
        });
        // Registration succeeded: remember the pending token so going back from
        // the OTP screen offers "Continue to Verification" instead of orphaning
        // the first token with a second registration.
        setSubmittedToken(response.pending_token);
        setSubmitted(true);
        navigation.navigate('OtpVerify', {
          pendingToken: response.pending_token,
          emailSent: response.email_sent,
          // A release client never consumes an OTP returned by an API, even if a
          // server is accidentally misconfigured. Explicit dev builds retain the
          // local-only escape hatch for isolated testing.
          devCode: __DEV__ ? response.dev_code : undefined,
        });
      } catch (err) {
        setError(errorText(err));
      } finally {
        setBusy(false);
      }
    } finally {
      registerBusyRef.current = false;
    }
  }

  return (
    <Screen>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 64 : 0}
        style={styles.keyboardContainer}
      >
        <ScrollView
          ref={scrollRef}
          style={styles.scroll}
          keyboardShouldPersistTaps="handled"
          keyboardDismissMode="on-drag"
          automaticallyAdjustKeyboardInsets={Platform.OS === 'ios'}
          contentContainerStyle={[
            styles.scrollContent,
            { paddingBottom: keyboardHeight > 0 ? keyboardHeight + 40 : spacing.xl },
          ]}
          showsVerticalScrollIndicator={true}
          nestedScrollEnabled={true}
          bounces={true}
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
            <Text style={styles.heroSubtitle}>Create your verified parent account to supervise safely</Text>
          </View>

          <Card>
            <StepIndicator step={1} total={2} label="Guardian Details" />

            <Field
              label="Full Name"
              placeholder="e.g. Dr. Ramesh Kumar"
              value={fullName}
              onChangeText={(text) => { setFullName(text); clearFieldError('fullName'); }}
              onFocus={() => scrollToInput(20)}
              error={fieldErrors.fullName}
            />
            <Field
              label="Parent Username"
              placeholder="e.g. dad_ramesh"
              autoCapitalize="none"
              autoCorrect={false}
              helper="3–30 letters, numbers, _ or ."
              value={username}
              onChangeText={(text) => { setUsername(text); clearFieldError('username'); }}
              onFocus={() => scrollToInput(75)}
              error={fieldErrors.username}
            />
            <Field
              label="Email Address"
              placeholder="parent@example.com"
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="email-address"
              value={email}
              onChangeText={(text) => { setEmail(text); clearFieldError('email'); }}
              onFocus={() => scrollToInput(135)}
              error={fieldErrors.email}
            />
            <Field
              label="Date of Birth (YYYY-MM-DD)"
              placeholder="1990-05-14"
              helper="You must be at least 18 years old. Server validates age."
              keyboardType="numbers-and-punctuation"
              value={dob}
              onChangeText={(text) => { setDob(text); clearFieldError('dob'); }}
              onFocus={() => scrollToInput(195)}
              error={fieldErrors.dob}
            />
            <Field
              label="Password"
              placeholder="Minimum 8 characters"
              secureTextEntry={!showPassword}
              autoCapitalize="none"
              autoCorrect={false}
              textContentType="newPassword"
              value={password}
              onChangeText={(text) => { setPassword(text); clearFieldError('password'); }}
              onFocus={() => scrollToInput(265)}
              error={fieldErrors.password}
              rightAction={
                <Pressable onPress={() => setShowPassword((prev) => !prev)} hitSlop={8}>
                  <Text style={styles.pwdToggle}>{showPassword ? 'Hide' : 'Show'}</Text>
                </Pressable>
              }
            />

            <Pressable
              accessibilityRole="checkbox"
              accessibilityState={{ checked: guardianAgreed }}
              onPress={() => setGuardianAgreed((prev) => !prev)}
              style={styles.guardianCheckboxRow}
            >
              <View style={[styles.checkboxBox, guardianAgreed && styles.checkboxBoxChecked]}>
                {guardianAgreed ? <Feather name="check" size={13} color="#FFFFFF" strokeWidth={3} /> : null}
              </View>
              <Text style={styles.guardianCheckboxLabel}>
                I certify that I am the legal adult parent or guardian responsible for child safety and supervision.
              </Text>
            </Pressable>

            <View style={styles.flowInfoBox}>
              <Feather name="info" size={16} color="#0284C7" />
              <Text style={styles.flowInfoText}>
                Next: LittleNet sends a 6-digit email code to verify ownership of your address.
              </Text>
            </View>

            {error ? <Notice message={error} /> : null}

            <Button
              label={submitted ? 'Continue to Verification →' : busy ? 'Creating Account…' : 'Create Account →'}
              onPress={() => {
                if (submitted && submittedToken) {
                  navigation.navigate('OtpVerify', { pendingToken: submittedToken });
                  return;
                }
                void submit();
              }}
              loading={busy}
              disabled={busy}
            />

            <View style={styles.signupBox}>
              <Text style={styles.signupMuted}>Already registered?</Text>
              <Pressable onPress={() => navigation.navigate('Login')} hitSlop={6}>
                <Text style={styles.signupLinkText}>Log In as Parent →</Text>
              </Pressable>
            </View>
          </Card>
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}

export function OtpVerifyScreen({ route }: AuthScreenProps<'OtpVerify'>) {
  const { signIn } = useAuth();
  const { pendingToken, devCode } = route.params;
  const [otp, setOtp] = useState(devCode || '');
  const otpInputRef = useRef<TextInput>(null);
  const [busy, setBusy] = useState(false);
  const [resending, setResending] = useState(false);
  const [error, setError] = useState('');
  /**
   * Synchronous double-tap guards (render-state flags don't stop two taps
   * dispatched before re-render). Verify and resend also block each other:
   * the server rotates the OTP code on resend, so a verify in flight during
   * a resend would spuriously fail, and vice versa.
   */
  const verifyBusyRef = useRef(false);
  const resendBusyRef = useRef(false);
  const [info, setInfo] = useState(
    devCode
      ? `Verification code: ${devCode} (expires in 10 minutes)`
      : route.params.emailSent === false
      ? 'Email delivery may be slow. You can resend the code below.'
      : ''
  );

  useEffect(() => {
    if (devCode) return undefined;

    let cancelled = false;
    const checkDelivery = async () => {
      try {
        const response = await fetchParentEmailStatus(pendingToken);
        if (cancelled) return;

        if (response.delivery_failed) {
          const message =
            response.status === 'SUPPRESSED'
              ? 'This email address is suppressed after an earlier delivery problem. Check the address or use a different email.'
              : response.status === 'BOUNCED'
                ? 'The email provider rejected this address. Check that the mailbox exists and use a valid email.'
                : 'The verification email could not be delivered. Check the address and try again.';
          setError(message);
          setInfo('');
          return;
        }

        if (response.status === 'DELIVERED') {
          setError('');
          setInfo('Verification email delivered. Enter the 6-digit code from your inbox.');
        } else if (response.status === 'DELIVERY_DELAYED') {
          setInfo('Your email provider reports a delivery delay. You can wait or resend the code.');
        }
      } catch {
        // Delivery telemetry is advisory; OTP entry and resend must keep working
        // even if the status endpoint is temporarily unavailable.
      }
    };

    void checkDelivery();
    const timer = setInterval(() => void checkDelivery(), 4000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [devCode, pendingToken]);

  async function submit() {
    if (verifyBusyRef.current || resendBusyRef.current) return;
    verifyBusyRef.current = true;
    try {
      if (otp.trim().length !== 6) {
        setError('Enter the 6-digit code from your email.');
        return;
      }
      setBusy(true);
      setError('');
      try {
        // Email OTP is the final parent activation step: the backend returns a
        // signed-in session directly. Sign in without a parent selfie step —
        // device authentication gates Parent Mode locally instead.
        const response = await verifyParentEmail(pendingToken, otp.trim());
        await signIn(response);
      } catch (err) {
        setError(errorText(err));
      } finally {
        setBusy(false);
      }
    } finally {
      verifyBusyRef.current = false;
    }
  }

  async function resend() {
    if (resendBusyRef.current || verifyBusyRef.current) return;
    resendBusyRef.current = true;
    try {
      if (resending || busy) return;
      setResending(true);
      setError('');
      try {
        const response = await resendParentEmail(pendingToken);
        if (__DEV__ && response.dev_code) {
          setOtp(response.dev_code);
          setInfo(`Verification code: ${response.dev_code} (expires in 10 minutes)`);
        } else {
          setInfo(response.ok ? 'A fresh code is on its way. It expires in 10 minutes.' : (response.error ?? 'Resend failed. Try again.'));
        }
      } catch (err) {
        setError(errorText(err));
      } finally {
        setResending(false);
      }
    } finally {
      resendBusyRef.current = false;
    }
  }

  const [keyboardHeight, setKeyboardHeight] = useState(0);
  const scrollRef = useRef<ScrollView>(null);

  useEffect(() => {
    const showSub = Keyboard.addListener(
      Platform.OS === 'ios' ? 'keyboardWillShow' : 'keyboardDidShow',
      (e) => {
        setKeyboardHeight(e.endCoordinates.height);
      }
    );
    const hideSub = Keyboard.addListener(
      Platform.OS === 'ios' ? 'keyboardWillHide' : 'keyboardDidHide',
      () => {
        setKeyboardHeight(0);
      }
    );
    return () => {
      showSub.remove();
      hideSub.remove();
    };
  }, []);

  return (
    <Screen>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 64 : 0}
        style={styles.keyboardContainer}
      >
        <ScrollView
          ref={scrollRef}
          style={styles.scroll}
          keyboardShouldPersistTaps="handled"
          keyboardDismissMode="on-drag"
          automaticallyAdjustKeyboardInsets={Platform.OS === 'ios'}
          contentContainerStyle={[
            styles.scrollContent,
            { paddingBottom: keyboardHeight > 0 ? keyboardHeight + 40 : spacing.xl },
          ]}
          showsVerticalScrollIndicator={true}
          nestedScrollEnabled={true}
          bounces={true}
        >
          <View style={styles.headerHero}>
            <View style={styles.heroIconBadge}>
              <Feather name="mail" size={30} color={colors.brand} />
            </View>
            <Text style={styles.heroBrandName}>Check your email</Text>
            <Text style={styles.heroSubtitle}>We sent a 6-digit verification code to your email</Text>
          </View>

          <Card>
            <StepIndicator step={2} total={2} label="Email Verification" />

            <View style={styles.otpFieldWrap}>
              <Text style={styles.otpLabel}>6-DIGIT VERIFICATION CODE</Text>
              <Pressable
                style={styles.otpCells}
                accessibilityRole="button"
                accessibilityLabel="6-digit verification code"
                onPress={() => otpInputRef.current?.focus()}
              >
                {Array.from({ length: 6 }, (_, index) => {
                  const digit = otp[index] ?? '';
                  const active = Math.min(otp.length, 5) === index && otp.length < 6;
                  return (
                    <View key={index} style={[styles.otpCell, active && styles.otpCellActive]}>
                      <Text style={styles.otpDigit}>{digit}</Text>
                      {active && !digit ? <View style={styles.otpCursor} /> : null}
                    </View>
                  );
                })}
              </Pressable>
              <TextInput
                ref={otpInputRef}
                value={otp}
                onChangeText={(value) => setOtp(value.replace(/\D/g, '').slice(0, 6))}
                keyboardType="number-pad"
                maxLength={6}
                autoFocus
                caretHidden
                textContentType="oneTimeCode"
                autoComplete="sms-otp"
                returnKeyType="done"
                onSubmitEditing={submit}
                accessibilityLabel="Enter 6-digit verification code"
                onFocus={() => {
                  setTimeout(() => scrollRef.current?.scrollTo({ y: 60, animated: true }), 100);
                }}
                style={styles.otpHiddenInput}
              />
              <Text style={styles.otpHelperText}>The code expires in 10 minutes and is single-use.</Text>
            </View>

            {error ? <Notice message={error} /> : null}
            {info ? <Notice tone="info" message={info} /> : null}

            <Button label={busy ? 'Verifying…' : 'Verify Email →'} onPress={submit} loading={busy} disabled={busy || resending} />
            <Button label={resending ? 'Resending Code…' : 'Resend Verification Code'} variant="secondary" onPress={resend} disabled={resending || busy} />

            <View style={styles.flowInfoBox}>
              <Feather name="shield" size={16} color="#0284C7" />
              <Text style={styles.flowInfoText}>
                Your account activates as soon as your email ownership is verified.
              </Text>
            </View>
          </Card>
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  keyboardContainer: { flex: 1 },
  scroll: { flex: 1 },
  scrollContent: { paddingBottom: spacing.xl },
  headerHero: { alignItems: 'center', paddingTop: spacing.md, paddingBottom: spacing.sm, paddingHorizontal: spacing.lg },
  heroLogoBadge: {
    width: 58,
    height: 58,
    borderRadius: 16,
    overflow: 'hidden',
    shadowColor: '#0095F6',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.22,
    shadowRadius: 10,
    elevation: 4,
    marginBottom: 4,
  },
  heroLogo: { width: 58, height: 58, borderRadius: 16 },
  heroIconBadge: {
    width: 68,
    height: 68,
    borderRadius: 34,
    backgroundColor: '#E8F4FE',
    borderWidth: 1,
    borderColor: '#BFDBFE',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 6,
  },
  heroBrandName: { color: colors.ink, fontSize: 24, fontWeight: '900', letterSpacing: -0.5, marginTop: 4 },
  heroSubtitle: { color: colors.muted, fontSize: 13, textAlign: 'center', marginTop: 3, lineHeight: 18, maxWidth: 320 },
  pwdToggle: { fontSize: 12, fontWeight: '700', color: colors.brand },
  guardianCheckboxRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
    marginTop: spacing.md,
    backgroundColor: '#F8FAFC',
    borderWidth: 1,
    borderColor: '#E2E8F0',
    borderRadius: 12,
    padding: 12,
  },
  checkboxBox: {
    width: 20,
    height: 20,
    borderRadius: 5,
    borderWidth: 1.5,
    borderColor: '#CBD5E1',
    backgroundColor: '#FFFFFF',
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 2,
  },
  checkboxBoxChecked: {
    backgroundColor: colors.brand,
    borderColor: colors.brand,
  },
  checkmarkText: {
    color: '#FFFFFF',
    fontSize: 12,
    fontWeight: '900',
  },
  guardianCheckboxLabel: {
    flex: 1,
    fontSize: 12,
    lineHeight: 18,
    color: '#475569',
    fontWeight: '500',
  },
  flowInfoBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: '#F0F9FF',
    borderWidth: 1,
    borderColor: '#BAE6FD',
    borderRadius: 12,
    padding: 10,
    marginTop: spacing.md,
  },
  flowInfoIcon: { fontSize: 14 },
  flowInfoText: { flex: 1, fontSize: 12, color: '#0369A1', lineHeight: 17, fontWeight: '500' },
  signupBox: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingTop: 12,
    marginTop: spacing.md,
    borderTopWidth: 1,
    borderTopColor: '#F3F4F6',
    width: '100%',
    justifyContent: 'center',
  },
  signupMuted: { fontSize: 13, color: colors.muted },
  signupLinkText: { fontSize: 13, fontWeight: '700', color: colors.brand },
  otpFieldWrap: { marginTop: spacing.sm },
  otpLabel: { fontSize: 11, fontWeight: '800', color: colors.muted, letterSpacing: 0.8, textAlign: 'center', marginBottom: 6 },
  otpCells: { flexDirection: 'row', justifyContent: 'center', gap: 8 },
  otpCell: {
    width: 44,
    height: 54,
    borderRadius: 12,
    borderWidth: 1.5,
    borderColor: '#CBD5E1',
    backgroundColor: '#FFFFFF',
    alignItems: 'center',
    justifyContent: 'center',
  },
  otpCellActive: { borderColor: colors.brand, shadowColor: colors.brand, shadowOpacity: 0.16, shadowRadius: 6, elevation: 2 },
  otpDigit: { fontSize: 24, fontWeight: '800', color: colors.ink },
  otpCursor: { width: 2, height: 24, borderRadius: 1, backgroundColor: colors.brand },
  otpHiddenInput: { position: 'absolute', width: 1, height: 1, opacity: 0 },
  otpHelperText: { fontSize: 11, color: colors.muted, textAlign: 'center', marginTop: 6 },
});
