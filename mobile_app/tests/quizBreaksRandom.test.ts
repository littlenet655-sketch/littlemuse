import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { isQuizMarker, withQuizBreaks, type QuizMarker } from '../src/kids/quizBreaks';

describe('quizBreaksRandom contract', () => {
  const reels = [
    { id: 1, title: 'Reel 1' },
    { id: 2, title: 'Reel 2' },
    { id: 3, title: 'Reel 3' },
    { id: 4, title: 'Reel 4' },
    { id: 5, title: 'Reel 5' },
    { id: 6, title: 'Reel 6' },
  ];

  it('inserts brain break every 2 reels when server interval is 2', () => {
    const result = withQuizBreaks(reels, 2);
    // [R1, R2, Quiz-2, R3, R4, Quiz-4, R5, R6, Quiz-6]
    assert.equal(result.length, 9);
    assert.equal(isQuizMarker(result[2]), true);
    assert.equal((result[2] as QuizMarker).markerId, 'quiz-2');
    assert.equal(isQuizMarker(result[5]), true);
    assert.equal((result[5] as QuizMarker).markerId, 'quiz-4');
    assert.equal(isQuizMarker(result[8]), true);
    assert.equal((result[8] as QuizMarker).markerId, 'quiz-6');
  });

  it('inserts brain break every 3 reels when server interval is 3', () => {
    const result = withQuizBreaks(reels, 3);
    // [R1, R2, R3, Quiz-3, R4, R5, R6, Quiz-6]
    assert.equal(result.length, 8);
    assert.equal(isQuizMarker(result[3]), true);
    assert.equal((result[3] as QuizMarker).markerId, 'quiz-3');
    assert.equal(isQuizMarker(result[7]), true);
    assert.equal((result[7] as QuizMarker).markerId, 'quiz-6');
  });

  it('inserts brain break every 4 reels when server interval is 4', () => {
    const result = withQuizBreaks(reels, 4);
    // [R1, R2, R3, R4, Quiz-4, R5, R6]
    assert.equal(result.length, 7);
    assert.equal(isQuizMarker(result[4]), true);
    assert.equal((result[4] as QuizMarker).markerId, 'quiz-4');
  });

  it('inserts brain break every 5 reels when server interval is 5', () => {
    const result = withQuizBreaks(reels, 5);
    // [R1, R2, R3, R4, R5, Quiz-5, R6]
    assert.equal(result.length, 7);
    assert.equal(isQuizMarker(result[5]), true);
    assert.equal((result[5] as QuizMarker).markerId, 'quiz-5');
  });

  it('returns items untouched for invalid or non-positive intervals', () => {
    const unchanged = withQuizBreaks(reels, 0);
    assert.equal(unchanged.length, reels.length);
    assert.deepEqual(unchanged, reels);
  });
});
