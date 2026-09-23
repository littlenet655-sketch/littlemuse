import { useEffect, useState } from 'react';
import { QueryClient, QueryClientProvider, focusManager, onlineManager } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { AppState } from 'react-native';
import NetInfo from '@react-native-community/netinfo';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // No aggressive polling: screens opt into bounded refetch explicitly.
      retry: 1,
      staleTime: 120_000,
      gcTime: 5 * 60_000,
      refetchOnWindowFocus: false,
      refetchOnReconnect: true,
    },
    mutations: {
      retry: 0,
    },
  },
});

function wireFocusAndOnline(): () => void {
  onlineManager.setEventListener((setOnline) =>
    NetInfo.addEventListener((state) => {
      setOnline(state.isConnected ?? true);
    }),
  );
  const subscription = AppState.addEventListener('change', (state) => {
    focusManager.setFocused(state === 'active');
  });
  return () => subscription.remove();
}

export function QueryProvider({ children }: { children: ReactNode }) {
  useEffect(wireFocusAndOnline, []);
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

/** Foreground-only flag: polling/background refresh must suspend when not foregrounded. */
export function useIsForeground(): boolean {
  const [foreground, setForeground] = useState(AppState.currentState === 'active');
  useEffect(() => {
    const subscription = AppState.addEventListener('change', (state) => {
      setForeground(state === 'active');
    });
    return () => subscription.remove();
  }, []);
  return foreground;
}

/** Connectivity flag for offline banners and disabled states. */
export function useIsOnline(): boolean {
  const [online, setOnline] = useState(true);
  useEffect(() => NetInfo.addEventListener((state) => setOnline(state.isConnected ?? true)), []);
  return online;
}

/** Invalidate everything touching the signed-in user (used on logout/role change). */
export async function invalidateSessionQueries(): Promise<void> {
  await queryClient.invalidateQueries();
  queryClient.clear();
}

/** Central query keys for the Kids product (Agent C). */
export const kidsKeys = {
  me: ['me'],
  home: ['kids', 'home'],
  feed: ['kids', 'feed'],
  reels: ['kids', 'reels'],
  discover: (q: string) => ['kids', 'discover', q],
  ownProfile: ['kids', 'profile', 'me'],
  profile: (id: number) => ['kids', 'profile', id],
  post: (id: number) => ['kids', 'post', id],
  comments: (id: number) => ['kids', 'comments', id],
  saved: ['kids', 'saved'],
  connections: ['kids', 'connections'],
  notifications: ['kids', 'notifications'],
  conversations: ['kids', 'conversations'],
  chat: (peerId: number) => ['kids', 'chat', peerId],
  processing: (postId: number) => ['kids', 'processing', postId],
} as const;
