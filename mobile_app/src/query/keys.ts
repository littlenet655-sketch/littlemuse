/** Central query keys + fan-out invalidation (Agent C). */
import { queryClient } from './client';

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

export const parentKeys = {
  dashboard: ['parent', 'dashboard'],
  controls: (childId: number) => ['parent', 'controls', childId],
  safety: ['parent', 'safety'],
  follows: ['parent', 'follows'],
  activity: (childId: number) => ['parent', 'activity', childId],
  insights: (childId: number) => ['parent', 'insights', childId],
  notifications: ['parent', 'notifications'],
} as const;

export const adminKeys = {
  dashboard: ['admin', 'dashboard'],
  reviews: ['admin', 'reviews'],
  review: (eventId: number) => ['admin', 'review', eventId],
  users: (query: string) => ['admin', 'users', query],
  audit: ['admin', 'audit'],
} as const;

export async function invalidateSocialCaches(postIds: number[] = []): Promise<void> {
  await queryClient.invalidateQueries({ queryKey: ['kids', 'feed'] });
  await queryClient.invalidateQueries({ queryKey: ['kids', 'reels'] });
  await queryClient.invalidateQueries({ queryKey: ['kids', 'profile'] });
  await queryClient.invalidateQueries({ queryKey: ['kids', 'saved'] });
  for (const id of postIds) {
    await queryClient.invalidateQueries({ queryKey: kidsKeys.post(id) });
    await queryClient.invalidateQueries({ queryKey: kidsKeys.comments(id) });
  }
}
