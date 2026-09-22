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
  last_message?: { message_text?: string; sent_at?: string; sender_child_id?: number; is_seen?: boolean } | null;
}

export interface ChatMessage {
  child_message_id: number;
  sender_child_id: number;
  message_text?: string;
  message_type?: string;
  shared_post_id?: number | null;
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

export function fetchConversations(
  token: string,
  limit = 20,
  offset = 0,
): Promise<{ ok: boolean; conversations: ConversationItem[]; has_more: boolean }> {
  const p = new URLSearchParams({
    limit: String(Math.max(1, Math.min(limit, 50))),
    offset: String(Math.max(0, offset)),
  });
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

export function sendChatText(token: string, peerId: number, messageText: string): Promise<{ ok: boolean; status: string }> {
  return postJson(routes.chat(peerId), { message_text: messageText }, token);
}

export function sharePostToChat(token: string, peerId: number, postId: number): Promise<{ ok: boolean; message_id: number }> {
  return postJson(routes.sharePost(peerId), { post_id: postId }, token);
}
