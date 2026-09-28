import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';

const root = process.cwd();

function text(relative: string): string {
  return fs.readFileSync(path.join(root, relative), 'utf8');
}

test('Learn tab has no pinned Quiz Zone card (quizzes surface randomly between reels)', () => {
  const feed = text('src/screens/kids/FeedScreen.tsx');
  assert.doesNotMatch(feed, /Quiz Zone/);
  assert.doesNotMatch(feed, /QuizZoneCard/);
  assert.doesNotMatch(feed, /onStartQuizZone/);
  assert.doesNotMatch(feed, /withQuizBreaks\(visibleItems/);
  assert.doesNotMatch(feed, /scrollEnabled=\{!quizLocked\}/);
});

test('Reels rely on server latch instead of local marker placement', () => {
  const reels = text('src/screens/kids/ReelsScreen.tsx');
  // The prompt card position comes from a pure helper driven by the server's
  // quiz_due signal — never from locally counted markers.
  assert.match(reels, /withQuizPromptRow\(feed\.items, showQuizPrompt\)/);
  assert.doesNotMatch(reels, /withQuizBreaks\(feed\.items/);
  assert.match(reels, /if \(result\.quiz_required\)/);
  assert.match(reels, /error\.code === 'quiz_required'/);
  // Non-blocking: no scroll lock, no forced pause, no full-screen lock card.
  assert.doesNotMatch(reels, /scrollEnabled=\{!quizLocked\}/);
  assert.doesNotMatch(reels, /paused=\{paused \|\| quizLocked\}/);
  assert.doesNotMatch(reels, /QuizBreakCard/);
  // The nudge: one dismissible inline card; tapping opens Quiz voluntarily.
  assert.match(reels, /QuizPromptCard/);
  assert.match(reels, /onDismiss=\{\(\) => setQuizPromptDismissed\(true\)\}/);
  assert.match(reels, /onTakeQuiz=\{\(\) => nav\.navigate\('Quiz', \{\}\)\}/);
});

test('meaningful Reel impression is flushed immediately, not in fixed batches of five', () => {
  const reels = text('src/screens/kids/ReelsScreen.tsx');
  assert.match(reels, /void flushBatch\(\);/);
  assert.doesNotMatch(reels, /impressionBatchRef\.current\.length >= 5/);
});
