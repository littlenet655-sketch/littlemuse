import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  isQuizPromptRow,
  QUIZ_PROMPT_KEY,
  quizPromptInsertAt,
  shouldShowQuizPrompt,
  withQuizPromptRow,
  type QuizPromptRow,
} from '../src/kids/quizPrompt';

describe('quiz prompt placement (non-blocking nudge)', () => {
  it('lands after the 2nd reel so the child sees content first', () => {
    assert.equal(quizPromptInsertAt(8), 2);
    assert.equal(quizPromptInsertAt(2), 2);
    assert.equal(quizPromptInsertAt(1), 1);
    assert.equal(quizPromptInsertAt(0), 0);
  });

  it('shows only when a quiz is due and the card was not dismissed', () => {
    assert.equal(shouldShowQuizPrompt(true, false), true);
    assert.equal(shouldShowQuizPrompt(true, true), false);
    assert.equal(shouldShowQuizPrompt(false, false), false);
    assert.equal(shouldShowQuizPrompt(false, true), false);
  });

  it('inserts exactly one prompt card after the 2nd reel', () => {
    const reels = ['r1', 'r2', 'r3', 'r4'];
    const rows = withQuizPromptRow(reels, true);
    assert.equal(rows.length, 5);
    assert.deepEqual(rows[0], 'r1');
    assert.deepEqual(rows[1], 'r2');
    assert.ok(isQuizPromptRow(rows[2]));
    assert.deepEqual(rows[3], 'r3');
    assert.deepEqual(rows[4], 'r4');
    const prompts = rows.filter(isQuizPromptRow);
    assert.equal(prompts.length, 1);
    assert.equal((prompts[0] as QuizPromptRow).key, QUIZ_PROMPT_KEY);
  });

  it('is idempotent: repeated calls never duplicate the card', () => {
    const rows = withQuizPromptRow(['r1', 'r2', 'r3'], true);
    const again = withQuizPromptRow(rows, true);
    assert.equal(again.filter(isQuizPromptRow).length, 1);
    assert.equal(again.length, 4);
  });

  it('never renders a card when no quiz is due', () => {
    const rows = withQuizPromptRow(['r1', 'r2'], false);
    assert.deepEqual(rows, ['r1', 'r2']);
    assert.ok(!rows.some(isQuizPromptRow));
  });

  it('dismissal removes the card while the reels stay intact', () => {
    const shown = withQuizPromptRow(['r1', 'r2', 'r3'], true);
    const hidden = withQuizPromptRow(shown, false);
    assert.deepEqual(hidden, ['r1', 'r2', 'r3']);
  });

  it('recognizes only the sentinel row, not real feed items', () => {
    assert.equal(isQuizPromptRow({ kind: 'quiz-prompt', key: 'quiz-prompt' }), true);
    assert.equal(isQuizPromptRow({ kind: 'reel', key: '1' }), false);
    assert.equal(isQuizPromptRow(null), false);
    assert.equal(isQuizPromptRow(undefined), false);
    assert.equal(isQuizPromptRow('quiz-prompt'), false);
  });
});
