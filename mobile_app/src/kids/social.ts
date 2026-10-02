/** Pure Kids helpers (Agent C): feed dedupe, cursors, moderation copy, polling. */

export interface KeyedItem {
  source_type?: string;
  source_id?: number;
  post_id?: number;
}

export function feedKey(item: KeyedItem): string {
  const t = item.source_type ?? 'SOCIAL';
  const id = item.source_id ?? item.post_id ?? -1;
  return `${t}:${id}`;
}

/** Deduplicate by authoritative post identity, preserving first order.
 * Skips null/non-object entries defensively: malformed server payloads used
 * to crash render here (`item.source_type` on null/undefined). */
export function dedupeFeed<T extends KeyedItem>(items: T[]): T[] {
  const seen = new Set<string>();
  const out: T[] = [];
  for (const item of items) {
    if (!item || typeof item !== 'object') continue;
    const key = feedKey(item);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(item);
  }
  return out;
}

export function mergeFeedPages<T extends KeyedItem>(pages: T[][]): T[] {
  return dedupeFeed(pages.flat());
}

/** Never render REVIEW/BLOCKED/quarantine content in public surfaces. */
export function isPubliclyVisible(item: { moderation_status?: string; is_safe?: boolean }): boolean {
  return item.moderation_status === 'ALLOWED' && item.is_safe !== false;
}

export type ProcessingStage = 'uploading' | 'processing' | 'review' | 'allowed' | 'blocked' | 'retryable' | 'failed';

export function processingStage(status: string, moderation?: string | null, retryable?: boolean): ProcessingStage {
  const s = (status || '').toUpperCase();
  const m = (moderation || '').toUpperCase();
  if (s === 'BLOCKED' || m === 'BLOCKED') return 'blocked';
  if (s === 'ALLOWED' || m === 'ALLOWED') return 'allowed';
  if (s === 'REVIEW' || m === 'REVIEW') return 'review';
  if (s === 'FAILED' || s === 'ERROR') return retryable ? 'retryable' : 'failed';
  if (s === 'UPLOADED' && retryable) return 'retryable';
  if (s === 'UPLOADED' || s === 'PROCESSING' || s === 'PENDING') return 'processing';
  return 'processing';
}

/** Terminal states stop polling. */
export function isTerminalStage(stage: ProcessingStage): boolean {
  return stage === 'allowed' || stage === 'blocked' || stage === 'review' || stage === 'retryable' || stage === 'failed';
}

export interface SocialFeedIdentity extends KeyedItem {
  child_id?: number;
}

export function engagementTarget(item: SocialFeedIdentity): { sourceType: 'SOCIAL' | 'CURATED'; sourceId: number } | null {
  const type = String(item.source_type || '').toUpperCase();
  const rawId = item.source_id ?? item.post_id;
  if ((type !== 'SOCIAL' && type !== 'CURATED') || !Number.isInteger(rawId) || Number(rawId) <= 0) return null;
  return { sourceType: type as 'SOCIAL' | 'CURATED', sourceId: Number(rawId) };
}

export function socialPostTarget(item: SocialFeedIdentity): { postId: number } | null {
  return item.source_type === 'SOCIAL' && Number.isInteger(item.post_id) && Number(item.post_id) > 0
    ? { postId: Number(item.post_id) }
    : null;
}

export function socialProfileTarget(item: SocialFeedIdentity): { targetId: number } | null {
  return item.source_type === 'SOCIAL' && Number.isInteger(item.child_id) && Number(item.child_id) > 0
    ? { targetId: Number(item.child_id) }
    : null;
}

export async function runSocialPostAction<T>(item: SocialFeedIdentity, action: (postId: number) => Promise<T>): Promise<T | undefined> {
  const target = socialPostTarget(item);
  return target ? action(target.postId) : undefined;
}

export function moderationCopy(stage: ProcessingStage): string {
  if (stage === 'review') return 'Your post is waiting for a safety check. Only you can see it for now.';
  if (stage === 'blocked') return 'This post could not be shared. Try posting something else.';
  if (stage === 'retryable') return 'Something hiccuped while preparing your post. You can try again.';
  if (stage === 'failed') return 'This post could not be prepared.';
  if (stage === 'allowed') return 'Your post is live!';
  return 'Getting your post ready…';
}

export const CHAT_BLOCKED_COPY = "That message couldn't be sent. Try saying it another way.";

export interface ChatMsg {
  child_message_id: number;
  sent_at?: string;
}

export function dedupeChat<T extends ChatMsg>(rows: T[]): T[] {
  const seen = new Set<number>();
  const out: T[] = [];
  for (const row of rows) {
    if (seen.has(row.child_message_id)) continue;
    seen.add(row.child_message_id);
    out.push(row);
  }
  return out.sort((a, b) => {
    if (a.sent_at && b.sent_at && a.sent_at !== b.sent_at) return a.sent_at < b.sent_at ? -1 : 1;
    return a.child_message_id - b.child_message_id;
  });
}

export interface PollBudget {
  attempts: number;
  maxAttempts: number;
}

/** Stop polling on terminal state, background, or exhausted budget. */
export function shouldStopPolling(stage: ProcessingStage, budget: PollBudget, foreground: boolean): boolean {
  if (!foreground) return true;
  if (isTerminalStage(stage)) return true;
  return budget.attempts >= budget.maxAttempts;
}

export const MAX_POLL_ATTEMPTS = 30;
export const MAX_POLL_DURATION_MS = 2 * 60_000;

/** At most the active reel and its immediate neighbors may hold a media source. */
export function shouldLoadReel(index: number, activeIndex: number): boolean {
  return Math.abs(index - activeIndex) <= 1;
}

/** Exactly one reel may play, and never while the app is inactive. */
export function shouldPlayReel(index: number, activeIndex: number, foreground: boolean): boolean {
  return foreground && index === activeIndex;
}

export interface ConversationPreview {
  conversation_id: number;
  peer_id: number;
  last_message?: { sender_child_id?: number; is_seen?: boolean } | null;
}

/** Deduplicate conversations by their server identity, preserving first order. */
export function dedupeConversations<T extends ConversationPreview>(rows: T[]): T[] {
  const seen = new Set<number>();
  const out: T[] = [];
  for (const row of rows) {
    if (seen.has(row.conversation_id)) continue;
    seen.add(row.conversation_id);
    out.push(row);
  }
  return out;
}

/**
 * A message stuck in REVIEW must render as a pending state, never as a
 * normal delivered message. The server only ever returns REVIEW messages to
 * their sender, so this is checked for own messages.
 */
export function isChatMessagePending(
  message: { moderation_status?: string } | null | undefined,
  isOwn: boolean,
): boolean {
  if (!isOwn) return false;
  const status = (message?.moderation_status ?? 'ALLOWED').toUpperCase();
  return status !== 'ALLOWED';
}

export function canMessageRelationship(relationship: { can_message?: boolean } | null | undefined): boolean {
  return relationship?.can_message === true;
}

export function isConversationUnread(conversation: {
  peer_id: number;
  last_message?: { sender_child_id?: number; is_seen?: boolean } | null;
}): boolean {
  return conversation.last_message?.sender_child_id === conversation.peer_id
    && conversation.last_message.is_seen === false;
}

/** Stale-query guard: only the latest search response may render. */
export function createSearchGuard() {
  let latest = 0;
  return {
    next(): number {
      latest += 1;
      return latest;
    },
    isLatest(id: number): boolean {
      return id === latest;
    },
  };
}

/**
 * Maps a server notification target_url to an app destination. The backend
 * only ever creates /chat/<id>/ and /child/dashboard/ style URLs for kids
 * (plus parent-control alerts); anything unrecognized returns null so the
 * caller can safely ignore it instead of navigating somewhere wrong.
 */
export function notificationDestination(url: string | null | undefined): { route: string; params: Record<string, unknown> } | null {
  const target = url ?? '';
  const postMatch = target.match(/\/post\/(\d+)/);
  if (postMatch?.[1]) return { route: 'PostDetail', params: { postId: Number(postMatch[1]) } };
  const chatMatch = target.match(/\/chat\/(\d+)/);
  if (chatMatch?.[1]) return { route: 'Chat', params: { peerId: Number(chatMatch[1]) } };
  const profileMatch = target.match(/\/profile\/(\d+)/);
  if (profileMatch?.[1]) return { route: 'OtherProfile', params: { targetId: Number(profileMatch[1]) } };
  if (/\/child\/dashboard\/?/.test(target)) return { route: 'KidsTabs', params: { tab: 'FeedTab' } };
  return null;
}
