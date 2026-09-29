import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';

const root = process.cwd();
const text = (relative: string) => fs.readFileSync(path.join(root, relative), 'utf8');

test('inactive child screens do not schedule navigation resets', () => {
  const navigator = text('src/navigation/RootNavigator.tsx');
  assert.match(navigator, /const focused = useIsFocused\(\)/);
  assert.match(navigator, /if \(!focused\) return/);
  assert.match(navigator, /\[focused, navigation, session\?\.onboarding, session\?\.user\.quiz_required\]/);
});

test('feed image sizing avoids redundant fetch and prefetch requests', () => {
  const postCard = text('src/kids/PostCard.tsx');
  assert.match(postCard, /if \(!uri \|\| hintRatio != null\) return/);
  assert.doesNotMatch(postCard, /Image\.prefetch/);
});

test('new upload invalidates the cached profile before leaving the composer', () => {
  const create = text('src/screens/kids/CreateScreen.tsx');
  assert.match(create, /invalidateSocialCaches\(\[done\.post_id\]\)/);
});

test('own and friend profile media grids are virtualized', () => {
  for (const screen of ['OwnProfileScreen.tsx', 'OtherProfileScreen.tsx']) {
    const source = text(`src/screens/kids/${screen}`);
    assert.match(source, /<FlashList/);
    assert.match(source, /numColumns=\{GRID_COLS\}/);
    assert.match(source, /drawDistance=\{600\}/);
    assert.doesNotMatch(source, /posts\.map\(\(/);
  }
});

test('People search has its own empty state even when other tabs have results', () => {
  const discover = text('src/screens/kids/DiscoverScreen.tsx');
  assert.match(discover, /const hasContentForKind =/);
  assert.match(discover, /kind === 'People'\s*\?\s*kids\.length > 0/);
  assert.match(discover, /No match in your approved friend circle/);
  assert.doesNotMatch(discover, /hasAnyContent/);
});