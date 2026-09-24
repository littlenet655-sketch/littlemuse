/** Kids notifications + chat API (Agent C). */
import { apiRequest, routes } from './client';

export interface NotificationItem {
  notification_id: number;
  notification_type?: string;
  message?: string;
  target_url?: string | null;
  actor_id?: number | null;
  actor_name?: string | null;
  actor_avatar_url?: string | null;
  is_read?: boolean;
  created_at?: string;
}

export interface ConversationItem {
  conversation_id: number;
  peer_id: number;
  peer_name?: string;
  peer_avatar_url?: string | null;
  last_message?: { message_text?: string; message_type?: string; sent_at?: string; sender_child_id?: number; is_seen?: boolean } | null;
}

export interface ChatMessage {
  child_message_id: number;
  sender_child_id: number;
  message_text?: string;
  message_type?: string;
  shared_post_id?: number | null;
  reply_to_message_id?: number | null;
  reply_message_text?: string | null;
  reply_message_type?: string | null;
  reply_sender_child_id?: number | null;
  reactions?: Record<string, number>;
  viewer_reaction?: string | null;
  media_url?: string | null;
  moderation_status?: string;
  sent_at?: string;
  /** Read receipt: the server returns this per message (m.*) and marks peer
      messages seen on every fetch. Shown under the last own ALLOWED message. */
  is_seen?: boolean;
}

async function get<T>(path: string, token: string): Promise<T> {
  return apiRequest<T>(path, {}, token);
}

async function postJson<T>(path: string, body: Record<string, unknown>, token: string): Promise<T> {
  return apiRequest<T>(path, { method: 'POST', body: JSON.stringify(body) }, token);
}

export function fetchNotifications(token: string): Promise<{ ok: boolean; notifications: NotificationItem[] }> {
  return get(routes.notifications, token);
}

export function markNotificationsRead(token: string, ids?: number[]): Promise<{ ok: boolean; marked: number | 'all' }> {
  return postJson(routes.notificationsRead, ids ? { notification_ids: ids } : {}, token);
}

export interface ConversationsPage {
  ok: boolean;
  conversations: ConversationItem[];
  /** True when the server has another page after this one (offset paging). */
  has_more?: boolean;
}

/**
 * Server-paged conversation list. The backend clamps limit to 1..50 and
 * returns has_more (it fetches one row past the limit).
 */
export function fetchConversations(
  token: string,
  opts?: { limit?: number; offset?: number },
): Promise<ConversationsPage> {
  const p = new URLSearchParams({ limit: String(opts?.limit ?? 20) });
  if (opts?.offset) p.set('offset', String(opts.offset));
  return get(`${routes.conversations}?${p.toString()}`, token);
}

export function fetchChat(token: string, peerId: number, limit = 30, beforeId?: number): Promise<{ ok: boolean; peer: Record<string, unknown>; messages: ChatMessage[]; peer_typing?: boolean }> {
  const p = new URLSearchParams({ limit: String(limit) });
  if (beforeId) p.set('before_id', String(beforeId));
  return get(`${routes.chat(peerId)}?${p.toString()}`, token);
}

/** Poll for messages newer than afterId plus the peer typing flag. */
export function fetchChatUpdates(token: string, peerId: number, afterId: number): Promise<{ ok: boolean; messages: ChatMessage[]; peer_typing?: boolean }> {
  const p = new URLSearchParams({ after_id: String(afterId), limit: '50' });
  return get(`${routes.chat(peerId)}?${p.toString()}`, token);
}

/** Typing heartbeat; server enforces the TTL. Fire-and-forget safe. */
export function sendTyping(token: string, peerId: number): Promise<{ ok: boolean }> {
  return postJson(`${routes.chat(peerId)}/typing`, {}, token);
}

export function sendChatText(token: string, peerId: number, messageText: string, replyToMessageId?: number | null): Promise<{ ok: boolean; status: string; message_id?: number }> {
  return postJson(routes.chat(peerId), {
    message_text: messageText,
    reply_to_message_id: replyToMessageId ?? null,
  }, token);
}

export const MESSAGE_REACTION_EMOJIS = ['❤️', '😂', '😮', '👏', '🔥', '⭐'] as const;

export function reactToMessage(token: string, peerId: number, messageId: number, emoji: string): Promise<{ ok: boolean; viewer_reaction: string | null; reactions: Record<string, number> }> {
  return postJson(routes.messageReaction(peerId, messageId), { emoji }, token);
}

export function sharePostToChat(token: string, peerId: number, postId: number): Promise<{ ok: boolean; message_id: number }> {
  return postJson(routes.sharePost(peerId), { post_id: postId }, token);
}


export interface ChatUploadSession {
  ok: boolean;
  upload_id: string;
  upload_url: string;
  object_key: string;
  expires_at: string;
  required_headers: Record<string, string>;
  media_type: 'IMAGE' | 'VIDEO';
}

export function requestChatUploadSession(
  token: string,
  peerId: number,
  input: { mediaType: 'IMAGE' | 'VIDEO'; filename: string; sizeBytes: number; mimeType: string; extension?: string },
): Promise<ChatUploadSession> {
  return postJson(routes.chatUploadSession(peerId), {
    media_type: input.mediaType,
    filename: input.filename,
    size_bytes: input.sizeBytes,
    mime_type: input.mimeType,
    extension: input.extension,
  }, token);
}

export function completeChatUpload(
  token: string,
  peerId: number,
  uploadId: string,
): Promise<{ ok: boolean; message_id: number; status: 'ALLOWED' | 'REVIEW' | string; idempotent?: boolean }> {
  return postJson(routes.chatUploadComplete(peerId, uploadId), {}, token);
}
