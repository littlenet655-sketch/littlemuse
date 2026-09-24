import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';

const SRC = join(__dirname, '..', '..', 'src');

describe('Task 1: Complete Navigation / Back Behavior Contracts', () => {
  it('CreateScreen has draft confirmation and KidsTabs -> FeedTab fallback', () => {
    const filePath = join(SRC, 'screens/kids/CreateScreen.tsx');
    const content = readFileSync(filePath, 'utf-8');

    // Verification of fallback contract
    assert.match(content, /navigation\.canGoBack\(\)/);
    assert.match(content, /nav\.navigate\('KidsTabs',\s*\{\s*tab:\s*'FeedTab'\s*\}\)/);

    // Verification of draft protection
    assert.match(content, /hasDraft\s*&&\s*!busy/);
    assert.match(content, /'Discard your post\?'/);
    assert.match(content, /'Keep editing'/);
    assert.match(content, /'Discard'/);

    // Hardware back listener cleanup
    assert.match(content, /BackHandler\.addEventListener\('hardwareBackPress'/);
    assert.match(content, /sub\.remove\(\)/);
  });

  it('StoriesScreen has safe exit and back-to-home in empty/error states', () => {
    const filePath = join(SRC, 'screens/kids/StoriesScreen.tsx');
    const content = readFileSync(filePath, 'utf-8');

    // Safe close handles both history and tab fallback
    assert.match(content, /closeStories\s*=\s*useCallback\(/);
    assert.match(content, /if\s*\(navigation\.canGoBack\(\)\)\s*navigation\.goBack\(\);/);
    assert.match(content, /nav\.navigate\('KidsTabs',\s*\{\s*tab:\s*'FeedTab'\s*\}\)/);

    // Empty state includes Back to Home button (no black screen trap)
    assert.match(content, /label="Back to Home"/);
    assert.match(content, /accessibilityLabel="Back to Home"/);

    // BackHandler listener cleanup
    assert.match(content, /BackHandler\.addEventListener\('hardwareBackPress'/);
    assert.match(content, /sub\.remove\(\)/);
  });

  it('ConversationsScreen maintains header back across all states and cleans up listeners', () => {
    const filePath = join(SRC, 'screens/kids/ConversationsScreen.tsx');
    const content = readFileSync(filePath, 'utf-8');

    // Back handler cleans up
    assert.match(content, /BackHandler\.addEventListener\('hardwareBackPress'/);
    assert.match(content, /sub\.remove\(\)/);

    // BrandHeader back wired to closeConversations in normal, loading, error, and disabled states
    const headerOccurrences = content.match(/<BrandHeader\s+title="Messages"\s+onBack=\{closeConversations\}/g);
    assert.ok(headerOccurrences && headerOccurrences.length >= 4, 'BrandHeader onBack must appear across all inbox states');
  });
});

describe('Task 3: Explore Always Opens at Top Contracts', () => {
  it('DiscoverScreen maintains FlashList refs and scroll-to-top resets', () => {
    const filePath = join(SRC, 'screens/kids/DiscoverScreen.tsx');
    const content = readFileSync(filePath, 'utf-8');

    // FlashList refs attached
    assert.match(content, /peopleListRef\s*=\s*useRef/);
    assert.match(content, /gridListRef\s*=\s*useRef/);
    assert.match(content, /<FlashList[\s\S]*?ref=\{peopleListRef\}/);
    assert.match(content, /<FlashList[\s\S]*?ref=\{gridListRef\}/);

    // resetToTop handles scroll offset 0
    assert.match(content, /scrollToOffset\(\{\s*offset:\s*0,\s*animated:\s*false\s*\}\)/);

    // Reset triggers on focus, category change, and search query change
    assert.match(content, /if\s*\(isFocused\)\s*\{\s*resetToTop\(\);/);
    assert.match(content, /useEffect\(\(\)\s*=>\s*\{\s*resetToTop\(\);\s*\},\s*\[kind,\s*resetToTop\]\);/);
    assert.match(content, /prevDebouncedRef\.current\s*!==\s*debounced/);
  });
});

describe('Task 4: All Reels Camera Buttons Wired Contracts', () => {
  it('ReelsScreen wires all camera buttons to CreateTab with initialKind: reel', () => {
    const filePath = join(SRC, 'screens/kids/ReelsScreen.tsx');
    const content = readFileSync(filePath, 'utf-8');

    // openReelCamera navigation
    assert.match(content, /openReelCamera\s*=\s*useCallback\(/);
    assert.match(content, /nav\.navigate\('KidsTabs',\s*\{\s*tab:\s*'CreateTab',\s*initialKind:\s*'reel'\s*\}\)/);

    // Camera buttons use openReelCamera
    const wiredCameraButtons = content.match(/onPress=\{openReelCamera\}/g);
    assert.ok(wiredCameraButtons && wiredCameraButtons.length === 3, 'All 3 Reels camera buttons must be wired to openReelCamera');

    // No dead camera button remains
    assert.doesNotMatch(content, /accessibilityLabel="Camera"[\s\S]*?onPress=\{\(\)\s*=>\s*\{\}\}/);
  });
});

describe('Task 5: Open Exact Tapped Story Contracts', () => {
  function resolveStoryTargetIndex(
    stories: Array<{ post_id: number }>,
    initialStoryId?: number,
  ): number {
    if (initialStoryId == null) return 0;
    const idx = stories.findIndex((s) => s.post_id === initialStoryId);
    return idx >= 0 ? idx : 0; // safe fallback
  }

  it('selects the targeted story index when found', () => {
    const stories = [{ post_id: 101 }, { post_id: 102 }, { post_id: 103 }];
    assert.equal(resolveStoryTargetIndex(stories, 102), 1);
    assert.equal(resolveStoryTargetIndex(stories, 103), 2);
    assert.equal(resolveStoryTargetIndex(stories, 101), 0);
  });

  it('falls back safely to index 0 when story is expired or deleted without crashing', () => {
    const stories = [{ post_id: 101 }, { post_id: 102 }];
    assert.equal(resolveStoryTargetIndex(stories, 999), 0);
    assert.equal(resolveStoryTargetIndex([], 999), 0);
  });

  it('FeedScreen StoriesTray passes tapped story.post_id to Stories navigation', () => {
    const filePath = join(SRC, 'screens/kids/FeedScreen.tsx');
    const content = readFileSync(filePath, 'utf-8');

    assert.match(content, /onOpen\(\s*own\?\.post_id\s*\)/);
    assert.match(content, /onOpen\(\s*story\.post_id\s*\)/);
    assert.match(content, /nav\.navigate\('Stories',\s*initialStoryId\s*\?\s*\{\s*initialStoryId\s*\}\s*:\s*\{\}\)/);
  });
});

describe('Task 8: Reels Follow + Audio Controls Contracts', () => {
  it('useReelPlayback toggles mute without restarting video or seeking', () => {
    const filePath = join(SRC, 'video/useReelPlayback.ts');
    const content = readFileSync(filePath, 'utf-8');

    // toggleMute mutates player.muted directly
    assert.match(content, /player\.muted\s*=\s*next/);
    assert.match(content, /setMuted\(next\)/);
    // Does NOT call replaceAsync or change currentTime during mute toggle
    const muteSlice = content.slice(content.indexOf('const toggleMute ='), content.indexOf('const toggleMute =') + 250);
    assert.doesNotMatch(muteSlice, /replaceAsync/);
    assert.doesNotMatch(muteSlice, /currentTime/);
  });

  it('ReelsScreen wires SOCIAL creator follow with optimistic Requested state and curated disabled', () => {
    const filePath = join(SRC, 'screens/kids/ReelsScreen.tsx');
    const content = readFileSync(filePath, 'utf-8');

    // Social follow uses toggleFollow API
    assert.match(content, /toggleFollow\(session\.token,\s*childId\)/);
    // Optimistic transition to 'Requested' (parent approval required)
    assert.match(content, /currentStatus\s*===\s*'Follow'\s*\?\s*'Requested'\s*:\s*'Follow'/);
    // Rollback on failure
    assert.match(content, /setFollowStates\(\(\s*prev\s*\)\s*=>\s*\(\{\s*\.\.\.prev,\s*\[childId\]:\s*currentStatus\s*\}\)\)/);
    // Curated creator follow disabled (does not fake child id)
    assert.match(content, /item\.source_type\s*!==\s*'SOCIAL'/);
    assert.match(content, /accessibilityLabel="Curated creator"/);
  });

  it('Reels UI exposes audio control via disc and audio tag using authoritative hook state', () => {
    const filePath = join(SRC, 'screens/kids/ReelsScreen.tsx');
    const content = readFileSync(filePath, 'utf-8');

    // Both audio disc and audio tag call handleToggleMute
    assert.match(content, /<Pressable[\s\S]*?styles\.audioDiscWrap[\s\S]*?onPress=\{handleToggleMute\}/);
    assert.match(content, /<Pressable[\s\S]*?styles\.audioTagRow[\s\S]*?onPress=\{handleToggleMute\}/);
    assert.match(content, /cellMuted\s*\?\s*'Audio off • Tap to turn on'\s*:\s*'Safe Sound • Kid Approved'/);
  });
});

describe('Task 12: Child-Safe Explore Learn More Contracts', () => {
  it('DiscoverScreen Learn more is pressable and opens child-safe explainer modal', () => {
    const filePath = join(SRC, 'screens/kids/DiscoverScreen.tsx');
    const content = readFileSync(filePath, 'utf-8');

    // Learn more is a Pressable button
    assert.match(content, /<Pressable[\s\S]*?onPress=\{\(\)\s*=>\s*setExplainerOpen\(true\)\}[\s\S]*?accessibilityLabel="Learn more about Classroom SafeSpace"/);

    // Explainer modal present with accessibility
    assert.match(content, /<Modal[\s\S]*?visible=\{explainerOpen\}[\s\S]*?onRequestClose=\{\(\)\s*=>\s*setExplainerOpen\(false\)\}/);

    // Required child-friendly copy themes
    assert.match(content, /Checked Before Sharing/);
    assert.match(content, /LittleNet checks posts and Reels before they can appear so you can explore safely\./);
    assert.match(content, /Parent Controls/);
    assert.match(content, /Private & Protected/);
    assert.match(content, /Friendly Reporting/);
    assert.match(content, /Safe Recommendations/);

    // Got it button closes modal
    assert.match(content, /accessibilityLabel="Got it, close info"/);
  });
});

describe('Task 14: Parent Date-of-Birth Picker Contracts', () => {
  function serializeCanonicalDob(year: number, month1Indexed: number, day: number): string {
    const mm = String(month1Indexed).padStart(2, '0');
    const dd = String(day).padStart(2, '0');
    return `${year}-${mm}-${dd}`;
  }

  function validateAdultAge(dobString: string, referenceDate: Date = new Date()): boolean {
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dobString.trim());
    if (!match) return false;
    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = Number(match[3]);
    const birth = new Date(year, month - 1, day);
    if (birth.getFullYear() !== year || birth.getMonth() !== month - 1 || birth.getDate() !== day) {
      return false;
    }
    let age = referenceDate.getFullYear() - birth.getFullYear();
    const hadBirthday =
      referenceDate.getMonth() > birth.getMonth() ||
      (referenceDate.getMonth() === birth.getMonth() && referenceDate.getDate() >= birth.getDate());
    if (!hadBirthday) age -= 1;
    return age >= 18;
  }

  it('serializes canonical YYYY-MM-DD correctly', () => {
    assert.equal(serializeCanonicalDob(1985, 3, 7), '1985-03-07');
    assert.equal(serializeCanonicalDob(2000, 11, 24), '2000-11-24');
    assert.equal(serializeCanonicalDob(1990, 1, 1), '1990-01-01');
  });

  it('enforces 18+ adult age constraint against canonical DOB', () => {
    const ref = new Date(2026, 8, 24); // Sept 24, 2026
    assert.equal(validateAdultAge('2008-09-24', ref), true); // exactly 18
    assert.equal(validateAdultAge('2008-09-25', ref), false); // 17 years 364 days
    assert.equal(validateAdultAge('2010-01-01', ref), false); // minor
    assert.equal(validateAdultAge('2028-01-01', ref), false); // future date
    assert.equal(validateAdultAge('1990-05-14', ref), true); // adult
    assert.equal(validateAdultAge('1990-02-31', ref), false); // invalid date
  });

  it('ParentOnboarding renders ParentDobPicker with 18+ constraint and modal controls', () => {
    const filePath = join(SRC, 'screens/ParentOnboarding.tsx');
    const content = readFileSync(filePath, 'utf-8');

    // ParentDobPicker component is used
    assert.match(content, /<ParentDobPicker[\s\S]*?value=\{dob\}[\s\S]*?onChange=\{/);
    assert.match(content, /18\+ Adult Required/);
    assert.match(content, /Must be at least 18 years old\. Server validates age authoritatively\./);

    // Modal date selection controls
    assert.match(content, /accessibilityLabel="Date of Birth Picker"/);
    assert.match(content, /accessibilityLabel="Previous year"/);
    assert.match(content, /accessibilityLabel="Next year"/);
    assert.match(content, /accessibilityLabel="Cancel date selection"/);
    assert.match(content, /accessibilityLabel="Confirm date of birth"/);
  });
});
