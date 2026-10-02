import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';
import { quizAnswerAction } from '../src/quiz/decision';

const source = readFileSync('src/video/useReelPlayback.ts', 'utf8');
const file = ts.createSourceFile('useReelPlayback.ts', source, ts.ScriptTarget.Latest, true);

function find(predicate: (node: ts.Node) => boolean): ts.Node {
  let found: ts.Node | undefined;
  function visit(node: ts.Node) {
    if (predicate(node)) found = node;
    else ts.forEachChild(node, visit);
  }
  visit(file);
  assert.ok(found);
  return found;
}

function callback(name: string): ts.Node {
  const declaration = find(n => ts.isVariableDeclaration(n) && n.name.getText(file) === name) as ts.VariableDeclaration;
  const initializer = declaration.initializer as ts.CallExpression;
  assert.ok(initializer.arguments[0]);
  return initializer.arguments[0];
}

function run(node: ts.Node, context: Record<string, unknown>) {
  const javascript = ts.transpileModule(`(${node.getText(file)})`, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  }).outputText;
  return vm.runInNewContext(javascript, context)();
}

const watchdog = find(n => ts.isCallExpression(n) && n.expression.getText(file) === 'useEffect'
  && Boolean(n.arguments[0]?.getText(file).includes("onError('first_frame_timeout')"))) as ts.CallExpression;

test('first-frame budget starts after signing and skips paused/offscreen/ready/error states', () => {
  for (const overrides of [{ currentSource: null }, { paused: true }, { active: false },
    { nearby: false }, { firstFrameRendered: true }, { errorMessage: 'load failed' }, {}]) {
    const timers: Array<{ fn: () => void; ms: number }> = [];
    const errors: string[] = [];
    let cleared = false;
    const context = {
      active: true, nearby: true, paused: false, currentSource: 'https://storage.test/signed.mp4',
      firstFrameRendered: false, errorMessage: null, isMountedRef: { current: true },
      FIRST_FRAME_TIMEOUT_MS: 10000, ...overrides,
      setTimeout: (fn: () => void, ms: number) => { timers.push({ fn, ms }); return 1; },
      clearTimeout: () => { cleared = true; },
      setIsDebouncedBuffering: () => {}, setShowPreparing: () => {}, setPlaybackState: () => {},
      metricsRef: { current: { onError: (error: string) => errors.push(error) } },
      setErrorMessage: () => {},
    };
    const cleanup = run(watchdog.arguments[0]!, context);
    if (Object.keys(overrides).length) assert.equal(timers.length, 0);
    else {
      assert.equal(timers[0]?.ms, 10000);
      timers[0]!.fn();
      assert.deepEqual(errors, ['first_frame_timeout']);
      cleanup();
      assert.equal(cleared, true);
    }
  }
  const dependencies = watchdog.arguments[1]!.getText(file);
  for (const dependency of ['currentSource', 'paused', 'nearby']) assert.ok(dependencies.includes(dependency));
});

test('native first frame clears poster/loading/error and retry reloads existing source', async () => {
  const updates: unknown[] = [];
  run(callback('handleFirstFrameRender'), {
    setFirstFrameRendered: (value: boolean) => updates.push(value),
    setShowPreparing: (value: boolean) => updates.push(value),
    metricsRef: { current: { onFirstFrame: () => updates.push('first-frame') } },
    setErrorMessage: (value: unknown) => updates.push(value),
  });
  assert.deepEqual(updates, [true, false, 'first-frame', null]);
  const replaced: string[] = [];
  let played = false;
  await run(callback('retry'), {
    errorRefreshAttemptsRef: { current: 3 }, token: undefined,
    setErrorMessage: () => {}, setFirstFrameRendered: () => {}, setShowPreparing: () => {}, setPlaybackState: () => {},
    currentSource: 'https://storage.test/signed.mp4', active: true, paused: false,
    player: { replaceAsync: async (url: string) => replaced.push(url), play: () => { played = true; } },
  });
  assert.deepEqual(replaced, ['https://storage.test/signed.mp4']);
  assert.equal(played, true);
});

test('curated and social playback resolve their own signed source endpoints', async () => {
  const declaration = find(n => ts.isFunctionDeclaration(n) && n.name?.text === 'fetchPlayback');
  const javascript = ts.transpileModule(`${declaration.getText(file)}; fetchPlayback`, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  }).outputText;
  const calls: number[] = [];
  const fetchPlayback = vm.runInNewContext(javascript, {
    refreshCuratedReelPlayback: async (_token: string, id: number) => { calls.push(id); return { playback_url: 'curated-signed' }; },
    refreshReelPlayback: async (_token: string, id: number) => { calls.push(id); return { playback_url: 'social-signed' }; },
  });
  assert.equal((await fetchPlayback({ source_type: 'CURATED', source_id: 2 }, 'test-token')).playback_url, 'curated-signed');
  assert.equal((await fetchPlayback({ source_type: 'SOCIAL', source_id: 3, post_id: 9 }, 'test-token')).playback_url, 'social-signed');
  assert.deepEqual(calls, [2, 9]);
});

test('Brain Break keeps wrong answers locked and pops correct completion onto the retained Reel list', () => {
  assert.equal(quizAnswerAction(false, false, true, true), 'retry');
  assert.equal(quizAnswerAction(false, true, false, true), 'complete');
  const quiz = readFileSync('src/screens/Quiz.tsx', 'utf8');
  const reels = readFileSync('src/screens/kids/ReelsScreen.tsx', 'utf8');
  assert.match(quiz, /params.returnTo === 'ReelsTab' && navigation.canGoBack\(\)\) navigation.goBack\(\)/);
  assert.match(reels, /\(\) => feed.items/);
  assert.match(reels, /if \(!focused\)[\s\S]*quizNavigationRef.current = false/);
  assert.doesNotMatch(reels, /scrollTo(?:Index|Offset)\(\{[^}]*0/);
});

test('session refreshes reuse gated screen identities so Reel position and quiz loading survive', () => {
  const navigation = readFileSync('src/navigation/RootNavigator.tsx', 'utf8');
  const navigationFile = ts.createSourceFile('RootNavigator.tsx', navigation, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const wrapper = navigationFile.statements.find(n => ts.isFunctionDeclaration(n) && n.name?.text === 'withGateSync');
  assert.ok(wrapper);
  const javascript = ts.transpileModule(`${wrapper.getText(navigationFile)}; withGateSync`, {
    compilerOptions: { target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.React },
  }).outputText;
  const withGateSync = vm.runInNewContext(javascript, { gatedScreens: new WeakMap() });
  const reels = () => null;
  const quiz = () => null;
  assert.equal(withGateSync(reels), withGateSync(reels));
  assert.equal(withGateSync(quiz), withGateSync(quiz));
  assert.notEqual(withGateSync(reels), withGateSync(quiz));
});
