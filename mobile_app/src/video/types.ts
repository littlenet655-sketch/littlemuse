export type PlaybackState =
  | 'IDLE'
  | 'PREPARING'
  | 'READY'
  | 'PLAYING'
  | 'PAUSED'
  | 'BUFFERING'
  | 'ENDED'
  | 'ERROR';

export type PlaybackPolicy = 'NORMAL' | 'DATA_SAVER';

export interface ReelMetrics {  source_type: 'SOCIAL' | 'CURATED';
  source_id: number;
  session_id?: string;
  surface: 'REELS' | 'FEED';
  watched_ms: number;
  completed: boolean;
  replay_count: number;
  liked?: boolean;
  saved?: boolean;
  ttff_ms?: number;
  rebuffer_count?: number;
  total_rebuffer_ms?: number;
  error_type?: string | null;
  credential_refreshes?: number;
}

export interface ImpressionEventPayload {
  session_id?: string;
  source_type: string;
  source_id: number;
  surface: string;
  watched_ms?: number;
  completed?: boolean;
  liked?: boolean;
  saved?: boolean;
  replay_count?: number;
}

/**
 * Full playback payload returned by
 * GET /api/mobile/v2/kids/reels/<post_id>/playback (and the curated variant).
 *
 * The server resolves the delivery provider internally: when Cloudflare Stream
 * is configured and the asset is READY it returns an HLS manifest URL with a
 * real provider UID (`playback_id`); otherwise it falls back to a signed
 * private-R2 MP4. The client must treat this payload as opaque and never
 * assume one provider — Stream is enabled server-side only.
 */
export interface ReelPlaybackResponse {
  ok: boolean;
  /** Real provider asset UID (Cloudflare Stream) or synthetic R2 playback id. */
  playback_id?: string | null;
  /** "CLOUDFLARE_STREAM" | "R2_SANITIZED_MP4" — server-chosen provider. */
  provider?: string | null;
  /** "HLS" for Stream, "MP4" for the R2 fallback. */
  delivery_type?: string | null;
  playback_url?: string | null;
  /** Unix seconds when the signed playback credential expires. */
  playback_expires_at?: number | null;
  poster_url?: string | null;
  duration_ms?: number | null;
  width?: number | null;
  height?: number | null;
  /** Server-tagged ratio like "9:16" (may be absent). */
  aspect_ratio?: string | null;
  /** "DIRECT_SIGNED" | "DENIED" | R2 delivery mode. */
  delivery_mode?: string | null;
  error?: string | null;
}

export type DeliveryKind = 'HLS' | 'MP4' | 'UNKNOWN';

/**
 * Classify the concrete delivery behind a playback payload. Pure function so
 * playback decisions stay testable and never hard-code a provider.
 */
export function deliveryKindOf(input: {
  delivery_type?: string | null;
  playback_url?: string | null;
}): DeliveryKind {
  const declared = (input.delivery_type ?? '').toUpperCase();
  if (declared === 'HLS') return 'HLS';
  if (declared === 'MP4') return 'MP4';
  const url = (input.playback_url ?? '').toLowerCase();
  if (url.includes('.m3u8')) return 'HLS';
  if (/\.(mp4|mov|webm|mkv)(\?|#|$)/.test(url)) return 'MP4';
  return 'UNKNOWN';
}

/** Clamp for feed media aspect ratios: portrait 9:16 .. landscape 16:9. */
export const MIN_FEED_ASPECT = 9 / 16;
export const MAX_FEED_ASPECT = 16 / 9;

/**
 * Parse a server "W:H" aspect tag into a numeric width/height ratio.
 * Returns null for missing/malformed tags — callers fall back to measuring.
 */
export function parseAspectRatio(value?: string | null): number | null {
  if (!value || typeof value !== 'string') return null;
  const match = value.trim().match(/^(\d+(?:\.\d+)?)\s*[:/x]\s*(\d+(?:\.\d+)?)$/);
  if (!match) return null;
  const w = Number(match[1]);
  const h = Number(match[2]);
  if (!Number.isFinite(w) || !Number.isFinite(h) || w <= 0 || h <= 0) return null;
  return w / h;
}

/** Clamp an aspect ratio into a sane display range (guards against 0/NaN). */
export function clampAspectRatio(ratio: number, min: number = MIN_FEED_ASPECT, max: number = MAX_FEED_ASPECT): number {
  if (!Number.isFinite(ratio) || ratio <= 0) return 1;
  return Math.min(max, Math.max(min, ratio));
}
