/** Kids profiles/discover API (Agent C). */
import { apiRequest, routes } from './client';
import type { PostDetail } from './kidsSocial';

export interface KidSummary {
  user_id: number;
  username?: string;
  full_name?: string;
  avatar_url?: string | null;
  is_following?: boolean;
  is_pending?: boolean;
}

export interface ProfilePayload {
  ok: boolean;
  profile: Record<string, unknown>;
  counts: Record<string, unknown>;
  posts: PostDetail[];
  relationship?: { connected: boolean; pending: boolean; can_message: boolean };
  interests?: string[];
}

async function get<T>(path: string, token: string, signal?: AbortSignal): Promise<T> {
  return apiRequest<T>(path, signal ? { signal } : {}, token);
}

export interface CuratedSearchItem {
  source_id: number;
  title?: string;
  caption?: string;
  media_type?: string;
  media_url?: string | null;
  poster_url?: string | null;
  content_category?: string;
}

export function searchDiscover(token: string, q: string, signal?: AbortSignal): Promise<{
  ok: boolean;
  pii_warning: boolean;
  children: KidSummary[];
  posts: PostDetail[];
  curated?: CuratedSearchItem[];
  hashtags?: unknown[];
}> {
  return get(`${routes.discoverV2}${q ? `?q=${encodeURIComponent(q)}` : ''}`, token, signal);
}

export function fetchOwnProfile(token: string): Promise<ProfilePayload> {
  return get(routes.ownProfile, token);
}

export function updateOwnProfile(token: string, patch: Record<string, unknown>): Promise<ProfilePayload> {
  return apiRequest<ProfilePayload>(routes.ownProfile, { method: 'PUT', body: JSON.stringify(patch) }, token);
}

export function fetchOtherProfile(token: string, targetId: number): Promise<ProfilePayload> {
  return get(routes.otherProfile(targetId), token);
}
