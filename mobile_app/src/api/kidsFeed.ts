/** Kids feed/discover API (Agent C). Maps to mobile/api.py v2 routes. */
import { apiRequest, routes } from './client';

export interface FeedItem {
  source_type: 'SOCIAL' | 'CURATED';
  source_id: number;
  post_id: number;
  /** Session that authorized this exact item; required across refill sessions. */
  feed_session_id?: string;
  full_name?: string;
  creator_key?: string;
  creator_username?: string;
  avatar_url?: string | null;
  media_type?: string;
  media_url?: string | null;
  poster_url?: string | null;
  playback_expires_at?: number | null;
  playback_ready?: boolean;
  delivery_type?: 'JIT' | 'MP4' | 'HLS' | string;
  duration_ms?: number;
  aspect_ratio?: string;
  title?: string;
  caption?: string;
  content_category?: string;
  likes?: number;
  comments_count?: number;
  comments_enabled?: boolean;
  created_at?: string;
  child_id?: number;
  is_reel?: boolean;
  moderation_status?: string;
  is_safe?: boolean;
  viewer_liked?: boolean;
  viewer_saved?: boolean;
}

export interface StoryItem {
  post_id: number;
  full_name?: string;
  avatar_url?: string | null;
  media_type?: string;
  media_url?: string | null;
  poster_url?: string | null;
  caption?: string;
}

export interface FeedPage {
  ok: boolean;
  items: FeedItem[];
  next_cursor: number | null;
  has_more: boolean;
  can_refill?: boolean;
  exhaustion_reason?: 'SESSION_END' | 'NO_ELIGIBLE_CONTENT' | string | null;
  total_in_session?: number;
  session_id: string;
}

async function get<T>(path: string, token: string, signal?: AbortSignal): Promise<T> {
  return apiRequest<T>(path, signal ? { signal } : {}, token);
}

export function fetchFeedV2(
  token: string,
  cursor: number,
  limit = 10,
  sessionId?: string,
  modeOrSignal?: 'for_you' | 'friends' | 'learn' | AbortSignal,
  signal?: AbortSignal,
  refillFrom?: string,
): Promise<FeedPage> {
  let mode: 'for_you' | 'friends' | 'learn' = 'for_you';
  let activeSignal = signal;
  if (typeof modeOrSignal === 'string') {
    mode = modeOrSignal;
  } else if (modeOrSignal && typeof modeOrSignal === 'object' && 'aborted' in modeOrSignal) {
    activeSignal = modeOrSignal as AbortSignal;
  }
  const p = new URLSearchParams({ cursor: String(cursor), limit: String(limit), mode });
  if (sessionId) p.set('session_id', sessionId);
  if (refillFrom) p.set('refill_from', refillFrom);
  return get<FeedPage>(`${routes.feedV2}?${p.toString()}`, token, activeSignal);
}

export function fetchReelsV2(
  token: string,
  cursor: number,
  limit = 10,
  sessionId?: string,
  signal?: AbortSignal,
  refillFrom?: string,
): Promise<FeedPage> {
  const p = new URLSearchParams({ cursor: String(cursor), limit: String(limit) });
  if (sessionId) p.set('session_id', sessionId);
  if (refillFrom) p.set('refill_from', refillFrom);
  return apiRequest<FeedPage>(`${routes.reelsV2}?${p.toString()}`, {
    signal,
    timeoutMs: 30_000,
  }, token);
}

export function refreshReelPlayback(
  token: string,
  postId: number,
): Promise<{ ok: boolean; playback_url?: string; playback_expires_at?: number; poster_url?: string }> {
  return get(routes.reelPlayback(postId), token);
}

export function refreshCuratedReelPlayback(
  token: string,
  contentId: number,
): Promise<{ ok: boolean; playback_url?: string; playback_expires_at?: number; poster_url?: string }> {
  return get(routes.curatedReelPlayback(contentId), token);
}

export function recordStoryView(
  token: string,
  storyId: number,
  completionRatio = 1.0,
): Promise<{ ok: boolean; viewer_count?: number }> {
  return apiRequest(routes.storyView(storyId), {
    method: 'POST',
    body: JSON.stringify({ completion_ratio: completionRatio }),
  }, token);
}

export function recordFeedImpression(
  token: string,
  params: {
    session_id?: string;
    source_type: string;
    source_id: number;
    surface?: string;
    watched_ms?: number;
    completed?: boolean;
    liked?: boolean;
    saved?: boolean;
    replay_count?: number;
  },
): Promise<{ ok: boolean; quiz_required?: boolean; posts_seen?: number; quiz_interval?: number }> {
  return apiRequest(routes.impressions, {
    method: 'POST',
    body: JSON.stringify(params),
  }, token);
}

export function fetchKidsHome(token: string): Promise<{ ok: boolean; stories: StoryItem[]; controls?: { allowed_categories?: string[]; educational_only_feed?: boolean } }> {
  return get(routes.kidsHome, token);
}

export interface HeartbeatResult {
  ok: boolean;
  minutes_today: number;
  remaining_minutes: number | null;
  daily_limit_minutes?: number;
  strict_mode?: boolean;
  quiet_hours?: { enabled: boolean; active: boolean; start: string; end: string };
  server_time?: string;
  locked?: boolean;
  self_resets_used?: number;
  self_resets_remaining?: number;
}

export interface KidTimeLimitStatus {
  ok: boolean;
  locked: boolean;
  minutes_today: number;
  daily_limit_minutes: number;
  strict_mode: boolean;
  remaining_minutes: number | null;
  resets_used: number;
  resets_remaining: number;
}

export function sendHeartbeat(token: string, signal?: AbortSignal): Promise<HeartbeatResult> {
  return apiRequest<HeartbeatResult>(
    routes.heartbeatV2,
    { method: 'POST', signal },
    token,
  );
}

export function fetchKidsTimeLimitStatus(token: string): Promise<KidTimeLimitStatus> {
  return get<KidTimeLimitStatus>(routes.kidsTimeLimitStatus, token);
}

export function resetKidsTimeLimitSelf(token: string): Promise<{
  ok: boolean;
  message: string;
  resets_used: number;
  resets_remaining: number;
  minutes_today: number;
}> {
  return apiRequest(routes.kidsTimeLimitReset, { method: 'POST' }, token);
}

export function recordImpressionBatch(
  token: string,
  events: Array<{
    session_id?: string;
    source_type: string;
    source_id: number;
    surface: string;
    watched_ms?: number;
    completed?: boolean;
    liked?: boolean;
    saved?: boolean;
    replay_count?: number;
  }>,
): Promise<{ ok: boolean; processed: number; recorded?: number; quiz_required?: boolean; posts_seen?: number; quiz_interval?: number; next_quiz_threshold?: number }> {
  return apiRequest<{ ok: boolean; processed: number; recorded?: number; quiz_required?: boolean; posts_seen?: number; quiz_interval?: number; next_quiz_threshold?: number }>(
    routes.impressionsBatch,
    {
      method: 'POST',
      body: JSON.stringify({ events }),
    },
    token,
  );
}

