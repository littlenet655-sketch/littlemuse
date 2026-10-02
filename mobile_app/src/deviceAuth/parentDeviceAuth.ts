/**
 * React Native bridge for the native ParentDeviceAuth module (Android).
 *
 * Contract (mirrors the native module):
 *   checkParentDeviceAuth(): {
 *     biometricAvailable: boolean;
 *     biometricEnrolled: boolean;
 *     deviceCredentialAvailable: boolean;
 *     canAuthenticate: boolean;
 *   }
 *   authenticateParentDevice(): {
 *     success: boolean;
 *     method?: 'BIOMETRIC' | 'DEVICE_CREDENTIAL';
 *     error?: string;   // native Kotlin settles UPPERCASE codes:
 *                       // USER_CANCEL | NOT_ENROLLED | NO_ACTIVITY | LOCKOUT | FAILED
 *     message?: string;
 *   }
 *
 * The Kotlin module settles uppercase error codes; authenticateParentDevice
 * normalizes them onto the lowercase ParentAuthErrorCode union below so
 * consumers (e.g. parentAuthGate's 'user_cancel' check) match reliably.
 * This normalization is the only change: prompt semantics are untouched.
 *
 * Authentication stays entirely inside the Android system prompt. The app
 * never reads or stores the PIN / pattern / password / biometric template.
 */
import { NativeModules, Platform } from 'react-native';

export interface ParentDeviceAuthStatus {
  biometricAvailable: boolean;
  biometricEnrolled: boolean;
  deviceCredentialAvailable: boolean;
  canAuthenticate: boolean;
}

export type ParentAuthMethod = 'BIOMETRIC' | 'DEVICE_CREDENTIAL';

export type ParentAuthErrorCode =
  | 'user_cancel'
  | 'not_enrolled'
  | 'lockout'
  | 'failure'
  | 'unavailable'
  | 'in_progress';

export interface ParentDeviceAuthResult {
  success: boolean;
  method?: ParentAuthMethod;
  error?: ParentAuthErrorCode | string;
  message?: string;
}

interface NativeParentDeviceAuth {
  checkParentDeviceAuth(): Promise<ParentDeviceAuthStatus>;
  authenticateParentDevice(): Promise<ParentDeviceAuthResult>;
}

const nativeModule: NativeParentDeviceAuth | null =
  Platform.OS === 'android' && NativeModules.ParentDeviceAuth
    ? (NativeModules.ParentDeviceAuth as NativeParentDeviceAuth)
    : null;

const UNAVAILABLE: ParentDeviceAuthStatus = {
  biometricAvailable: false,
  biometricEnrolled: false,
  deviceCredentialAvailable: false,
  canAuthenticate: false,
};

export function isParentDeviceAuthNativeAvailable(): boolean {
  return nativeModule !== null;
}

export async function checkParentDeviceAuth(): Promise<ParentDeviceAuthStatus> {
  if (!nativeModule) return { ...UNAVAILABLE };
  try {
    const status = await nativeModule.checkParentDeviceAuth();
    return {
      biometricAvailable: !!status.biometricAvailable,
      biometricEnrolled: !!status.biometricEnrolled,
      deviceCredentialAvailable: !!status.deviceCredentialAvailable,
      canAuthenticate: !!status.canAuthenticate,
    };
  } catch {
    return { ...UNAVAILABLE };
  }
}

export async function authenticateParentDevice(): Promise<ParentDeviceAuthResult> {
  if (!nativeModule) {
    return {
      success: false,
      error: 'unavailable',
      message: 'Device authentication is not available on this device.',
    };
  }
  try {
    const result = await nativeModule.authenticateParentDevice();
    if (result && result.success) {
      return { success: true, method: result.method };
    }
    return {
      success: false,
      error: normalizeParentAuthError(result && result.error),
      message: result && result.message,
    };
  } catch (err) {
    return {
      success: false,
      error: 'failure',
      message: err instanceof Error ? err.message : 'Authentication failed.',
    };
  }
}

/**
 * Normalize a native error string onto the ParentAuthErrorCode union.
 * The Kotlin module settles uppercase codes ("USER_CANCEL", "NOT_ENROLLED",
 * "LOCKOUT", "FAILED", "NO_ACTIVITY"); consumers compare lowercase, so a
 * user-cancelled prompt previously surfaced as a generic failure.
 * Unknown/empty codes fall back to 'failure' — never to a success-shaped value.
 */
function normalizeParentAuthError(raw: unknown): ParentAuthErrorCode {
  const code = String(raw ?? '').toLowerCase();
  switch (code) {
    case 'user_cancel':
    case 'not_enrolled':
    case 'lockout':
    case 'in_progress':
    case 'unavailable':
      return code;
    case 'failed':
      return 'failure';
    default:
      return 'failure';
  }
}
