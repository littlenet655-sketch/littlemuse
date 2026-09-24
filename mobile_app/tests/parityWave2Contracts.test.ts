import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const SRC = join(__dirname, '..', '..', 'src');

function source(path: string): string {
  return readFileSync(join(SRC, path), 'utf-8');
}

describe('Parity Wave 2: durable Create drafts and fail-closed category policy', () => {
  it('persists separate post/story/reel drafts and clears them after publishing', () => {
    const create = source('screens/kids/CreateScreen.tsx');
    const drafts = source('kids/createDrafts.ts');
    assert.match(drafts, /littlemuse:create-draft:v1:/);
    assert.match(drafts, /loadCreateDraft/);
    assert.match(drafts, /saveCreateDraft/);
    assert.match(drafts, /clearCreateDraft/);
    assert.match(create, /loadCreateDraft\(draftUserId, kind\)/);
    assert.match(create, /saveCreateDraft\(draftUserId/);
    assert.match(create, /await clearCreateDraft\(draftUserId, kind\)/);
    assert.match(create, /Save & close/);
  });

  it('does not invent Other when parent category policy is explicitly empty', () => {
    const create = source('screens/kids/CreateScreen.tsx');
    assert.match(create, /if \(!Array\.isArray\(source\)\) return \[\]/);
    assert.match(create, /const canPublishCategory = categoryPolicyReady && allowedCategories\.length > 0/);
    assert.match(create, /Posting is paused until your parent allows at least one content category/);
    assert.doesNotMatch(create, /return clean\.length > 0 \? clean : \['Other'\]/);
  });
});

describe('Parity Wave 2: curated Story music', () => {
  it('uses the existing approved music route and persists only catalog IDs', () => {
    const client = source('api/client.ts');
    const upload = source('api/kidsUpload.ts');
    const create = source('screens/kids/CreateScreen.tsx');
    assert.match(client, /curatedMusic: '\/api\/mobile\/v1\/music\/curated'/);
    assert.match(upload, /fetchCuratedMusic/);
    assert.match(upload, /music_id: input\.musicId \?\? null/);
    assert.match(create, /pre-approved royalty-free tracks/);
    assert.match(create, /musicId: kind === 'story' \? storyMusicId : null/);
    assert.match(create, /<StoryMusicPreview/);
  });

  it('plays stored Story music and mutes original story video when music exists', () => {
    const stories = source('screens/kids/StoriesScreen.tsx');
    assert.match(stories, /function StoryMusicPlayback/);
    assert.match(stories, /instance\.audioMixingMode = 'duckOthers'/);
    assert.match(stories, /muted=\{Boolean\(current\.story_music\?\.audio_url\)\}/);
    assert.match(stories, /current\.story_music\.title/);
  });
});

describe('Parity Wave 2: Story interactions remain inside the safe social graph', () => {
  it('wires only allowlisted reactions and moderated replies', () => {
    const feed = source('api/kidsFeed.ts');
    const stories = source('screens/kids/StoriesScreen.tsx');
    assert.match(feed, /STORY_REACTION_EMOJIS/);
    assert.match(feed, /reactToStory/);
    assert.match(feed, /replyToStory/);
    assert.match(stories, /sendStoryReaction/);
    assert.match(stories, /sendStoryReply/);
    assert.match(stories, /Reply sent for safety review/);
  });
});
