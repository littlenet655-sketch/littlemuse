import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const SRC = join(__dirname, '..', '..', 'src');
const source = (path: string) => readFileSync(join(SRC, path), 'utf-8');

describe('Parity Wave 3: native message replies and reactions', () => {
  it('keeps reply metadata instead of copying text into a new protocol', () => {
    const api = source('api/kidsChat.ts');
    const chat = source('screens/kids/ChatScreen.tsx');
    assert.match(api, /reply_to_message_id/);
    assert.match(api, /reply_message_text/);
    assert.match(api, /reactToMessage/);
    assert.match(chat, /const \[replyTo, setReplyTo\]/);
    assert.match(chat, /reply_to_message_id: replying\?\.child_message_id/);
    assert.match(chat, /Long press for reply and reactions/);
    assert.match(chat, /MESSAGE_REACTION_EMOJIS\.map/);
  });
});

describe('Parity Wave 3: moderated photo/video chat', () => {
  it('uploads binary directly to a signed URL and completes moderation server-side', () => {
    const api = source('api/kidsChat.ts');
    const chat = source('screens/kids/ChatScreen.tsx');
    assert.match(api, /requestChatUploadSession/);
    assert.match(api, /completeChatUpload/);
    assert.match(chat, /putFileToSignedUrl/);
    assert.match(chat, /Photos and videos are safety-checked before your friend can see them/);
    assert.match(chat, /result\.status === 'REVIEW'/);
    assert.match(chat, /Only you can see it for now/);
  });

  it('does not autoplay video in the message list', () => {
    const chat = source('screens/kids/ChatScreen.tsx');
    assert.match(chat, /Video message · tap to play/);
    assert.match(chat, /setVideoModalUri/);
    assert.match(chat, /<Modal[\s\S]*?videoModalUri/);
    assert.match(chat, /<VideoMedia source=\{videoModalUri\} active/);
    const mediaBubbleStart = chat.indexOf("m.message_type === 'VIDEO'");
    const modalStart = chat.indexOf('<Modal');
    assert.ok(mediaBubbleStart >= 0 && modalStart > mediaBubbleStart);
  });

  it('shows meaningful photo/video previews in the inbox', () => {
    const inbox = source('screens/kids/ConversationsScreen.tsx');
    assert.match(inbox, /kind === 'IMAGE' \? '📷 Photo'/);
    assert.match(inbox, /kind === 'VIDEO' \? '🎬 Video'/);
    assert.match(inbox, /kind === 'SHARED_POST' \? '↗ Shared post'/);
  });
});
