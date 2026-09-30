import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import { quizAnswerAction } from '../src/quiz/decision';

test('practice advances every answer and refills after five, independently of Reel latch', () => {
  for (const required of [false, true]) {
    for (const correct of [false, true]) {
      assert.deepEqual(Array.from({ length: 5 }, (_, i) => quizAnswerAction(true, correct, required, i === 4)),
        ['next', 'next', 'next', 'next', 'refill']);
    }
  }
  assert.equal(quizAnswerAction(false, false, true, true), 'retry');
  // End of a required batch asks for authoritative confirmation; refresh still
  // refuses navigation while the server latch is true (quiz decision suite).
  assert.equal(quizAnswerAction(false, true, true, true), 'complete');
  assert.equal(quizAnswerAction(false, true, true, false), 'next');
  assert.equal(quizAnswerAction(false, true, false, true), 'complete');
});

test('Reel completion pops the quiz and keeps the underlying Reel list stable', () => {
  const quiz = readFileSync('src/screens/Quiz.tsx', 'utf8');
  const reels = readFileSync('src/screens/kids/ReelsScreen.tsx', 'utf8');
  assert.match(quiz, /params.returnTo === 'ReelsTab' && navigation.canGoBack\(\)\) navigation.goBack\(\)/);
  assert.match(reels, /\(\) => feed.items/);
  assert.match(reels, /setPaused\(false\)/);
});

test('processing reconciles on foreground and invalidates authoritative terminal outcomes', () => {
  const source = readFileSync('src/kids/useProcessing.ts', 'utf8');
  assert.match(source, /if \(!active \|\| !postId\) return/);
  assert.match(source, /if \(terminal\) void fetchOnce\(\)/);
  assert.match(source, /invalidateSocialCaches\(\[postId\]\)/);
  assert.match(readFileSync('src/query/client.tsx', 'utf8'), /refetchOnWindowFocus: 'always'/);
});

test('Create retains photo and video with two primary media sources', () => {
  const source = readFileSync('src/screens/kids/CreateScreen.tsx', 'utf8');
  assert.match(source, /pickGalleryMedia\(allowVideoForPost \? 'all'/);
  assert.match(source, /capturePostMedia\('image'\)/);
  assert.match(source, /capturePostMedia\('video', maxVideoDurationFor\(kind\)\)/);
});
