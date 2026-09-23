import { ApiError, parseErrorResponse, retryDelayMs, shouldRetryRequest } from './errors';

export { ApiError };
export * from './errors';

export function apiBaseUrl(): string {
  return (process.env.EXPO_PUBLIC_API_BASE_URL ?? '').replace(/\/+$/, '');
}

/** Public releases must never transmit family data to local/private or cleartext endpoints. */
export function productionApiUrlProblem(raw: string): string | null {
  const value = raw.trim();
  if (!value) return 'missing';
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    return 'invalid';
  }
  if (parsed.protocol !== 'https:') return 'https_required';
  const host = parsed.hostname.toLowerCase();
  if (host === 'localhost' || host === '127.0.0.1' || host === '::1') return 'private_host';
  if (/^10\./.test(host) || /^192\.168\./.test(host)) return 'private_host';
  const match = host.match(/^172\.(\d+)\./);
  if (match && Number(match[1]) >= 16 && Number(match[1]) <= 31) return 'private_host';
  return null;
}

function isDevelopmentRuntime(): boolean {
  return (globalThis as typeof globalThis & { __DEV__?: boolean }).__DEV__ === true;
}

/** Kept for components that only need to know whether a backend is configured. */
export const API_BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL ?? '';

export const REQUEST_TIMEOUT_MS = 10000;

/** Prefer /api/mobile/v2 where a v2 route exists; keep v1 only where no v2 exists. */
export const routes = {
  login: '/api/mobile/v1/auth/login',
  logout: '/api/mobile/v1/auth/logout',
  me: '/api/mobile/v1/me',
  parentRegister: '/api/mobile/v1/auth/parent/register',
  parentVerifyEmail: '/api/mobile/v1/auth/parent/verify-email',
  parentResendEmail: '/api/mobile/v1/auth/parent/resend-email',
  parentEmailStatus: '/api/mobile/v1/auth/parent/email-status',
  forgotPassword: '/api/mobile/v1/auth/forgot-password',
  resetPassword: '/api/mobile/v1/auth/reset-password',
  quiz: '/api/mobile/v1/kids/quiz',
  quizAnswer: (quizId: number) => `/api/mobile/v1/kids/quiz/${quizId}/answer`,
  kidsTimeLimitStatus: '/api/mobile/v1/kids/time-limit/status',
  kidsTimeLimitReset: '/api/mobile/v1/kids/time-limit/reset',
  parentCreateChild: '/api/mobile/v1/parent/children',
  parentDashboard: '/api/mobile/v1/parent/dashboard',
  parentControls: (childId: number) => `/api/mobile/v1/parent/controls/${childId}`,
  parentTimeLimit: (childId: number) => `/api/mobile/v1/parent/time-limit/${childId}`,
  parentResetTimeLimit: (childId: number) => `/api/mobile/v1/parent/time-limit/${childId}/reset`,
  parentExtendTimeLimit: (childId: number) => `/api/mobile/v1/parent/time-limit/${childId}/extend`,
  parentSafety: '/api/mobile/v1/parent/safety',
  parentReview: (eventId: number) => `/api/mobile/v1/parent/safety/${eventId}`,
  parentFollowRequests: '/api/mobile/v1/parent/follow-requests',
  parentFollowAction: '/api/mobile/v1/parent/follow-requests/action',
  parentNotifications: '/api/mobile/v1/parent/notifications',
  parentActivity: (childId: number) => `/api/mobile/v1/parent/activity/${childId}`,
  /** Read-only per-child watch aggregates through the bearer-authenticated mobile alias. */
  parentViewingInsights: (childId: number) => `/api/mobile/v1/parent/child/${childId}/viewing-insights`,
  parentResetChildPassword: (childId: number) => `/api/mobile/v1/parent/child/${childId}/reset-password`,
  parentChild: (childId: number) => `/api/mobile/v1/parent/child/${childId}`,
  adminDashboard: '/api/mobile/v1/admin/dashboard',
  adminReviews: '/api/mobile/v1/admin/reviews',
  adminReview: (eventId: number) => `/api/mobile/v1/admin/reviews/${eventId}`,
  adminUsers: '/api/mobile/v1/admin/users',
  adminUserStatus: (userId: number) => `/api/mobile/v1/admin/users/${userId}/status`,
  adminAudit: '/api/mobile/v1/admin/audit',
  // v2 media pipeline (Agent C owns the posting UI; routes stay centralized here).
  feedV2: '/api/mobile/v2/kids/feed',
  reelsV2: '/api/mobile/v2/kids/reels',
  heartbeatV2: '/api/mobile/v2/kids/heartbeat',
  discoverV2: '/api/mobile/v2/kids/discover',
  impressions: '/api/mobile/v2/kids/impressions',
  impressionsBatch: '/api/mobile/v2/kids/impressions/batch',
  recommendationActions: '/api/mobile/v2/kids/recommendation-actions',
  reelPlayback: (postId: number) => `/api/mobile/v2/kids/reels/${postId}/playback`,
  curatedReelPlayback: (contentId: number) => `/api/mobile/v2/kids/reels/curated/${contentId}/playback`,
  storyView: (storyId: number) => `/api/mobile/v2/kids/stories/${storyId}/view`,
  storyViewers: (storyId: number) => `/api/mobile/v2/kids/stories/${storyId}/viewers`,
  uploadSession: '/api/mobile/v2/uploads/session',
  uploadComplete: (uploadId: string) => `/api/mobile/v2/uploads/${encodeURIComponent(uploadId)}/complete`,
  processingStatus: (postId: number) => `/api/mobile/v2/posts/${postId}/processing-status`,
  redrive: (postId: number) => `/api/mobile/v2/posts/${postId}/redrive`,
  kidsHome: '/api/mobile/v1/kids/home',
  ownProfile: '/api/mobile/v1/kids/profile',
  otherProfile: (targetId: number) => `/api/mobile/v1/kids/profiles/${targetId}`,
  profileActions: (targetId: number) => `/api/mobile/v1/kids/profiles/${targetId}/actions`,
  postDetail: (postId: number) => `/api/mobile/v1/kids/posts/${postId}`,
  like: (postId: number) => `/api/mobile/v1/kids/posts/${postId}/like`,
  save: (postId: number) => `/api/mobile/v1/kids/posts/${postId}/save`,
  comments: (postId: number) => `/api/mobile/v1/kids/posts/${postId}/comments`,
  addComment: (postId: number) => `/api/mobile/v1/kids/posts/${postId}/comment`,
  deletePost: (postId: number) => `/api/mobile/v1/kids/posts/${postId}`,
  deleteStory: (storyId: number) => `/api/mobile/v2/kids/stories/${storyId}`,
  follow: (childId: number) => `/api/mobile/v1/kids/follow/${childId}`,
  connections: '/api/mobile/v1/kids/connections',
  connectionRequests: '/api/mobile/v1/kids/connections/requests',
  saved: '/api/mobile/v1/kids/saved',
  block: (targetId: number) => `/api/mobile/v1/kids/block/${targetId}`,
  mute: (targetId: number) => `/api/mobile/v1/kids/mute/${targetId}`,
  blockedUsers: '/api/mobile/v1/kids/blocked-users',
  mutedUsers: '/api/mobile/v1/kids/muted-users',
  report: '/api/mobile/v1/kids/report',
  reports: '/api/mobile/v1/kids/reports',
  notifications: '/api/mobile/v1/kids/notifications',
  notificationsRead: '/api/mobile/v1/kids/notifications/read',
  conversations: '/api/mobile/v1/kids/messages',
  chat: (peerId: number) => `/api/mobile/v1/kids/chat/${peerId}`,
  sharePost: (peerId: number) => `/api/mobile/v1/kids/chat/${peerId}/share`,
  deviceRegister: '/api/mobile/v2/device/register',
  deviceUnregister: '/api/mobile/v2/device/unregister',
} as const;

type UnauthorizedHandler = () => void;
let unauthorizedHandler: UnauthorizedHandler | null = null;

/** Centralized 401 handling: AuthProvider registers LOCAL invalidation here (never a network call). */
export function setUnauthorizedHandler(handler: UnauthorizedHandler | null): void {
  unauthorizedHandler = handler;
}

let suppressUnauthorizedDepth = 0;

/**
 * Runs fn with the centralized 401 handler suppressed. Used exactly once per
 * user-initiated sign-out so an expired token on /logout cannot recurse.
 */
export async function withoutUnauthorizedHandler<T>(fn: () => Promise<T>): Promise<T> {
  suppressUnauthorizedDepth += 1;
  try {
    return await fn();
  } finally {
    suppressUnauthorizedDepth -= 1;
  }
}

export interface RequestOptions extends RequestInit {
  timeoutMs?: number;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}, token?: string): Promise<T> {
  const baseUrl = apiBaseUrl();
  if (!baseUrl) {
    throw new ApiError(0, 'misconfigured', 'The app is not pointed at a LittleNet backend.');
  }
  if (!isDevelopmentRuntime()) {
    const problem = productionApiUrlProblem(baseUrl);
    if (problem) {
      throw new ApiError(0, 'insecure_api_configuration', 'This LittleNet build is not connected to the secure production service. Please update the app.');
    }
  }
  const method = (options.method ?? 'GET').toUpperCase();
  const timeoutMs = options.timeoutMs ?? REQUEST_TIMEOUT_MS;

  let attempt = 0;
  for (;;) {
    if (options.signal?.aborted) {
      throw parseErrorResponse(0, { error: 'request_cancelled' });
    }
    const controller = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, timeoutMs);
    const onCallerAbort = (): void => controller.abort();
    // Caller abort and timeout share one controller: either aborts the request.
    options.signal?.addEventListener('abort', onCallerAbort, { once: true });
    try {
      const headers = new Headers(options.headers);
      headers.set('Accept', 'application/json');
      if (token) headers.set('Authorization', `Bearer ${token}`);
      const body = options.body;
      if (body && !(body instanceof FormData) && !headers.has('Content-Type')) {
        headers.set('Content-Type', 'application/json');
      }
      const response = await fetch(`${baseUrl}${path}`, { ...options, headers, signal: controller.signal });
      const payload: unknown = await response.json().catch(() => ({}));
      if (!response.ok) {
        const err = parseErrorResponse(response.status, payload);
        if (response.status === 401 && suppressUnauthorizedDepth === 0) unauthorizedHandler?.();
        if (shouldRetryRequest(method, attempt, response.status)) {
          attempt += 1;
          await sleep(retryDelayMs(attempt));
          continue;
        }
        throw err;
      }
      return payload as T;
    } catch (error) {
      if (error instanceof ApiError) throw error;
      if (options.signal?.aborted) {
        // Caller cancellation is intentional: never retry, never misreport.
        throw parseErrorResponse(0, { error: 'request_cancelled' });
      }
      const aborted = (error instanceof Error && error.name === 'AbortError') || (typeof DOMException !== 'undefined' && error instanceof DOMException && error.name === 'AbortError');
      const networkError = parseErrorResponse(0, { error: timedOut || aborted ? 'request_timeout' : 'network_unreachable' });
      if (shouldRetryRequest(method, attempt, 0)) {
        attempt += 1;
        await sleep(retryDelayMs(attempt));
        continue;
      }
      throw networkError;
    } finally {
      clearTimeout(timer);
      options.signal?.removeEventListener('abort', onCallerAbort);
    }
  }
}
