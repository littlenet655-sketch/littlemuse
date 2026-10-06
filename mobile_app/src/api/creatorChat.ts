/** Curated creator mentor chat API. */
import { apiRequest, routes } from './client';

export interface CreatorChatMessage {
  message_id: number;
  sender: 'CHILD' | 'CREATOR';
  message_text: string;
  created_at?: string;
}

export interface CreatorChatPayload {
  ok: boolean;
  creator: {
    creator_id: number;
    display_name: string;
    username: string;
    interest_vertical?: string | null;
    bio?: string | null;
    avatar_url?: string | null;
  };
  messages: CreatorChatMessage[];
}

export function fetchCreatorChat(token: string, creatorId: number): Promise<CreatorChatPayload> {
  return apiRequest(routes.creatorChat(creatorId), {}, token);
}

export function sendCreatorChat(
  token: string,
  creatorId: number,
  messageText: string,
): Promise<CreatorChatPayload & { reply?: CreatorChatMessage }> {
  return apiRequest(routes.creatorChat(creatorId), {
    method: 'POST',
    body: JSON.stringify({ message_text: messageText }),
    // K2 generation is server-side and may legitimately outlive the normal
    // 10s REST timeout. Keep the mobile request below the server's bounded
    // provider timeout rather than retrying an in-flight generation.
    timeoutMs: 35_000,
  }, token);
}
