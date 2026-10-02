import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

process.env.EXPO_PUBLIC_API_BASE_URL = 'https://backend.test.invalid';

import { setUnauthorizedHandler } from '../src/api/client';
import { blockUser, fetchPostDetail, muteUser, toggleFollow } from '../src/api/kidsSocial';
import { fetchOtherProfile } from '../src/api/kidsProfiles';
import { fetchChat, markNotificationsRead, sendChatText, sharePostToChat } from '../src/api/kidsChat';
import { completeUpload, fetchProcessingStatus, redriveProcessing, requestUploadSession } from '../src/api/kidsUpload';
import { canMessageRelationship, CHAT_BLOCKED_COPY, createSearchGuard, dedupeChat, isConversationUnread, moderationCopy, shouldStopPolling } from '../src/kids/social';

let seen: Array<{ url: string; init: RequestInit }> = [];
let nextPayload: unknown = { ok: true };
let nextStatus = 200;

function stub() {
  seen = [];
  (globalThis as unknown as Record<string, unknown>).fetch = async (url: unknown, init?: RequestInit) => {
    seen.push({ url: String(url), init: init ?? {} });
    return { ok: nextStatus >= 200 && nextStatus < 300, status: nextStatus, json: async () => nextPayload };
  };
}

describe('agentC relationships/upload/chat/notifications', () => {
  it('follow/mute/block plus relationship state', async () => {
    stub();
    setUnauthorizedHandler(null);
    nextStatus = 200;
    nextPayload = { ok: true, status: 'pending' };
    const f = await toggleFollow('tok', 9);
    assert.equal(f.status, 'pending');
    nextPayload = { ok: true, muted: true };
    await muteUser('tok', 9, 'mute');
    assert.ok(seen[1]?.url.endsWith('/api/mobile/v1/kids/mute/9'));
    nextPayload = { ok: true, blocked: true };
    await blockUser('tok', 9, 'block');
    assert.ok(seen[2]?.url.endsWith('/api/mobile/v1/kids/block/9'));
    nextPayload = { ok: true, profile: {}, counts: {}, posts: [], relationship: { connected: false, pending: true, can_message: false } };
    const p = await fetchOtherProfile('tok', 9);
    assert.equal(p.relationship?.pending, true);
  });

  it('v2 upload session/complete/status/redrive contracts', async () => {
    stub();
    nextStatus = 200;
    nextPayload = { ok: true, upload_id: 'u', upload_url: 'https://r2/put', object_key: 'k', expires_at: 'x', required_headers: { 'Content-Type': 'image/jpeg' } };
    const s = await requestUploadSession('tok', { kind: 'post', filename: 'a.jpg', mediaType: 'IMAGE', sizeBytes: 10, mimeType: 'image/jpeg' });
    assert.equal(s.required_headers['Content-Type'], 'image/jpeg');
    nextPayload = { ok: true, post_id: 11, status: 'PROCESSING' };
    const done = await completeUpload('tok', 'u', { caption: 'hi', contentCategory: 'Other', tags: [], locationName: 'Bengaluru' });
    assert.equal(done.post_id, 11);
    assert.ok(JSON.stringify(seen[1]?.init.body).includes('Bengaluru'));
    nextPayload = { ok: true, post_id: 11, status: 'ALLOWED', stage: 'ALLOWED', moderation_status: 'ALLOWED' };
    const st = await fetchProcessingStatus('tok', 11);
    assert.equal(st.status, 'ALLOWED');
    nextPayload = { ok: true };
    assert.equal((await redriveProcessing('tok', 11)).ok, true);
    assert.ok(moderationCopy('blocked').length > 0);
  });

  it('chat pagination/dedupe/send/share + safe blocked copy', async () => {
    stub();
    nextStatus = 200;
    nextPayload = { ok: true, peer: { user_id: 9 }, messages: [{ child_message_id: 2 }, { child_message_id: 1 }] };
    const thread = await fetchChat('tok', 9, 30);
    assert.deepEqual(dedupeChat(thread.messages).map((m) => m.child_message_id), [1, 2]);
    nextPayload = { ok: true, status: 'ALLOWED' };
    assert.equal((await sendChatText('tok', 9, 'hello kindly')).status, 'ALLOWED');
    nextPayload = { ok: true, message_id: 5 };
    assert.equal((await sharePostToChat('tok', 9, 3)).message_id, 5);
    assert.equal(CHAT_BLOCKED_COPY, "That message couldn't be sent. Try saying it another way.");
    const g = createSearchGuard();
    const a = g.next();
    const b = g.next();
    assert.equal(g.isLatest(a), false);
    assert.equal(g.isLatest(b), true);
    assert.equal(shouldStopPolling('processing', { attempts: 30, maxAttempts: 30 }, true), true);
    assert.equal(shouldStopPolling('processing', { attempts: 1, maxAttempts: 30 }, false), true);
  });

  it('notifications mark-read + post detail hide internals', async () => {
    stub();
    nextStatus = 200;
    nextPayload = { ok: true, marked: 2 };
    const res = await markNotificationsRead('tok', [1, 2]);
    assert.equal(res.marked, 2);
    assert.ok(seen[0]?.url.endsWith('/api/mobile/v1/kids/notifications/read'));
    nextPayload = { ok: true, post: { post_id: 1, media_url: 'https://cdn/x.jpg' }, comments: [] };
    const d = await fetchPostDetail('tok', 1);
    assert.ok(!JSON.stringify(d).includes('quarantine'));
  });

  it('uses authoritative message capability and conversation unread state', () => {
    assert.equal(canMessageRelationship({ can_message: false }), false);
    assert.equal(canMessageRelationship({ can_message: true }), true);
    assert.equal(isConversationUnread({ peer_id: 9, last_message: { sender_child_id: 9, is_seen: false } }), true);
    assert.equal(isConversationUnread({ peer_id: 9, last_message: { sender_child_id: 7, is_seen: false } }), false);
    assert.equal(isConversationUnread({ peer_id: 9, last_message: { sender_child_id: 9, is_seen: true } }), false);
  });
});
