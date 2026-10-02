import * as SecureStore from 'expo-secure-store';
import type { StorageBackend } from './backends';

export type { StorageBackend } from './backends';
export { memoryBackend } from './backends';

export const secureStoreBackend: StorageBackend = {
  getItem: (key) => SecureStore.getItemAsync(key),
  setItem: (key, value) => SecureStore.setItemAsync(key, value).then(() => undefined),
  removeItem: (key) => SecureStore.deleteItemAsync(key).then(() => undefined),
};
