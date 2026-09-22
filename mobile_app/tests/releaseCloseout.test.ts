/// <reference types="node" />
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

function source(path: string): string {
  return readFileSync(path, 'utf8');
}

describe('final release close-out contracts', () => {
  it('shows explicit child, parent and moderator/admin entry roles', () => {
    const s = source('src/screens/WelcomeLogin.tsx');
    assert.ok(s.includes("label: 'Kids Mode'"));
    assert.ok(s.includes("label: 'Parent Mode'"));
    assert.ok(s.includes("label: 'Admin'"));
    assert.ok(s.includes("navigation.navigate('Login', { mode: item.value })"));
  });

  it('renders six OTP cells backed by one hidden numeric input', () => {
    const s = source('src/screens/ParentOnboarding.tsx');
    assert.ok(s.includes('Array.from({ length: 6 }'));
    assert.ok(s.includes('styles.otpCellActive'));
    assert.ok(s.includes('styles.otpHiddenInput'));
    assert.ok(s.includes("value.replace(/\\D/g, '').slice(0, 6)"));
  });

  it('opens Story creation directly in story mode', () => {
    const stories = source('src/screens/kids/StoriesScreen.tsx');
    const create = source('src/screens/kids/CreateScreen.tsx');
    assert.ok(stories.includes("navigation.navigate('CreateTab', { kind: 'story' })"));
    assert.ok(create.includes("route.params?.kind ?? 'post'"));
  });

  it('exposes owner delete actions for posts and stories', () => {
    const posts = source('src/screens/kids/PostDetailScreen.tsx');
    const stories = source('src/screens/kids/StoriesScreen.tsx');
    assert.ok(posts.includes("deletePost(session.token, postId)"));
    assert.ok(posts.includes('Delete post'));
    assert.ok(stories.includes('deleteStory(session.token, storyId)'));
    assert.ok(stories.includes('Delete story'));
  });

  it('renders parent viewing insights and private video review playback', () => {
    const s = source('src/screens/parent/ParentScreens.tsx');
    assert.ok(s.includes('Activity & Viewing Insights'));
    assert.ok(s.includes('reels_watched_7d'));
    assert.ok(s.includes('ReviewVideo'));
    assert.ok(s.includes('nativeControls'));
  });
});
