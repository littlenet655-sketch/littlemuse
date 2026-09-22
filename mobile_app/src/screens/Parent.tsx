import { useEffect, useRef, useState } from 'react';
import { Keyboard, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useQueryClient } from '@tanstack/react-query';
import { Feather } from '@expo/vector-icons';
import { createChild } from '../api/auth';
import { useAuth } from '../auth/AuthProvider';
import { ensureParentAuthForAction } from '../components/ParentModeGate';
import type { ParentScreenProps } from '../navigation/types';
import { parentKeys } from '../query/keys';
import { Button, Card, Field, Notice, Screen, errorText } from '../ui/components';
import { colors, radius, spacing, type } from '../ui/tokens';

export function CreateChildScreen({ navigation }: ParentScreenProps<'CreateChild'>) {
  const { session } = useAuth();
  const queryClient = useQueryClient();
  const [username, setUsername] = useState('');
  const [fullName, setFullName] = useState('');
  const [age, setAge] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
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

  const scrollToInput = (offsetY: number) => {
    setTimeout(() => {
      scrollRef.current?.scrollTo({ y: offsetY, animated: true });
    }, 120);
  };

  async function submit() {
    const problems: Record<string, string> = {};
    if (username.trim().length < 3) problems.username = 'Pick at least 3 characters.';
    if (!fullName.trim()) problems.fullName = 'Enter the child\u2019s name.';
    const ageNumber = Number(age);
    if (!Number.isInteger(ageNumber) || ageNumber < 6 || ageNumber > 16) problems.age = 'Age must be 6–16.';
    if (password.length < 8) problems.password = 'At least 8 characters.';
    if (Object.keys(problems).length) {
      setFieldErrors(problems);
      return;
    }
    setFieldErrors({});
    if (!session) return;
    // Sensitive action: require a fresh parent device authentication.
    if (!(await ensureParentAuthForAction())) return;
    setBusy(true);
    setError('');
    try {
      await createChild(session.token, {
        username: username.trim(),
        full_name: fullName.trim(),
        age: ageNumber,
        password,
      });
      await queryClient.invalidateQueries({ queryKey: parentKeys.dashboard });
      navigation.goBack();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 88 : 0}
        style={styles.keyboardContainer}
      >
        <ScrollView
          ref={scrollRef}
          style={{ flex: 1 }}
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
            <View style={styles.iconBadge}>
              <Feather name="user-plus" size={26} color={colors.brand} />
            </View>
            <Text style={styles.headerTitle}>Add a Child Account</Text>
            <Text style={styles.headerSubtitle}>
              Create your child's profile. Next: face key setup and age-tailored safety quiz.
            </Text>
          </View>

          <Card>
            <Field
              label="Child Username"
              placeholder="e.g. alex_star"
              autoCapitalize="none"
              autoCorrect={false}
              helper="3–30 letters, numbers, _ or ."
              value={username}
              onChangeText={setUsername}
              onFocus={() => scrollToInput(20)}
              error={fieldErrors.username}
            />
            <Field
              label="Child Full Name"
              placeholder="e.g. Alex Kumar"
              value={fullName}
              onChangeText={setFullName}
              onFocus={() => scrollToInput(80)}
              error={fieldErrors.fullName}
            />
            <Field
              label="Child Age (6–16)"
              placeholder="e.g. 10"
              keyboardType="number-pad"
              value={age}
              onChangeText={setAge}
              onFocus={() => scrollToInput(140)}
              error={fieldErrors.age}
            />
            <Field
              label="Initial Password"
              placeholder="Minimum 8 characters"
              secureTextEntry={!showPassword}
              value={password}
              onChangeText={setPassword}
              onFocus={() => scrollToInput(210)}
              error={fieldErrors.password}
              rightAction={
                <Pressable onPress={() => setShowPassword((prev) => !prev)} hitSlop={8}>
                  <Text style={styles.pwdToggle}>{showPassword ? 'Hide' : 'Show'}</Text>
                </Pressable>
              }
            />

            <View style={styles.infoBanner}>
              <Feather name="shield" size={18} color="#0284C7" style={styles.infoIcon} />
              <Text style={styles.infoText}>
                The child will log in using this username and password, enroll their face key for biometric protection, and take the welcome safety quiz.
              </Text>
            </View>

            {error ? <Notice message={error} /> : null}

            <Button
              label={busy ? 'Creating Child Profile…' : 'Add Child →'}
              onPress={submit}
              loading={busy}
              disabled={busy}
            />
          </Card>
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  keyboardContainer: { flex: 1 },
  scrollContent: { flexGrow: 1, paddingBottom: 280 },
  headerHero: {
    alignItems: 'center',
    paddingTop: spacing.lg,
    paddingBottom: spacing.sm,
    paddingHorizontal: spacing.lg,
  },
  iconBadge: {
    width: 56,
    height: 56,
    borderRadius: 16,
    backgroundColor: '#EFF6FF',
    borderWidth: 1.5,
    borderColor: '#BFDBFE',
    alignItems: 'center',
    justifyContent: 'center',
    shadowColor: '#0095F6',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.15,
    shadowRadius: 8,
    elevation: 3,
    marginBottom: spacing.xs,
  },
  iconEmoji: { fontSize: 26 },
  headerTitle: {
    color: colors.ink,
    fontSize: 22,
    fontWeight: '900',
    letterSpacing: -0.4,
    marginTop: 4,
  },
  headerSubtitle: {
    color: colors.muted,
    fontSize: 13,
    textAlign: 'center',
    marginTop: 4,
    lineHeight: 18,
    maxWidth: 300,
  },
  pwdToggle: { fontSize: 12, fontWeight: '700', color: colors.brand },
  infoBanner: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
    backgroundColor: '#F0F9FF',
    borderWidth: 1,
    borderColor: '#BAE6FD',
    borderRadius: 12,
    padding: 10,
    marginTop: spacing.md,
  },
  infoIcon: { fontSize: 14, marginTop: 1 },
  infoText: {
    flex: 1,
    fontSize: 12,
    color: '#0369A1',
    lineHeight: 17,
    fontWeight: '500',
  },
});

