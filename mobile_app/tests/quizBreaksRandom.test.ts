import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';

const root = process.cwd();

function text(relative: string): string {
  return fs.readFileSync(path.join(root, relative), 'utf8');
}

test('Learn tab exposes an optional Quiz Zone without creating a feed gate', () => {
  const feed = text('src/screens/kids/FeedScreen.tsx');
  assert.match(feed, /QuizPromoCard/);
  assert.match(feed, /tab === 'Learn'/);
  assert.match(feed, /openQuiz/);
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
  // The due signal becomes a compulsory Reel interruption.
  assert.doesNotMatch(reels, /scrollEnabled=\{!quizLocked\}/);
  assert.doesNotMatch(reels, /QuizBreakCard/);
  assert.match(reels, /QuizPromptCard/);
  assert.doesNotMatch(reels, /onDismiss=/);
  assert.match(reels, /setPaused\(true\)/);
  assert.match(reels, /nav\.navigate\('Quiz', \{ returnTo: 'ReelsTab', autoStart: true \}\)/);
});

test('meaningful Reel impression is flushed immediately, not in fixed batches of five', () => {
  const reels = text('src/screens/kids/ReelsScreen.tsx');
  assert.match(reels, /void flushBatch\(\);/);
  assert.doesNotMatch(reels, /impressionBatchRef\.current\.length >= 5/);
});


test('Quiz Zone practice mode cannot consume the compulsory Reel latch', () => {
  const quiz = text('src/screens/Quiz.tsx');
  const api = text('src/api/auth.ts');
  assert.match(quiz, /practiceMode/);
  assert.match(quiz, /fetchQuiz\(session\.token, undefined, practiceMode \? 'practice' : undefined\)/);
  assert.match(quiz, /answerQuiz\(session\.token, current\.quiz_id, option, practiceMode \? 'practice' : undefined\)/);
  assert.match(api, /mode\?: 'practice'/);
});
