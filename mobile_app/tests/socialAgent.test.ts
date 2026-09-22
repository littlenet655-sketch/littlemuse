/// <reference types="node" />
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

process.env.EXPO_PUBLIC_API_BASE_URL = 'https://backend.test.invalid';

import { setUnauthorizedHandler } from '../src/api/client';
import {
  addComment,
  blockUser,
  deletePost,
  deleteStory,
  fetchBlockedUsers,
  fetchComments,
  fetchConnectionRequests,
  fetchConnections,
  fetchMutedUsers,
  fetchReports,
  muteUser,
  submitReport,
  toggleFollow,
  toggleLike,
  toggleSave,
} from '../src/api/kidsSocial';
import {
  fetchChat,
  fetchConversations,
  fetchNotifications,
  markNotificationsRead,
  sendChatText,
  sharePostToChat,
} from '../src/api/kidsChat';
import { searchDiscover } from '../src/api/kidsProfiles';
import { submitRecommendationAction } from '../src/api/recommendation';
import {
  canMessageRelationship,
  dedupeChat,
  dedupeConversations,
  dedupeFeed,
  feedKey,
  isChatMessagePending,
  isConversationUnread,
  isPubliclyVisible,
  notificationDestination,
} from '../src/kids/social';

interface SeenRequest {
  url: string;
  init: RequestInit;
}

let seen: SeenRequest[] = [];
let nextPayload: unknown = { ok: true };
let nextStatus = 200;

function stubFetch(): void {
  seen = [];
  nextPayload = { ok: true };
  nextStatus = 200;
  setUnauthorizedHandler(null);
  (globalThis as unknown as Record<string, unknown>).fetch = async (url: unknown, init?: RequestInit) => {
    seen.push({ url: String(url), init: init ?? {} });
    return {
      ok: nextStatus >= 200 && nextStatus < 300,
      status: nextStatus,
      json: async () => nextPayload,
    };
  };
}

function bodyJson(index = 0): Record<string, unknown> {
  return JSON.parse(String(seen[index]?.init.body ?? '{}')) as Record<string, unknown>;
}

describe('follow / unfollow contract', () => {
  it('toggles follow with a POST and no body; server owns pending state', async () => {
    stubFetch();
    nextPayload = { ok: true, status: 'pending' };
    const res = await toggleFollow('tok', 7);
    assert.equal(seen[0]?.url, 'https://backend.test.invalid/api/mobile/v1/kids/follow/7');
    assert.equal(seen[0]?.init.method, 'POST');
    assert.deepEqual(bodyJson(), {});
    assert.equal(res.status, 'pending');
  });

  it('reads follow requests from the real endpoint', async () => {
    stubFetch();
    nextPayload = { ok: true, incoming: [{ id: 1 }], outgoing: [] };
    const res = await fetchConnectionRequests('tok');
    assert.equal(seen[0]?.url, 'https://backend.test.invalid/api/mobile/v1/kids/connections/requests');
    assert.equal(res.incoming.length, 1);
  });

  it('reads approved connections', async () => {
    stubFetch();
    nextPayload = { ok: true, followers: [], following: [], suggested: [] };
    await fetchConnections('tok');
    assert.equal(seen[0]?.url, 'https://backend.test.invalid/api/mobile/v1/kids/connections');
  });
});

describe('block / mute / report contract', () => {
  it('blocks with an explicit action body and reads the authoritative flag', async () => {
    stubFetch();
    nextPayload = { ok: true, blocked: true };
    const res = await blockUser('tok', 9, 'block');
    assert.equal(seen[0]?.url, 'https://backend.test.invalid/api/mobile/v1/kids/block/9');
    assert.deepEqual(bodyJson(), { action: 'block' });
    assert.equal(res.blocked, true);
  });

  it('unblocks and unmutes with the matching actions', async () => {
    stubFetch();
    nextPayload = { ok: true, blocked: false };
    const unblocked = await blockUser('tok', 9, 'unblock');
    assert.deepEqual(bodyJson(), { action: 'unblock' });
    assert.equal(unblocked.blocked, false);

    nextPayload = { ok: true, muted: false };
    const unmuted = await muteUser('tok', 9, 'unmute');
    assert.equal(seen[1]?.url, 'https://backend.test.invalid/api/mobile/v1/kids/mute/9');
    assert.deepEqual(bodyJson(1), { action: 'unmute' });
    assert.equal(unmuted.muted, false);
  });

  it('lists blocked and muted users from the real endpoints', async () => {
    stubFetch();
    nextPayload = { ok: true, blocked_users: [] };
    await fetchBlockedUsers('tok');
    assert.equal(seen[0]?.url, 'https://backend.test.invalid/api/mobile/v1/kids/blocked-users');
    nextPayload = { ok: true, muted_users: [] };
    await fetchMutedUsers('tok');
    assert.equal(seen[1]?.url, 'https://backend.test.invalid/api/mobile/v1/kids/muted-users');
  });

  it('submits reports with target type, id and reason', async () => {
    stubFetch();
    nextPayload = { ok: true };
    await submitReport('tok', 'POST', 42, 'Unsafe or unkind');
    assert.equal(seen[0]?.url, 'https://backend.test.invalid/api/mobile/v1/kids/report');
    assert.deepEqual(bodyJson(), { target_type: 'POST', target_id: 42, reason: 'Unsafe or unkind', details: '' });
  });

  it('reads the report history', async () => {
    stubFetch();
    nextPayload = { ok: true, reports: [] };
    await fetchReports('tok');
    assert.equal(seen[0]?.url, 'https://backend.test.invalid/api/mobile/v1/kids/reports');
  });
});

describe('like / save / comment contract', () => {
  it('like returns the authoritative liked flag and count', async () => {
    stubFetch();
    nextPayload = { ok: true, liked: true, likes: 6 };
    const res = await toggleLike('tok', 5);
    assert.equal(seen[0]?.url, 'https://backend.test.invalid/api/mobile/v1/kids/posts/5/like');
    assert.equal(res.liked, true);
    assert.equal(res.likes, 6);
  });

  it('save returns the authoritative saved flag', async () => {
    stubFetch();
    nextPayload = { ok: true, saved: false };
    const res = await toggleSave('tok', 5);
    assert.equal(seen[0]?.url, 'https://backend.test.invalid/api/mobile/v1/kids/posts/5/save');
    assert.equal(res.saved, false);
  });

  it('comment POST returns the moderation status for pending-state UI', async () => {
    stubFetch();
    nextPayload = { ok: true, status: 'REVIEW', comment_id: 11 };
    const res = await addComment('tok', 5, 'hello');
    assert.equal(seen[0]?.url, 'https://backend.test.invalid/api/mobile/v1/kids/posts/5/comment');
    assert.deepEqual(bodyJson(), { text: 'hello' });
    assert.equal(res.status, 'REVIEW');
    assert.equal(res.comment_id, 11);
  });

  it('comment GET hits the real comments endpoint', async () => {
    stubFetch();
    nextPayload = { ok: true, comments: [] };
    await fetchComments('tok', 5);
    assert.equal(seen[0]?.url, 'https://backend.test.invalid/api/mobile/v1/kids/posts/5/comments');
  });
});


  it('deletes owner posts and stories through bearer-native routes', async () => {
    stubFetch();
    nextPayload = { ok: true };
    await deletePost('tok', 21);
    assert.equal(seen[0]?.url, 'https://backend.test.invalid/api/mobile/v1/kids/posts/21');
    assert.equal(String(seen[0]?.init.method).toUpperCase(), 'DELETE');

    await deleteStory('tok', 34);
    assert.equal(seen[1]?.url, 'https://backend.test.invalid/api/mobile/v2/kids/stories/34');
    assert.equal(String(seen[1]?.init.method).toUpperCase(), 'DELETE');
  });

describe('chat contract', () => {
  it('fetches a page with limit and before_id cursor', async () => {
    stubFetch();
    nextPayload = { ok: true, peer: {}, messages: [] };
    await fetchChat('tok', 3, 30, 99);
    assert.equal(
      seen[0]?.url,
      'https://backend.test.invalid/api/mobile/v1/kids/chat/3?limit=30&before_id=99',
    );
  });

  it('sends text and surfaces the moderation status', async () => {
    stubFetch();
    nextPayload = { ok: true, status: 'REVIEW' };
    const res = await sendChatText('tok', 3, 'hi there');
    assert.equal(seen[0]?.url, 'https://backend.test.invalid/api/mobile/v1/kids/chat/3');
    assert.deepEqual(bodyJson(), { message_text: 'hi there' });
    assert.equal(res.status, 'REVIEW');
  });

  it('shares a post into a chat with the real share endpoint', async () => {
    stubFetch();
    nextPayload = { ok: true, message_id: 77 };
    const res = await sharePostToChat('tok', 3, 21);
    assert.equal(seen[0]?.url, 'https://backend.test.invalid/api/mobile/v1/kids/chat/3/share');
    assert.deepEqual(bodyJson(), { post_id: 21 });
    assert.equal(res.message_id, 77);
  });

  it('lists conversations with real backend pagination', async () => {
    stubFetch();
    nextPayload = { ok: true, conversations: [], has_more: true };
    const page = await fetchConversations('tok', 20, 40);
    assert.equal(seen[0]?.url, 'https://backend.test.invalid/api/mobile/v1/kids/messages?limit=20&offset=40');
    assert.equal(page.has_more, true);
  });
});

describe('notifications contract', () => {
  it('fetches notifications and marks single/all as read', async () => {
    stubFetch();
    nextPayload = { ok: true, notifications: [] };
    await fetchNotifications('tok');
    assert.equal(seen[0]?.url, 'https://backend.test.invalid/api/mobile/v1/kids/notifications');

    nextPayload = { ok: true, marked: 1 };
    await markNotificationsRead('tok', [4]);
    assert.equal(seen[1]?.url, 'https://backend.test.invalid/api/mobile/v1/kids/notifications/read');
    assert.deepEqual(bodyJson(1), { notification_ids: [4] });

    nextPayload = { ok: true, marked: 'all' };
    await markNotificationsRead('tok');
    assert.deepEqual(bodyJson(2), {});
  });

  it('maps server target URLs to app destinations', () => {
    assert.deepEqual(notificationDestination('/chat/12/'), { route: 'Chat', params: { peerId: 12 } });
    assert.deepEqual(notificationDestination('/post/34/'), { route: 'PostDetail', params: { postId: 34 } });
    assert.deepEqual(notificationDestination('/child/dashboard/'), { route: 'KidsTabs', params: { tab: 'FeedTab' } });
    assert.equal(notificationDestination('/parent/safety/'), null);
    assert.equal(notificationDestination(null), null);
  });
});

describe('discover + recommendations contract', () => {
  it('searches discover v2 with the query param', async () => {
    stubFetch();
    nextPayload = { ok: true, pii_warning: false, children: [], posts: [] };
    await searchDiscover('tok', 'space');
    assert.equal(seen[0]?.url, 'https://backend.test.invalid/api/mobile/v2/kids/discover?q=space');
  });

  it('records recommendation feedback through the v2 contract', async () => {
    stubFetch();
    nextPayload = { ok: true, action: 'NOT_INTERESTED' };
    await submitRecommendationAction('tok', { source_type: 'SOCIAL', source_id: 9, action: 'NOT_INTERESTED' });
    assert.equal(seen[0]?.url, 'https://backend.test.invalid/api/mobile/v2/kids/recommendation-actions');
    assert.deepEqual(bodyJson(), { source_type: 'SOCIAL', source_id: 9, action: 'NOT_INTERESTED' });
  });
});

describe('social helpers', () => {
  it('dedupes feed items by source identity', () => {
    const items = [
      { source_type: 'SOCIAL', source_id: 1 },
      { source_type: 'SOCIAL', source_id: 1 },
      { source_type: 'CURATED', source_id: 1 },
    ];
    assert.deepEqual(dedupeFeed(items).map(feedKey), ['SOCIAL:1', 'CURATED:1']);
  });

  it('dedupes chat messages by id and sorts oldest-first', () => {
    const rows = [
      { child_message_id: 2, sent_at: '2026-09-21T10:00:01Z' },
      { child_message_id: 1, sent_at: '2026-09-21T10:00:00Z' },
      { child_message_id: 2, sent_at: '2026-09-21T10:00:01Z' },
    ];
    assert.deepEqual(dedupeChat(rows).map((r) => r.child_message_id), [1, 2]);
  });

  it('dedupes conversations by conversation id', () => {
    const rows = [
      { conversation_id: 5, peer_id: 8 },
      { conversation_id: 5, peer_id: 8 },
      { conversation_id: 6, peer_id: 9 },
    ];
    assert.deepEqual(dedupeConversations(rows).map((r) => r.conversation_id), [5, 6]);
  });

  it('never shows a REVIEW message as delivered', () => {
    assert.equal(isChatMessagePending({ moderation_status: 'REVIEW' }, true), true);
    assert.equal(isChatMessagePending({ moderation_status: 'ALLOWED' }, true), false);
    // A peer can never see our REVIEW message, so it is never "pending" for them.
    assert.equal(isChatMessagePending({ moderation_status: 'REVIEW' }, false), false);
  });

  it('flags unread conversations only for peer-sent unseen messages', () => {
    assert.equal(isConversationUnread({ peer_id: 8, last_message: { sender_child_id: 8, is_seen: false } }), true);
    assert.equal(isConversationUnread({ peer_id: 8, last_message: { sender_child_id: 1, is_seen: false } }), false);
    assert.equal(isConversationUnread({ peer_id: 8, last_message: { sender_child_id: 8, is_seen: true } }), false);
    assert.equal(isConversationUnread({ peer_id: 8, last_message: null }), false);
  });

  it('gates messaging on the server relationship flag', () => {
    assert.equal(canMessageRelationship({ can_message: true }), true);
    assert.equal(canMessageRelationship({ can_message: false }), false);
    assert.equal(canMessageRelationship(null), false);
  });

  it('hides non-public content from public surfaces', () => {
    assert.equal(isPubliclyVisible({ moderation_status: 'ALLOWED', is_safe: true }), true);
    assert.equal(isPubliclyVisible({ moderation_status: 'REVIEW', is_safe: true }), false);
    assert.equal(isPubliclyVisible({ moderation_status: 'ALLOWED', is_safe: false }), false);
  });
});
