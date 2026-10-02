/**
 * Component behavior tests for src/components/ParentModeGate.tsx.
 *
 * Named *.test.ts (not *.test.tsx) because tsconfig.tests.json only includes
 * `tests/**\/*.ts`; the component itself is compiled from
 * src/components/ParentModeGate.tsx into test-dist by tsconfig.tests.json.
 *
 * React, react/jsx-runtime and react-native are stubbed with a minimal hook
 * shim + element tree so the component renders in plain node (no
 * react-test-renderer). The `../ui/components` and `../ui/tokens` layers are
 * stubbed to light-weight equivalents; the parentAuthGate module is replaced
 * with a controllable mock. Every test below executes — nothing is skipped.
 *
 * Contract under test:
 * - while checking: renders an ActivityIndicator, never children
 * - { ok: true }: renders children (biometric and device-credential success
 *   both funnel through the gate as ok:true)
 * - { ok: false, reason: 'cancelled' | 'failed' }: a "Try again" button,
 *   children NOT rendered
 * - { ok: false, reason: 'no_credential' }: exact text
 *   "Set up a screen lock on this phone to use Parent Mode." plus an
 *   "Open security settings" button, children NOT rendered
 * - foreground return re-invokes authentication (background invalidation)
 * - session invalidation forces a fresh check on next mount
 * - mounting the gate never renders children without a successful auth
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

const NodeModule: any = require('node:module');
const originalLoad: any = NodeModule._load;

/** Minimal react stub: working useState/useRef/useEffect/useCallback/useMemo + createElement. */
function makeReactStub(): any {
  let slots: any[] = [];
  let idx = 0;
  const effects: Array<() => unknown> = [];
  return {
    __reset() {
      slots = [];
      idx = 0;
      effects.length = 0;
    },
    __beginRender() {
      idx = 0;
    },
    __flushEffects(): Promise<unknown[]> {
      const pending = effects.splice(0, effects.length);
      return Promise.all(pending.map((fn) => fn()));
    },
    createElement(type: any, props: any, ...children: any[]) {
      return { type, props: { ...(props || {}), children: children.length <= 1 ? children[0] : children } };
    },
    Fragment: 'Fragment',
    useState(initial: any) {
      const i = idx++;
      if (!(i in slots)) slots[i] = typeof initial === 'function' ? initial() : initial;
      const setState = (v: any) => {
        slots[i] = typeof v === 'function' ? v(slots[i]) : v;
      };
      return [slots[i], setState];
    },
    useEffect(fn: () => unknown) {
      effects.push(fn);
    },
    useRef(initial: any) {
      const i = idx++;
      if (!(i in slots)) slots[i] = { current: initial };
      return slots[i];
    },
    useCallback(fn: any) {
      return fn;
    },
    useMemo(fn: any) {
      return fn();
    },
  };
}

const reactStub = makeReactStub();
const linkingCalls: string[] = [];
const appStateHandlers: Array<(next: string) => void> = [];

function makeReactNativeStub(): any {
  return {
    View: 'View',
    Text: 'Text',
    Pressable: 'Pressable',
    TouchableOpacity: 'TouchableOpacity',
    Button: 'Button',
    ActivityIndicator: 'ActivityIndicator',
    Alert: { alert: () => {} },
    StyleSheet: { create: (s: any) => s, flatten: (s: any) => s },
    Platform: { OS: 'android', select: (o: any) => o.android },
    Linking: {
      openSettings: async () => {
        linkingCalls.push('openSettings');
        return true;
      },
      openURL: async (url: string) => {
        linkingCalls.push('openURL:' + url);
        return true;
      },
    },
    AppState: {
      addEventListener: (_event: string, handler: (next: string) => void) => {
        appStateHandlers.push(handler);
        return {
          remove: () => {
            const i = appStateHandlers.indexOf(handler);
            if (i >= 0) appStateHandlers.splice(i, 1);
          },
        };
      },
    },
    NativeModules: {},
  };
}

function makeJsxRuntimeStub(): any {
  const el = (type: any, props: any) => ({ type, props: { ...(props || {}) } });
  return { jsx: el, jsxs: el, Fragment: 'Fragment' };
}

function makeUiComponentsStub(): any {
  return {
    Screen: (props: any) => reactStub.createElement('View', null, props.children),
    Button: (props: any) =>
      reactStub.createElement(
        'Pressable',
        { onPress: props.onPress, testID: props.label },
        reactStub.createElement('Text', null, props.label),
      ),
  };
}

function makeUiTokensStub(): any {
  return {
    colors: { brand: '#000000', muted: '#666666', ink: '#111111' },
    spacing: { sm: 4, md: 8, lg: 16 },
  };
}

/** Controllable gate mock: the test decides auth outcomes and authz state. */
let nextOutcome: any = { ok: true };
let requireCalls = 0;
let authorizedFlag = false;
const gateMock = {
  requireParentAuth: async () => {
    requireCalls++;
    return nextOutcome;
  },
  installParentGateInvalidation: () => () => {},
  isParentAuthorized: () => authorizedFlag,
  invalidateParentAuth: () => {
    authorizedFlag = false;
  },
};

NodeModule._load = function (request: string, parent: unknown, isMain: unknown): unknown {
  if (request === 'react') return reactStub;
  if (request === 'react/jsx-runtime') return makeJsxRuntimeStub();
  if (request === 'react-native') return makeReactNativeStub();
  if (request.endsWith('/parentAuthGate')) return gateMock;
  if (request.endsWith('/ui/components')) return makeUiComponentsStub();
  if (request.endsWith('/ui/tokens')) return makeUiTokensStub();
  return originalLoad.call(this, request, parent, isMain);
};

// The component is compiled from src/components/ParentModeGate.tsx into
// test-dist/src/components/ParentModeGate.js by tsconfig.tests.json.
const gateModule = require('../src/components/ParentModeGate');
const ParentModeGate: any = gateModule.ParentModeGate ?? gateModule.default ?? null;
assert.ok(ParentModeGate, 'ParentModeGate component must be compiled and loadable');

const NO_LOCK_TEXT = 'Set up a screen lock on this phone to use Parent Mode.';

function collectStrings(node: any, out: string[] = []): string[] {
  if (node === null || node === undefined || typeof node === 'boolean') return out;
  if (typeof node === 'string' || typeof node === 'number') {
    out.push(String(node));
    return out;
  }
  if (Array.isArray(node)) {
    for (const n of node) collectStrings(n, out);
    return out;
  }
  if (typeof node.type === 'function' && node.type !== ParentModeGate) {
    try {
      return collectStrings(node.type(node.props), out);
    } catch {
      /* fall through to children */
    }
  }
  if (node.props && 'children' in node.props) collectStrings(node.props.children, out);
  return out;
}

function findByType(node: any, types: string[], out: any[] = []): any[] {
  if (Array.isArray(node)) {
    for (const n of node) findByType(n, types, out);
    return out;
  }
  if (node === null || node === undefined || typeof node !== 'object') return out;
  if (typeof node.type === 'function' && node.type !== ParentModeGate) {
    // Expand stub function components (Screen/Button) to find host elements.
    try {
      return findByType(node.type(node.props), types, out);
    } catch {
      /* fall through to children */
    }
  }
  if (typeof node.type === 'string' && types.includes(node.type)) out.push(node);
  if (node.props && 'children' in node.props) findByType(node.props.children, types, out);
  return out;
}

const tick = () => new Promise<void>((resolve) => setImmediate(resolve));

function resetTest() {
  reactStub.__reset();
  appStateHandlers.length = 0;
  linkingCalls.length = 0;
  requireCalls = 0;
  nextOutcome = { ok: true };
  authorizedFlag = false;
}

async function renderGate(children: any = 'CHILD-MARKER'): Promise<any> {
  reactStub.__beginRender();
  ParentModeGate({ children });
  await reactStub.__flushEffects();
  await tick();
  reactStub.__beginRender();
  return ParentModeGate({ children });
}

/** Render once, synchronously, without flushing effects (pre-auth frame). */
function renderGateSync(children: any = 'CHILD-MARKER'): any {
  reactStub.__beginRender();
  return ParentModeGate({ children });
}

function buttonLabels(tree: any): string[] {
  return findByType(tree, ['Pressable', 'TouchableOpacity', 'Button']).map((b: any) =>
    collectStrings(b).join(' '),
  );
}

function findButton(tree: any, labelPart: string): any {
  return findByType(tree, ['Pressable', 'TouchableOpacity', 'Button']).find((b: any) =>
    collectStrings(b).join(' ').includes(labelPart),
  );
}

describe('ParentModeGate', () => {
  it('opens Parent Mode after successful system authentication', async () => {
    resetTest();
    nextOutcome = { ok: true };
    const tree = await renderGate('CHILD-MARKER');
    assert.ok(collectStrings(tree).includes('CHILD-MARKER'), 'children should render when authorized');
    assert.equal(requireCalls, 1);
  });

  it('opens Parent Mode after device-credential (PIN/pattern/password) success', async () => {
    resetTest();
    // The bridge reports method BIOMETRIC vs DEVICE_CREDENTIAL; both funnel
    // through the gate as { ok: true }.
    nextOutcome = { ok: true };
    const tree = await renderGate('CHILD-MARKER');
    assert.ok(collectStrings(tree).includes('CHILD-MARKER'));
    assert.equal(requireCalls, 1);
  });

  it('shows a spinner while the check is in flight and never children first', async () => {
    resetTest();
    nextOutcome = { ok: true };
    const tree = renderGateSync('CHILD-MARKER');
    assert.ok(
      findByType(tree, ['ActivityIndicator']).length > 0,
      'expected an ActivityIndicator while checking',
    );
    assert.ok(
      !collectStrings(tree).includes('CHILD-MARKER'),
      'children must not render before authentication completes',
    );
  });

  it('shows the exact no-lock guidance with a settings button when no credential exists', async () => {
    resetTest();
    nextOutcome = { ok: false, reason: 'no_credential' };
    const tree = await renderGate();
    const text = collectStrings(tree).join(' ');
    assert.ok(text.includes(NO_LOCK_TEXT), 'expected exact blocked text, got: ' + text);
    assert.ok(
      buttonLabels(tree).some((label) => label.includes('Open security settings')),
      'expected an "Open security settings" button',
    );
    assert.ok(!collectStrings(tree).includes('CHILD-MARKER'), 'children must not render when blocked');
  });

  it('opens Android security settings from the blocked screen', async () => {
    resetTest();
    nextOutcome = { ok: false, reason: 'no_credential' };
    const tree = await renderGate();
    const settings = findButton(tree, 'Open security settings');
    assert.ok(settings, 'settings button present');
    await settings.props.onPress();
    assert.ok(linkingCalls.includes('openSettings'), 'expected Linking.openSettings to be called');
  });

  it('does not open Parent Mode when the user cancels authentication', async () => {
    resetTest();
    nextOutcome = { ok: false, reason: 'cancelled' };
    const tree = await renderGate();
    assert.ok(
      buttonLabels(tree).some((label) => label.includes('Try again')),
      'expected a "Try again" button',
    );
    assert.ok(!collectStrings(tree).includes('CHILD-MARKER'), 'children must not render when denied');
  });

  it('does not open Parent Mode when authentication fails', async () => {
    resetTest();
    nextOutcome = { ok: false, reason: 'failed', message: 'Too many attempts.' };
    const tree = await renderGate();
    assert.ok(buttonLabels(tree).some((label) => label.includes('Try again')));
    assert.ok(!collectStrings(tree).includes('CHILD-MARKER'), 'children must not render on failure');
  });

  it('retry re-invokes system authentication', async () => {
    resetTest();
    nextOutcome = { ok: false, reason: 'cancelled' };
    const tree = await renderGate();
    assert.equal(requireCalls, 1);
    const retry = findButton(tree, 'Try again');
    assert.ok(retry, 'retry button present');
    assert.equal(typeof retry.props.onPress, 'function');
    nextOutcome = { ok: true };
    await retry.props.onPress();
    await tick();
    reactStub.__beginRender();
    const tree2 = ParentModeGate({ children: 'CHILD-MARKER' });
    assert.ok(collectStrings(tree2).includes('CHILD-MARKER'));
    assert.equal(requireCalls, 2);
  });

  it('returning to the foreground re-invokes authentication (background invalidation)', async () => {
    resetTest();
    nextOutcome = { ok: true };
    const tree = await renderGate('CHILD-MARKER');
    assert.ok(collectStrings(tree).includes('CHILD-MARKER'));
    assert.equal(requireCalls, 1);
    assert.ok(appStateHandlers.length > 0, 'expected an AppState change listener');
    // Simulate: app was backgrounded (window invalidated elsewhere) and the
    // user returns to the foreground.
    for (const h of [...appStateHandlers]) h('active');
    await tick();
    reactStub.__beginRender();
    const tree2 = ParentModeGate({ children: 'CHILD-MARKER' });
    assert.equal(requireCalls, 2, 'foreground return must trigger a fresh auth check');
    assert.ok(collectStrings(tree2).includes('CHILD-MARKER'));
  });

  it('session invalidation forces a fresh check on next entry', async () => {
    resetTest();
    // A prior session left the window open; the session is replaced.
    authorizedFlag = true;
    gateMock.invalidateParentAuth();
    assert.equal(authorizedFlag, false);
    // Fresh mount (direct navigation to Parent Mode) must not start granted.
    nextOutcome = { ok: false, reason: 'cancelled' };
    const tree = await renderGate('CHILD-MARKER');
    assert.equal(requireCalls, 1, 'a fresh auth check must run after session invalidation');
    assert.ok(
      !collectStrings(tree).includes('CHILD-MARKER'),
      'children must not render without a fresh successful auth',
    );
  });

  it('direct navigation cannot bypass the gate', async () => {
    resetTest();
    // Even mounted directly with children, the gate renders the checking
    // state first and only reveals children after ok:true.
    nextOutcome = { ok: true };
    const syncTree = renderGateSync('CHILD-MARKER');
    assert.ok(
      !collectStrings(syncTree).includes('CHILD-MARKER'),
      'children must never render before the auth outcome',
    );
    await reactStub.__flushEffects();
    await tick();
    reactStub.__beginRender();
    const tree = ParentModeGate({ children: 'CHILD-MARKER' });
    assert.ok(collectStrings(tree).includes('CHILD-MARKER'), 'children render only after ok:true');
  });
});
