import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';

const root = process.cwd();

function text(relative: string): string {
  return fs.readFileSync(path.join(root, relative), 'utf8');
}

test('normal Feed has Quiz Zone but no compulsory marker lock', () => {
  const feed = text('src/screens/kids/FeedScreen.tsx');
  assert.match(feed, /Quiz Zone/);
  assert.match(feed, /Start Quiz/);
  assert.doesNotMatch(feed, /withQuizBreaks\(visibleItems/);
  assert.doesNotMatch(feed, /scrollEnabled=\{!quizLocked\}/);
});

test('Reels rely on server latch instead of local marker placement', () => {
  const reels = text('src/screens/kids/ReelsScreen.tsx');
  assert.match(reels, /const displayItems = feed\.items/);
  assert.doesNotMatch(reels, /withQuizBreaks\(feed\.items/);
  assert.match(reels, /if \(result\.quiz_required\)/);
  assert.match(reels, /error\.code === 'quiz_required'/);
  assert.match(reels, /scrollEnabled=\{!quizLocked\}/);
  assert.match(reels, /paused=\{paused \|\| quizLocked\}/);
});

test('meaningful Reel impression is flushed immediately, not in fixed batches of five', () => {
  const reels = text('src/screens/kids/ReelsScreen.tsx');
  assert.match(reels, /void flushBatch\(\);/);
  assert.doesNotMatch(reels, /impressionBatchRef\.current\.length >= 5/);
});

test('Reels stay locked until an authoritative quiz refresh clears the server latch', () => {
  const reels = text('src/screens/kids/ReelsScreen.tsx');
  assert.match(reels, /const refreshed = await refreshMe\(\);/);
  assert.match(reels, /const stillRequired = refreshed\.user\.quiz_required \|\| refreshed\.onboarding\?\.quiz_required/);
  assert.match(reels, /setQuizLocked\(Boolean\(stillRequired\)\)/);
  assert.doesNotMatch(reels, /setQuizLocked\(false\);\s*setPaused\(false\);\s*if \(session\?\.token\)/);
});
