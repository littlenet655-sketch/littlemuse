import { useRef, useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView } from 'react-native';
import { requestPasswordReset, resetPassword } from '../api/auth';
import { validateResetInput } from '../auth/resetValidation';
import type { AuthScreenProps } from '../navigation/types';
import { BrandHeader, Button, Card, Field, Notice, Screen, errorText } from '../ui/components';

/** Step 1: identifier -> existing forgot-password endpoint -> reset-code screen. */
export function ForgotPasswordScreen({ navigation }: AuthScreenProps<'ForgotPassword'>) {
  const [identifier, setIdentifier] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');
  /**
   * Synchronous double-tap guard: the `busy` render state does not stop a
   * rapid second tap dispatched before re-render. This ref check-and-sets
   * synchronously at the top of submit().
   */
  const submitBusyRef = useRef(false);

  async function submit() {
    if (submitBusyRef.current) return;
    submitBusyRef.current = true;
    try {
      if (!identifier.trim()) {
        setError('Enter your username or email.');
        return;
      }
      setBusy(true);
      setError('');
      setInfo('');
      try {
        const response = await requestPasswordReset(identifier.trim());
        if (!response.ok) {
          setError(response.message || 'Could not send a reset code. Try again.');
          return;
        }
        if (typeof response.user_id !== 'number' || !response.masked_email) {
          // Anti-enumeration uniform response: the server does not say
          // whether an account matched. Show the message and stay here.
          setInfo(response.message || 'If an account exists, a reset code was sent.');
          return;
        }
        navigation.navigate('ResetPassword', {
          userId: response.user_id,
          maskedEmail: response.masked_email,
          message: response.is_parent_proxy
            ? 'For safety, the code was sent to your verified parent email.'
            : response.message,
        });
      } catch (err) {
        setError(errorText(err));
      } finally {
        setBusy(false);
      }
    } finally {
      submitBusyRef.current = false;
    }
  }

  return (
    <Screen>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 64 : 30}
        style={{ flex: 1 }}
      >
        <ScrollView keyboardShouldPersistTaps="handled">
          <BrandHeader title="Reset password" subtitle="Enter your username or email and we will send a 6-digit code (15 minutes)." />
          <Card>
            <Field label="Username or email" autoCapitalize="none" autoCorrect={false} keyboardType="email-address" value={identifier} onChangeText={setIdentifier} />
            {error ? <Notice message={error} /> : null}
            {info ? <Notice tone="info" message={info} /> : null}
            <Button label={busy ? 'Sending…' : 'Send reset code'} onPress={submit} loading={busy} disabled={busy} />
          </Card>
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}

/** Step 2: code + new password -> existing reset-password endpoint -> Login. */
export function ResetPasswordScreen({ navigation, route }: AuthScreenProps<'ResetPassword'>) {
  const { userId, maskedEmail, message } = route.params;
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState('');
  /**
   * Synchronous double-tap guard: the `busy` render state does not stop a
   * rapid second tap dispatched before re-render. This ref check-and-sets
   * synchronously at the top of submit().
   */
  const submitBusyRef = useRef(false);

  async function submit() {
    if (submitBusyRef.current) return;
    submitBusyRef.current = true;
    try {
      const problem = validateResetInput(code, password, confirm);
      if (problem) {
        setError(problem);
        return;
      }
      setBusy(true);
      setError('');
      try {
        const response = await resetPassword(userId, code.trim(), password);
        if (!response.ok) {
          setError(response.message || 'Could not reset your password. Try again.');
          return;
        }
        setDone(response.message);
      } catch (err) {
        setError(errorText(err));
      } finally {
        setBusy(false);
      }
    } finally {
      submitBusyRef.current = false;
    }
  }

  return (
    <Screen>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 64 : 30}
        style={{ flex: 1 }}
      >
        <ScrollView keyboardShouldPersistTaps="handled">
          <BrandHeader title="New password" subtitle={`Code sent to ${maskedEmail}.`} />
          <Card>
            {message ? <Notice tone="info" message={message} /> : null}
            <Field label="6-digit code" keyboardType="number-pad" maxLength={6} value={code} onChangeText={setCode} />
            <Field label="New password (min 8)" secureTextEntry value={password} onChangeText={setPassword} />
            <Field label="Confirm new password" secureTextEntry value={confirm} onChangeText={setConfirm} />
            {error ? <Notice message={error} /> : null}
            {done ? <Notice tone="ok" message={done} /> : null}
            {done ? (
              <Button label="Back to login" onPress={() => navigation.navigate('Login')} />
            ) : (
              <Button label={busy ? 'Resetting…' : 'Reset password'} onPress={submit} loading={busy} disabled={busy} />
            )}
          </Card>
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}
