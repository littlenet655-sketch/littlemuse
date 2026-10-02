import { Platform } from 'react-native';
import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import Constants from 'expo-constants';

import { apiRequest, routes } from '../api/client';

const PUSH_TOKEN_STORAGE_KEY = 'littlenet_push_token';
const DEVICE_ID_STORAGE_KEY = 'littlenet_device_id';

function randomDeviceId(): string {
  return `dev_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
}

async function getStoredDeviceId(): Promise<string> {
  try {
    const { default: AsyncStorage } = await import('@react-native-async-storage/async-storage');
    const existing = await AsyncStorage.getItem(DEVICE_ID_STORAGE_KEY);
    if (existing) return existing;
    const fresh = randomDeviceId();
    await AsyncStorage.setItem(DEVICE_ID_STORAGE_KEY, fresh);
    return fresh;
  } catch {
    return randomDeviceId();
  }
}

export async function registerPushToken(authToken: string): Promise<string | null> {
  try {
    if (!Device.isDevice) return null;
    const { status: existing } = await Notifications.getPermissionsAsync();
    let status = existing;
    if (status !== 'granted') {
      const req = await Notifications.requestPermissionsAsync();
      status = req.status;
    }
    if (status !== 'granted') return null;

    const projectId =
      Constants?.expoConfig?.extra?.eas?.projectId ?? Constants?.easConfig?.projectId;
    const expoPushToken = await Notifications.getExpoPushTokenAsync(
      projectId ? { projectId } : undefined,
    );

    const deviceId = await getStoredDeviceId();
    const token = expoPushToken.data;
    await apiRequest(
      routes.deviceRegister,
      {
        method: 'POST',
        body: JSON.stringify({
          push_token: token,
          platform: Platform.OS,
          device_identifier: deviceId,
        }),
      },
      authToken,
    );
    try {
      const { default: AsyncStorage } = await import('@react-native-async-storage/async-storage');
      await AsyncStorage.setItem(PUSH_TOKEN_STORAGE_KEY, token);
    } catch {
      // storage is best-effort; registration already succeeded server-side
    }
    return token;
  } catch {
    // Push registration must never break login/session flows.
    return null;
  }
}

export async function unregisterPushToken(authToken: string): Promise<void> {
  try {
    const { default: AsyncStorage } = await import('@react-native-async-storage/async-storage');
    const token = await AsyncStorage.getItem(PUSH_TOKEN_STORAGE_KEY);
    if (!token) return;
    await apiRequest(
      routes.deviceUnregister,
      { method: 'POST', body: JSON.stringify({ push_token: token }) },
      authToken,
    );
    await AsyncStorage.removeItem(PUSH_TOKEN_STORAGE_KEY);
  } catch {
    // best-effort; server-side revocation happens on token expiry too
  }
}
