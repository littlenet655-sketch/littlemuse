/** Kids v2 upload pipeline API (Agent C). Direct R2 PUT, never JSON media. */
import { apiRequest, routes } from './client';

const UPLOAD_CONTROL_TIMEOUT_MS = 60_000;

async function postJson<T>(path: string, body: Record<string, unknown>, token: string): Promise<T> {
  return apiRequest<T>(path, {
    method: 'POST',
    body: JSON.stringify(body),
    // Modal cold starts plus auth/parent-control/R2 checks can legitimately
    // exceed the general 15-second UI request budget.
    timeoutMs: UPLOAD_CONTROL_TIMEOUT_MS,
  }, token);
}

export interface UploadSession {
  ok: boolean;
  upload_id: string;
  upload_url: string;
  object_key: string;
  expires_at: string;
  required_headers: Record<string, string>;
}

export function requestUploadSession(token: string, input: { kind: string; filename: string; mediaType: string; sizeBytes: number; mimeType: string }): Promise<UploadSession> {
  return postJson<UploadSession>(routes.uploadSession, {
    kind: input.kind,
    filename: input.filename,
    media_type: input.mediaType,
    size_bytes: input.sizeBytes,
    mime_type: input.mimeType,
  }, token);
}

export interface CompleteUploadResult {
  ok: boolean;
  post_id: number;
  status: string;
  /** True when the session was already consumed and the server returned the existing post. */
  idempotent?: boolean;
  /** True when the server re-dispatched a previously failed processing job. */
  retry_dispatched?: boolean;
  /** Upload is acknowledged and the safety worker is queued/running. */
  moderation_queued?: boolean;
  /** PROCESSING posts remain private until the server publishes ALLOW. */
  publication_state?: 'PRIVATE_PROCESSING' | 'PUBLISHED' | string;
}

export function completeUpload(token: string, uploadId: string, input: { caption: string; contentCategory: string; tags: string[]; locationName?: string }): Promise<CompleteUploadResult> {
  return postJson<CompleteUploadResult>(routes.uploadComplete(uploadId), {
    caption: input.caption,
    content_category: input.contentCategory,
    tags: input.tags,
    location_name: input.locationName ?? '',
  }, token);
}

export interface ProcessingStatus {
  ok: boolean;
  post_id: number;
  status: string;
  stage: string;
  moderation_status?: string | null;
  is_safe?: boolean;
  media_url?: string | null;
  poster_url?: string | null;
  error?: string | null;
  retryable?: boolean;
}

export function fetchProcessingStatus(token: string, postId: number): Promise<ProcessingStatus> {
  return apiRequest<ProcessingStatus>(routes.processingStatus(postId), {}, token);
}

export function redriveProcessing(token: string, postId: number): Promise<{ ok: boolean }> {
  return postJson(routes.redrive(postId), {}, token);
}

export interface StoryViewer {
  child_id: number;
  full_name?: string | null;
  username?: string | null;
  /** Raw profile picture reference (may not be a resolved URL — render defensively). */
  profile_picture?: string | null;
  first_viewed_at?: string | null;
  last_viewed_at?: string | null;
  completion_ratio?: number | null;
}

/** Viewer list for the child's OWN story (server enforces ownership). */
export function fetchStoryViewers(token: string, storyId: number): Promise<{ ok: boolean; viewers: StoryViewer[] }> {
  return apiRequest<{ ok: boolean; viewers: StoryViewer[] }>(routes.storyViewers(storyId), {}, token);
}

// ---------------------------------------------------------------------------
// Pure upload-pipeline helpers (no native imports — safe for node tests).
// ---------------------------------------------------------------------------

const MIME_EXTENSIONS: Record<string, readonly string[]> = {
  'image/jpeg': ['jpg', 'jpeg'],
  'image/png': ['png'],
  'image/webp': ['webp'],
  'video/mp4': ['mp4', 'm4v'],
  'video/quicktime': ['mov'],
};

function extOf(name: string, fallback: string): string {
  const parts = name.split('.');
  return parts.length > 1 ? (parts[parts.length - 1] ?? fallback).toLowerCase() : fallback;
}

/** Guard against a renamed file whose extension disagrees with its MIME type. */
export function validateMediaIdentity(fileName: string, mimeType: string): void {
  const extension = extOf(fileName, '');
  const allowed = MIME_EXTENSIONS[mimeType.toLowerCase()];
  if (!allowed?.includes(extension)) throw new Error('The selected file type does not match its filename. Choose another file.');
}

/** 'image' | 'video' | null from a MIME type string. */
export function mediaKindFromMimeType(mimeType: string | null | undefined): 'image' | 'video' | null {
  const mt = (mimeType ?? '').toLowerCase();
  if (mt.startsWith('image/')) return 'image';
  if (mt.startsWith('video/')) return 'video';
  return null;
}

/** Human-friendly byte count for upload UI ("2.4 MB"). */
export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB'];
  let value = bytes / 1024;
  let unit = units[0] as string;
  for (const u of units) {
    unit = u;
    if (value < 1024 || u === 'GB') break;
    value /= 1024;
  }
  return `${value >= 100 ? Math.round(value) : Math.round(value * 10) / 10} ${unit}`;
}

/** Which upload-pipeline stage a CreateScreen failure happened in (for resume). */
export type UploadStage = 'session' | 'r2upload' | 'complete';

export function isRetryableUploadStageFailure(stage: UploadStage | null): boolean {
  return stage === 'session' || stage === 'r2upload' || stage === 'complete';
}
