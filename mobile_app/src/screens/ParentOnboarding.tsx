import { useEffect, useMemo, useRef, useState } from 'react';
import { Image, Keyboard, KeyboardAvoidingView, Modal, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { Feather } from '@expo/vector-icons';
import { fetchParentEmailStatus, registerParent, resendParentEmail, verifyParentEmail } from '../api/auth';
import { useAuth } from '../auth/AuthProvider';
import type { AuthScreenProps } from '../navigation/types';
import { Button, Card, Field, Notice, Screen, StepIndicator, errorText } from '../ui/components';
import { colors, radius, spacing, type } from '../ui/tokens';
import { OTP_LENGTH, applyOtpBackspace, applyOtpInput, cellsFromCode } from './otpCells';

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

const MONTH_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function getDaysInMonth(year: number, month1Indexed: number): number {
  return new Date(year, month1Indexed, 0).getDate();
}

/**
 * Interactive Date of Birth Picker (Task 14).
 * Enforces the visual 18+ requirement, disallows future dates,
 * serializes canonical YYYY-MM-DD for the backend, handles cancellation gracefully,
 * and maintains accessibility on Android and iOS.
 */
interface ParentDobPickerProps {
  value: string; // canonical 'YYYY-MM-DD'
  onChange: (canonical: string) => void;
  error?: string;
}

function ParentDobPicker({ value, onChange, error }: ParentDobPickerProps) {
  const [modalOpen, setModalOpen] = useState(false);

  const today = useMemo(() => new Date(), []);
  const maxYear = today.getFullYear() - 18;
  const minYear = today.getFullYear() - 100;
  const maxMonth = today.getMonth() + 1; // 1-indexed
  const maxDay = today.getDate();

  // Parse existing canonical value or default to 25 years ago
  const parsed = useMemo(() => {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value.trim());
    if (match) {
      const y = Number(match[1]);
      const m = Number(match[2]);
      const d = Number(match[3]);
      return { year: y, month: m, day: d };
    }
    return { year: today.getFullYear() - 25, month: 1, day: 1 };
  }, [value, today]);

  const [tempYear, setTempYear] = useState(parsed.year);
  const [tempMonth, setTempMonth] = useState(parsed.month);
  const [tempDay, setTempDay] = useState(parsed.day);

  // Sync temp state whenever modal opens or value changes
  useEffect(() => {
    setTempYear(parsed.year);
    setTempMonth(parsed.month);
    setTempDay(parsed.day);
  }, [parsed, modalOpen]);

  // Clamp month & day when year changes
  const daysInCurrentMonth = useMemo(() => getDaysInMonth(tempYear, tempMonth), [tempYear, tempMonth]);

  useEffect(() => {
    if (tempYear === maxYear && tempMonth > maxMonth) {
      setTempMonth(maxMonth);
    }
  }, [tempYear, tempMonth, maxYear, maxMonth]);

  useEffect(() => {
    let maxAllowedDay = daysInCurrentMonth;
    if (tempYear === maxYear && tempMonth === maxMonth && maxDay < maxAllowedDay) {
      maxAllowedDay = maxDay;
    }
    if (tempDay > maxAllowedDay) {
      setTempDay(maxAllowedDay);
    }
  }, [tempYear, tempMonth, tempDay, daysInCurrentMonth, maxYear, maxMonth, maxDay]);

  const formattedDisplay = useMemo(() => {
    if (!value) return '';
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value.trim());
    if (match) {
      const y = Number(match[1]);
      const m = Number(match[2]) - 1;
      const d = Number(match[3]);
      return `${MONTH_NAMES[m]} ${d}, ${y}`;
    }
    return value;
  }, [value]);

  const handleConfirm = () => {
    const mm = String(tempMonth).padStart(2, '0');
    const dd = String(tempDay).padStart(2, '0');
    const canonical = `${tempYear}-${mm}-${dd}`;
    onChange(canonical);
    setModalOpen(false);
  };

  const handleCancel = () => {
    setModalOpen(false);
  };

  return (
    <View style={styles.dobWrapper}>
      <View style={styles.dobLabelRow}>
        <Text style={styles.dobLabel}>Date of Birth</Text>
        <View style={styles.dob18Badge}>
          <Text style={styles.dob18BadgeText}>18+ Adult Required</Text>
        </View>
      </View>

      <Pressable
        style={[styles.dobTrigger, Boolean(error) && styles.dobTriggerError]}
        onPress={() => setModalOpen(true)}
        accessibilityRole="button"
        accessibilityLabel={value ? `Date of birth: ${formattedDisplay}. Tap to change.` : 'Select date of birth'}
        hitSlop={8}
      >
        <View style={styles.dobTriggerLeft}>
          <Feather name="calendar" size={18} color={value ? colors.brand : colors.muted} />
          <Text style={[styles.dobTriggerValue, !value && styles.dobTriggerPlaceholder]}>
            {formattedDisplay ? `${formattedDisplay} (${value})` : 'Select your date of birth'}
          </Text>
        </View>
        <Feather name="chevron-down" size={18} color={colors.muted} />
      </Pressable>

      {error ? (
        <Text style={styles.dobErrorText}>{error}</Text>
      ) : (
        <Text style={styles.dobHelperText}>
          Must be at least 18 years old. Server validates age authoritatively.
        </Text>
      )}

      {/* Interactive Date Picker Modal */}
      <Modal
        visible={modalOpen}
        animationType="slide"
        transparent={true}
        onRequestClose={handleCancel}
        accessibilityViewIsModal={true}
      >
        <View style={styles.dobModalBackdrop}>
          <Pressable style={styles.dobModalDismissArea} onPress={handleCancel} accessibilityLabel="Cancel" />
          <View style={styles.dobModalSheet} accessibilityRole="summary" accessibilityLabel="Date of Birth Picker">
            {/* Modal Header */}
            <View style={styles.dobModalHeader}>
              <View>
                <Text style={styles.dobModalTitle}>Select Date of Birth</Text>
                <Text style={styles.dobModalSubtitle}>Parent or Legal Guardian Verification</Text>
              </View>
              <Pressable
                onPress={handleCancel}
                style={styles.dobModalCloseBtn}
                accessibilityRole="button"
                accessibilityLabel="Close picker"
                hitSlop={8}
              >
                <Feather name="x" size={20} color={colors.ink} />
              </Pressable>
            </View>

            {/* 18+ Constraint Banner */}
            <View style={styles.dobConstraintBanner}>
              <Feather name="shield" size={16} color="#0284C7" />
              <Text style={styles.dobConstraintText}>
                Adults only: You must be born on or before {MONTH_NAMES[today.getMonth()]} {today.getDate()}, {maxYear}.
              </Text>
            </View>

            {/* Selected Date Preview */}
            <View style={styles.dobPreviewBox}>
              <Text style={styles.dobPreviewLabel}>SELECTED DATE</Text>
              <Text style={styles.dobPreviewValue}>
                {MONTH_NAMES[tempMonth - 1]} {tempDay}, {tempYear}
              </Text>
            </View>

            {/* Year Stepper / Selector */}
            <View style={styles.dobPickerSection}>
              <Text style={styles.dobSectionTitle}>Year</Text>
              <View style={styles.dobStepperRow}>
                <Pressable
                  style={[styles.dobStepperBtn, tempYear <= minYear && styles.dobStepperBtnDisabled]}
                  onPress={() => setTempYear((y: number) => Math.max(minYear, y - 1))}
                  disabled={tempYear <= minYear}
                  accessibilityRole="button"
                  accessibilityLabel="Previous year"
                >
                  <Feather name="minus" size={18} color={tempYear <= minYear ? colors.muted : colors.ink} />
                </Pressable>
                <View style={styles.dobStepperValueBox}>
                  <Text style={styles.dobStepperValueText}>{tempYear}</Text>
                </View>
                <Pressable
                  style={[styles.dobStepperBtn, tempYear >= maxYear && styles.dobStepperBtnDisabled]}
                  onPress={() => setTempYear((y: number) => Math.min(maxYear, y + 1))}
                  disabled={tempYear >= maxYear}
                  accessibilityRole="button"
                  accessibilityLabel="Next year"
                >
                  <Feather name="plus" size={18} color={tempYear >= maxYear ? colors.muted : colors.ink} />
                </Pressable>
              </View>
            </View>

            {/* Month Grid */}
            <View style={styles.dobPickerSection}>
              <Text style={styles.dobSectionTitle}>Month</Text>
              <View style={styles.dobMonthGrid}>
                {MONTH_SHORT.map((mShort, idx) => {
                  const mNum = idx + 1;
                  const isSelected = tempMonth === mNum;
                  const isDisabled = tempYear === maxYear && mNum > maxMonth;
                  return (
                    <Pressable
                      key={mShort}
                      style={[
                        styles.dobMonthCell,
                        isSelected && styles.dobMonthCellSelected,
                        isDisabled && styles.dobMonthCellDisabled,
                      ]}
                      onPress={() => !isDisabled && setTempMonth(mNum)}
                      disabled={isDisabled}
                      accessibilityRole="button"
                      accessibilityLabel={MONTH_NAMES[idx]}
                      accessibilityState={{ selected: isSelected, disabled: isDisabled }}
                    >
                      <Text
                        style={[
                          styles.dobMonthCellText,
                          isSelected && styles.dobMonthCellTextSelected,
                          isDisabled && styles.dobMonthCellTextDisabled,
                        ]}
                      >
                        {mShort}
                      </Text>
                    </Pressable>
                  );
                })}
              </View>
            </View>

            {/* Day Selector */}
            <View style={styles.dobPickerSection}>
              <Text style={styles.dobSectionTitle}>Day</Text>
              <ScrollView
                horizontal
                showsHorizontalScrollIndicator={false}
                contentContainerStyle={styles.dobDayScrollContent}
              >
                {Array.from({ length: daysInCurrentMonth }, (_, i) => i + 1).map((dNum) => {
                  const isSelected = tempDay === dNum;
                  const isDisabled = tempYear === maxYear && tempMonth === maxMonth && dNum > maxDay;
                  return (
                    <Pressable
                      key={dNum}
                      style={[
                        styles.dobDayCell,
                        isSelected && styles.dobDayCellSelected,
                        isDisabled && styles.dobDayCellDisabled,
                      ]}
                      onPress={() => !isDisabled && setTempDay(dNum)}
                      disabled={isDisabled}
                      accessibilityRole="button"
                      accessibilityLabel={`Day ${dNum}`}
                      accessibilityState={{ selected: isSelected, disabled: isDisabled }}
                    >
                      <Text
                        style={[
                          styles.dobDayCellText,
                          isSelected && styles.dobDayCellTextSelected,
                          isDisabled && styles.dobDayCellTextDisabled,
                        ]}
                      >
                        {dNum}
                      </Text>
                    </Pressable>
                  );
                })}
              </ScrollView>
            </View>

            {/* Action Buttons */}
            <View style={styles.dobModalActionRow}>
              <Pressable
                style={styles.dobCancelButton}
                onPress={handleCancel}
                accessibilityRole="button"
                accessibilityLabel="Cancel date selection"
              >
                <Text style={styles.dobCancelButtonText}>Cancel</Text>
              </Pressable>
              <Pressable
                style={styles.dobConfirmButton}
                onPress={handleConfirm}
                accessibilityRole="button"
                accessibilityLabel="Confirm date of birth"
              >
                <Text style={styles.dobConfirmButtonText}>Set Date</Text>
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

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
            <ParentDobPicker
              value={dob}
              onChange={(canonical) => {
                setDob(canonical);
                clearFieldError('dob');
              }}
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
  // Six individual cells (auto-advance, backspace moves back, paste/autofill
  // distributes digits). The joined string is the submittable code.
  const [cells, setCells] = useState<string[]>(() => cellsFromCode(devCode));
  const otp = cells.join('');
  const [focusedCell, setFocusedCell] = useState(0);
  const cellRefs = useRef<Array<TextInput | null>>([]);
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

  function focusCell(index: number) {
    const clamped = Math.max(0, Math.min(OTP_LENGTH - 1, index));
    setFocusedCell(clamped);
    cellRefs.current[clamped]?.focus();
  }

  function handleCellChange(index: number, text: string) {
    const { cells: next, focus } = applyOtpInput(cells, index, text);
    setCells(next);
    if (focus !== index) focusCell(focus);
    else setFocusedCell(index);
  }

  function handleCellKeyPress(index: number, key: string) {
    // Backspace on an already-empty cell moves back and clears the previous
    // cell; backspace on a filled cell is handled by onChangeText.
    if (key === 'Backspace' && cells[index] === '' && index > 0) {
      const { cells: next, focus } = applyOtpBackspace(cells, index);
      setCells(next);
      focusCell(focus);
    }
  }

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
          setCells(cellsFromCode(response.dev_code));
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
              <View
                style={styles.otpRow}
                accessibilityLabel="6-digit verification code"
              >
                {cells.map((cell, index) => {
                  const active = focusedCell === index;
                  return (
                    <TextInput
                      key={index}
                      ref={(element) => {
                        cellRefs.current[index] = element;
                      }}
                      value={cell}
                      onChangeText={(text) => handleCellChange(index, text)}
                      onKeyPress={(event) => handleCellKeyPress(index, event.nativeEvent.key)}
                      onFocus={() => setFocusedCell(index)}
                      keyboardType="number-pad"
                      maxLength={OTP_LENGTH}
                      autoFocus={index === 0}
                      textAlign="center"
                      selectionColor={colors.brand}
                      cursorColor={colors.brand}
                      textContentType={index === 0 ? 'oneTimeCode' : 'none'}
                      autoComplete={index === 0 ? 'sms-otp' : 'off'}
                      returnKeyType={index === OTP_LENGTH - 1 ? 'done' : 'next'}
                      onSubmitEditing={index === OTP_LENGTH - 1 ? submit : () => focusCell(index + 1)}
                      accessibilityLabel={`Digit ${index + 1} of 6`}
                      style={[styles.otpCell, active && styles.otpCellActive]}
                    />
                  );
                })}
              </View>
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
  otpRow: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: 8,
    marginTop: 4,
  },
  otpCell: {
    width: 48,
    height: 58,
    fontSize: 24,
    fontWeight: '800',
    textAlign: 'center',
    backgroundColor: '#F9FAFB',
    borderColor: '#E5E7EB',
    borderWidth: 1.5,
    borderRadius: 12,
    color: colors.ink,
  },
  otpCellActive: {
    // Active cell: visible focus ring + centered caret so the entry point is
    // unmistakable. The caret renders centered because textAlign is center.
    borderColor: colors.brand,
    borderWidth: 2,
    backgroundColor: '#FFFFFF',
    shadowColor: colors.brand,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.25,
    shadowRadius: 6,
    elevation: 2,
  },
  otpHelperText: { fontSize: 11, color: colors.muted, textAlign: 'center', marginTop: 6 },
  dobWrapper: {
    marginBottom: spacing.md,
  },
  dobLabelRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 6,
  },
  dobLabel: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.ink,
  },
  dob18Badge: {
    backgroundColor: 'rgba(2, 132, 199, 0.1)',
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 6,
  },
  dob18BadgeText: {
    fontSize: 11,
    fontWeight: '700',
    color: '#0284C7',
  },
  dobTrigger: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: '#FFFFFF',
    borderWidth: 1.5,
    borderColor: '#E5E7EB',
    borderRadius: 12,
    paddingHorizontal: 14,
    height: 48,
  },
  dobTriggerError: {
    borderColor: '#DC2626',
  },
  dobTriggerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    flex: 1,
  },
  dobTriggerValue: {
    fontSize: 14,
    fontWeight: '600',
    color: colors.ink,
  },
  dobTriggerPlaceholder: {
    color: colors.muted,
    fontWeight: '400',
  },
  dobErrorText: {
    fontSize: 12,
    color: '#DC2626',
    marginTop: 4,
    fontWeight: '500',
  },
  dobHelperText: {
    fontSize: 12,
    color: colors.muted,
    marginTop: 4,
  },
  dobModalBackdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.55)',
    justifyContent: 'flex-end',
  },
  dobModalDismissArea: {
    flex: 1,
  },
  dobModalSheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    paddingHorizontal: 20,
    paddingTop: 20,
    paddingBottom: Platform.OS === 'ios' ? 36 : 24,
    maxHeight: '90%',
  },
  dobModalHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingBottom: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#E2E8F0',
  },
  dobModalTitle: {
    fontSize: 18,
    fontWeight: '800',
    color: colors.ink,
  },
  dobModalSubtitle: {
    fontSize: 12,
    fontWeight: '600',
    color: colors.muted,
    marginTop: 2,
  },
  dobModalCloseBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: '#F1F5F9',
    justifyContent: 'center',
    alignItems: 'center',
  },
  dobConstraintBanner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: '#F0F9FF',
    borderWidth: 1,
    borderColor: '#BAE6FD',
    borderRadius: 10,
    padding: 10,
    marginTop: 14,
  },
  dobConstraintText: {
    flex: 1,
    fontSize: 12,
    fontWeight: '600',
    color: '#0369A1',
    lineHeight: 16,
  },
  dobPreviewBox: {
    backgroundColor: '#F8FAFC',
    borderRadius: 12,
    paddingVertical: 10,
    paddingHorizontal: 16,
    alignItems: 'center',
    marginTop: 12,
  },
  dobPreviewLabel: {
    fontSize: 10,
    fontWeight: '800',
    color: colors.muted,
    letterSpacing: 0.8,
  },
  dobPreviewValue: {
    fontSize: 18,
    fontWeight: '800',
    color: colors.brand,
    marginTop: 2,
  },
  dobPickerSection: {
    marginTop: 14,
  },
  dobSectionTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: colors.ink,
    marginBottom: 8,
  },
  dobStepperRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 16,
  },
  dobStepperBtn: {
    width: 44,
    height: 44,
    borderRadius: 12,
    backgroundColor: '#F1F5F9',
    justifyContent: 'center',
    alignItems: 'center',
  },
  dobStepperBtnDisabled: {
    opacity: 0.35,
  },
  dobStepperValueBox: {
    paddingHorizontal: 24,
    paddingVertical: 8,
    borderRadius: 12,
    backgroundColor: '#F8FAFC',
    borderWidth: 1,
    borderColor: '#E2E8F0',
    minWidth: 110,
    alignItems: 'center',
  },
  dobStepperValueText: {
    fontSize: 22,
    fontWeight: '800',
    color: colors.ink,
  },
  dobMonthGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    justifyContent: 'space-between',
  },
  dobMonthCell: {
    width: '23%',
    paddingVertical: 8,
    borderRadius: 8,
    backgroundColor: '#F8FAFC',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#E2E8F0',
  },
  dobMonthCellSelected: {
    backgroundColor: colors.brand,
    borderColor: colors.brand,
  },
  dobMonthCellDisabled: {
    opacity: 0.3,
  },
  dobMonthCellText: {
    fontSize: 12,
    fontWeight: '700',
    color: colors.ink,
  },
  dobMonthCellTextSelected: {
    color: '#FFFFFF',
  },
  dobMonthCellTextDisabled: {
    color: colors.muted,
  },
  dobDayScrollContent: {
    flexDirection: 'row',
    gap: 8,
    paddingVertical: 4,
  },
  dobDayCell: {
    width: 42,
    height: 42,
    borderRadius: 12,
    backgroundColor: '#F8FAFC',
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#E2E8F0',
  },
  dobDayCellSelected: {
    backgroundColor: colors.brand,
    borderColor: colors.brand,
  },
  dobDayCellDisabled: {
    opacity: 0.3,
  },
  dobDayCellText: {
    fontSize: 14,
    fontWeight: '700',
    color: colors.ink,
  },
  dobDayCellTextSelected: {
    color: '#FFFFFF',
  },
  dobDayCellTextDisabled: {
    color: colors.muted,
  },
  dobModalActionRow: {
    flexDirection: 'row',
    gap: 12,
    marginTop: 20,
  },
  dobCancelButton: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: 12,
    backgroundColor: '#F1F5F9',
    alignItems: 'center',
    justifyContent: 'center',
  },
  dobCancelButtonText: {
    fontSize: 15,
    fontWeight: '700',
    color: colors.ink,
  },
  dobConfirmButton: {
    flex: 1.5,
    paddingVertical: 12,
    borderRadius: 12,
    backgroundColor: colors.brand,
    alignItems: 'center',
    justifyContent: 'center',
  },
  dobConfirmButtonText: {
    fontSize: 15,
    fontWeight: '700',
    color: '#FFFFFF',
  },
});