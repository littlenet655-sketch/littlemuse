import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(__dirname, '..');

function text(relative: string): string {
  return fs.readFileSync(path.join(root, relative), 'utf8');
}

describe('server-authoritative random Reel brain break', () => {
  test('normal Feed has Quiz Zone but no compulsory marker lock', () => {
    const feed = text('src/screens/kids/FeedScreen.tsx');
    expect(feed).toContain('Quiz Zone');
    expect(feed).toContain('Start Quiz');
    expect(feed).not.toContain('withQuizBreaks(visibleItems');
    expect(feed).not.toContain('scrollEnabled={!quizLocked}');
  });

  test('Reels rely on server latch instead of local marker placement', () => {
    const reels = text('src/screens/kids/ReelsScreen.tsx');
    expect(reels).toContain('const displayItems = feed.items');
    expect(reels).not.toContain('withQuizBreaks(feed.items');
    expect(reels).toContain('if (result.quiz_required)');
    expect(reels).toContain("error.code === 'quiz_required'");
    expect(reels).toContain('scrollEnabled={!quizLocked}');
    expect(reels).toContain('paused={paused || quizLocked}');
  });

  test('meaningful Reel impression is flushed immediately, not in fixed batches of five', () => {
    const reels = text('src/screens/kids/ReelsScreen.tsx');
    expect(reels).toContain('void flushBatch();');
    expect(reels).not.toContain('impressionBatchRef.current.length >= 5');
  });
});
