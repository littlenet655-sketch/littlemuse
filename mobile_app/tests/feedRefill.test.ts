import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';

const root = process.cwd();
const text = (relative: string) => fs.readFileSync(path.join(root, relative), 'utf8');

test('useFeed rotates into a refill session after an exhausted materialized session', () => {
  const hook = text('src/kids/useFeed.ts');
  assert.match(hook, /last\.can_refill/);
  assert.match(hook, /refillFrom: last\.session_id/);
  assert.match(hook, /pageParam\.refillFrom/);
});

test('Feed impressions preserve the session that authorized each item', () => {
  const feed = text('src/screens/kids/FeedScreen.tsx');
  const types = text('src/api/kidsFeed.ts');
  assert.match(types, /feed_session_id\?: string/);
  assert.match(feed, /item\.feed_session_id \?\? feed\.sessionId/);
});

test('Feed coalesces visible impressions and relies on one pagination trigger', () => {
  const feed = text('src/screens/kids/FeedScreen.tsx');
  assert.match(feed, /recordImpressionBatch/);
  assert.doesNotMatch(feed, /recordFeedImpression/);
  assert.match(feed, /pendingImpressionsRef\.current\.size >= 20/);
  assert.match(feed, /onEndReached=\{feed\.loadMore\}/);
  assert.doesNotMatch(feed, /furthest >= 0 && furthest >= feed\.items\.length/);
  assert.match(feed, /drawDistance=\{600\}/);
});

test('Reel metrics preserve per-item session identity across refill sessions', () => {
  const metrics = text('src/video/reelPlaybackMetrics.ts');
  assert.match(metrics, /sessionId \?\? this\.item\.feed_session_id/);
});
