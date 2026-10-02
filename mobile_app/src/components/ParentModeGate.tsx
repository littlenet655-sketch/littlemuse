/**
 * Parent Mode entry gate.
 *
 * Wraps the Parent navigator. On mount (and when returning to the
 * foreground) it requires a fresh parent authorization via the Android
 * system authentication (strong biometric or device PIN/pattern/password).
 *
 * A successful authentication opens an in-memory authorization window
 * (~5 minutes, see parentAuthGate). Nothing is ever persisted to storage:
 * there is no `parentUnlocked` flag anywhere on disk. Backgrounding,
 * logout, session changes, and timeout invalidate the window.
 *
 * Also exports ensureParentAuthForAction(), the shared helper used to gate
 * individual sensitive parent mutations (child creation, screen-time
 * changes, safety controls, follow approvals, password resets,
 * unlink, security settings). When the window is still valid it resolves
 * immediately without re-prompting.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import {
  ActivityIndicator,
  Alert,
  AppState,
  Linking,
  Platform,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import {
  installParentGateInvalidation,
  isParentAuthorized,
  requireParentAuth,
} from '../deviceAuth/parentAuthGate';
import { Button, Screen } from '../ui/components';
import { colors, spacing } from '../ui/tokens';

export const NO_LOCK_MESSAGE = 'Set up a screen lock on this phone to use Parent Mode.';

type GatePhase = 'checking' | 'blocked' | 'denied' | 'granted';

/**
 * Ensure a fresh parent authorization before running a sensitive action.
 * Returns true when the caller may proceed; shows the appropriate
 * guidance/alert and returns false when the action must be aborted.
 */
export async function ensureParentAuthForAction(): Promise<boolean> {
  const outcome = await requireParentAuth();
  if (outcome.ok) return true;
  if (outcome.reason === 'cancelled') {
    Alert.alert('Authentication cancelled', 'The action was not performed.');
  } else if (outcome.reason === 'no_credential') {
    Alert.alert('Screen lock required', NO_LOCK_MESSAGE);
  } else {
    Alert.alert(
      'Authentication failed',
      outcome.message ?? 'Could not verify it is you. Please try again.',
    );
  }
  return false;
}

export function ParentModeGate({ children }: { children: ReactNode }) {
  const [phase, setPhase] = useState<GatePhase>(isParentAuthorized() ? 'granted' : 'checking');
  const [deniedMessage, setDeniedMessage] = useState('');
  const mounted = useRef(true);

  const runAuth = useCallback(async () => {
    setPhase('checking');
    const outcome = await requireParentAuth();
    if (!mounted.current) return;
    if (outcome.ok) {
      setPhase('granted');
      return;
    }
    if (outcome.reason === 'no_credential') {
      setPhase('blocked');
      return;
    }
    setDeniedMessage(
      outcome.reason === 'cancelled'
        ? 'Authentication was cancelled. Parent Mode needs a quick identity check.'
        : outcome.message ?? 'Could not verify it is you. Please try again.',
    );
    setPhase('denied');
  }, []);

  useEffect(() => {
    mounted.current = true;
    // installParentGateInvalidation returns an AppState-subscription cleanup;
    // the old code discarded it, leaking one subscription per mount.
    const uninstallGateInvalidation = installParentGateInvalidation();
    void runAuth();
    const sub = AppState.addEventListener('change', (next) => {
      // Re-check when returning to the foreground: backgrounding
      // invalidated the window, so entry must re-authenticate.
      if (next === 'active') void runAuth();
    });
    return () => {
      mounted.current = false;
      sub.remove();
      uninstallGateInvalidation();
    };
  }, [runAuth]);

  if (phase === 'granted') {
    return <>{children}</>;
  }

  if (phase === 'checking') {
    return (
      <Screen hasNativeHeader={false}>
        <View style={styles.center}>
          <ActivityIndicator size="large" color={colors.brand} />
          <Text style={styles.statusText}>Verifying it&apos;s you…</Text>
        </View>
      </Screen>
    );
  }

  if (phase === 'blocked') {
    return (
      <Screen hasNativeHeader={false}>
        <View style={styles.center}>
          <Text style={styles.blockTitle}>Screen lock required</Text>
          <Text style={styles.blockBody}>{NO_LOCK_MESSAGE}</Text>
          {Platform.OS === 'android' ? (
            <View style={styles.buttonWrap}>
              <Button
                label="Open security settings"
                onPress={() => {
                  Linking.openSettings().catch(() => {});
                }}
              />
            </View>
          ) : null}
          <View style={styles.buttonWrap}>
            <Button label="Check again" variant="secondary" onPress={() => void runAuth()} />
          </View>
        </View>
      </Screen>
    );
  }

  return (
    <Screen hasNativeHeader={false}>
      <View style={styles.center}>
        <Text style={styles.blockTitle}>Identity check needed</Text>
        <Text style={styles.blockBody}>{deniedMessage}</Text>
        <View style={styles.buttonWrap}>
          <Button label="Try again" onPress={() => void runAuth()} />
        </View>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  center: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.lg,
  },
  statusText: {
    marginTop: spacing.md,
    fontSize: 15,
    color: colors.muted,
  },
  blockTitle: {
    fontSize: 20,
    fontWeight: '800',
    color: colors.ink,
    marginBottom: spacing.sm,
    textAlign: 'center',
  },
  blockBody: {
    fontSize: 15,
    color: colors.muted,
    textAlign: 'center',
    lineHeight: 22,
    marginBottom: spacing.lg,
  },
  buttonWrap: {
    width: '100%',
    marginTop: spacing.sm,
  },
});
