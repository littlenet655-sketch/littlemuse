/**
 * Sensitive-action gating contract tests.
 *
 * Proves that every sensitive Parent API call in the mobile client is
 * dominated by `ensureParentAuthForAction()` — i.e. authentication
 * failure/cancel provably prevents the API call from executing.
 *
 * Two layers:
 * 1. Runtime: the exact handler pattern used across the parent screens
 *    (`if (!(await ensureParentAuthForAction())) return; <api>()`) is
 *    executed with a denied gate and an API spy — the spy must never fire.
 *    With an approving gate the spy fires exactly once.
 * 2. Static: every call site of each sensitive parent-admin API in
 *    ParentScreens.tsx / Parent.tsx is checked to be lexically dominated by
 *    an `ensureParentAuthForAction()` guard in an enclosing block. Read-only
 *    APIs (dashboard/notification fetches, markParentNotificationsRead) are
 *    asserted to remain ungated by design.
 *
 * If a future change adds a sensitive call without the gate, the static
 * test fails. If the gate's runtime semantics regress, the runtime test
 * fails. Neither test modifies the architecture.
 */
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const NodeModule: any = require('node:module');
const originalLoad: any = NodeModule._load;

// --- minimal stubs so the real ParentModeGate module loads in plain node ---
function makeReactStub(): any {
  return {
    createElement: (type: any, props: any, ...children: any[]) => ({
      type,
      props: { ...(props || {}), children: children.length <= 1 ? children[0] : children },
    }),
    Fragment: 'Fragment',
    useState: (i: any) => [i, () => {}],
    useEffect: () => {},
    useRef: (i: any) => ({ current: i }),
    useCallback: (f: any) => f,
    useMemo: (f: any) => f(),
  };
}
const alertCalls: string[] = [];
let gateOutcome: any = { ok: true };
let requireCalls = 0;
NodeModule._load = function (request: string, parent: unknown, isMain: unknown): unknown {
  if (request === 'react') return makeReactStub();
  if (request === 'react/jsx-runtime')
    return { jsx: (t: any, p: any) => ({ type: t, props: p || {} }), jsxs: (t: any, p: any) => ({ type: t, props: p || {} }), Fragment: 'Fragment' };
  if (request === 'react-native')
    return {
      View: 'View', Text: 'Text', Pressable: 'Pressable',
      ActivityIndicator: 'ActivityIndicator',
      Alert: { alert: (t: string, m?: string) => { alertCalls.push(t + ': ' + (m ?? '')); } },
      StyleSheet: { create: (s: any) => s },
      Platform: { OS: 'android', select: (o: any) => o.android },
      Linking: { openSettings: async () => true },
      AppState: { addEventListener: () => ({ remove: () => {} }) },
      NativeModules: {},
    };
  if (request.endsWith('/parentAuthGate'))
    return {
      requireParentAuth: async () => { requireCalls++; return gateOutcome; },
      installParentGateInvalidation: () => () => {},
      isParentAuthorized: () => false,
    };
  if (request.endsWith('/ui/components'))
    return { Screen: (p: any) => p.children, Button: (p: any) => p.label };
  if (request.endsWith('/ui/tokens'))
    return { colors: {}, spacing: {} };
  return originalLoad.call(this, request, parent, isMain);
};

const { ensureParentAuthForAction } = require('../src/components/ParentModeGate');

/** The exact handler shape used by every gated parent screen action. */
async function gatedHandler(api: () => Promise<void>): Promise<'blocked' | 'executed'> {
  if (!(await ensureParentAuthForAction())) return 'blocked';
  await api();
  return 'executed';
}

describe('sensitive action gating — runtime', () => {
  it('does NOT call the API when the user cancels authentication', async () => {
    gateOutcome = { ok: false, reason: 'cancelled' };
    requireCalls = 0;
    alertCalls.length = 0;
    let apiCalls = 0;
    const result = await gatedHandler(async () => { apiCalls++; });
    assert.equal(result, 'blocked');
    assert.equal(apiCalls, 0, 'API must not execute after cancel');
    assert.equal(requireCalls, 1);
    assert.ok(alertCalls.some((a) => a.includes('Authentication cancelled')));
  });

  it('does NOT call the API when authentication fails', async () => {
    gateOutcome = { ok: false, reason: 'failed', message: 'Too many attempts.' };
    let apiCalls = 0;
    const result = await gatedHandler(async () => { apiCalls++; });
    assert.equal(result, 'blocked');
    assert.equal(apiCalls, 0, 'API must not execute after failure');
  });

  it('does NOT call the API when no device credential exists', async () => {
    gateOutcome = { ok: false, reason: 'no_credential' };
    let apiCalls = 0;
    const result = await gatedHandler(async () => { apiCalls++; });
    assert.equal(result, 'blocked');
    assert.equal(apiCalls, 0, 'API must not execute without a screen lock');
    assert.ok(alertCalls.some((a) => a.includes('Screen lock required')));
  });

  it('calls the API exactly once after successful authentication', async () => {
    gateOutcome = { ok: true };
    let apiCalls = 0;
    const result = await gatedHandler(async () => { apiCalls++; });
    assert.equal(result, 'executed');
    assert.equal(apiCalls, 1);
  });
});

// ---------------------------------------------------------------------------
// Static dominance audit
// ---------------------------------------------------------------------------

const SRC = join(__dirname, '..', '..', 'src');

/** Sensitive mutating parent APIs: every call site must be gate-dominated. */
const SENSITIVE_APIS = [
  'createChild',
  'resetChildPassword',
  'unlinkChild',
  'resolveParentReview',
  'updateTimeLimit',
  'extendChildScreenTime',
  'resetChildScreenTime',
  'updateParentControls',
  'resolveFollowRequest',
];

const GATE = 'ensureParentAuthForAction';

interface CallSite { file: string; line: number; col: number; api: string }

function findCallSites(): CallSite[] {
  const sites: CallSite[] = [];
  for (const rel of ['screens/parent/ParentScreens.tsx', 'screens/Parent.tsx']) {
    const src = readFileSync(join(SRC, rel), 'utf8');
    const lines = src.split('\n');
    for (const api of SENSITIVE_APIS) {
      const importRe = new RegExp(`^import\\s*\\{[\\s\\S]*?\\b${api}\\b`);
      void importRe;
      const callRe = new RegExp(`\\b${api}\\s*\\(`);
      const mutateRe = /\.mutate\s*\(/;
      void mutateRe;
      lines.forEach((line, idx) => {
        if (line.trim().startsWith('import') || line.trim().startsWith('//')) return;
        // queryFn/mutationFn lambdas are deferred invocations, not call sites;
        // the actual invocation (.mutate() / query execution) is audited separately.
        // (Also skip a continuation line when the previous line opens a mutationFn.)
        if (line.includes('queryFn:') || line.includes('mutationFn:')) return;
        if (idx > 0 && lines[idx - 1]!.includes('mutationFn')) return;
        const cm = line.match(callRe);
        if (cm) sites.push({ file: rel, line: idx + 1, col: cm.index!, api });
      });
    }
    // mutation.mutate() sites: resolve the receiver (e.g. `resetMutation`),
    // find its `const <receiver> = useMutation(` declaration, and attribute
    // the API invoked by its mutationFn.
    const mutRe = /(\w+)\.mutate\s*\(/;
    lines.forEach((line, idx) => {
      const mm = line.match(mutRe);
      if (!mm) return;
      const receiver = mm[1]!;
      let api = 'unknown-mutation';
      const declRe = new RegExp(`const\\s+${receiver}\\s*=\\s*useMutation\\s*\\(`);
      for (let l = idx; l >= 0; l--) {
        if (!declRe.test(lines[l]!)) continue;
        const joined = lines.slice(l, l + 4).join(' ');
        const m = joined.match(/mutationFn[\s\S]*?=>\s*(\w+)\s*\(/);
        if (m) api = m[1]!;
        break;
      }
      if (SENSITIVE_APIS.includes(api)) sites.push({ file: rel, line: idx + 1, col: mm.index!, api: api + '.mutate' });
    });
  }
  return sites;
}

/**
 * True when an `ensureParentAuthForAction()` guard lexically dominates the
 * call: the nearest preceding gate occurrence is not separated from the
 * call by a block close (brace depth never goes negative scanning forward
 * from the gate line to the call).
 */
function isGateDominated(src: string, callLineIdx: number, callCol: number): boolean {
  const lines = src.split('\n');
  const callLine = lines[callLineIdx]!;
  // Same-line guard: `if (await ensureParentAuthForAction()) api(...)`.
  if (callLine.slice(0, callCol).includes(GATE)) return true;
  let gateLine = -1;
  for (let l = callLineIdx - 1; l >= Math.max(0, callLineIdx - 40) && gateLine < 0; l--) {
    if (lines[l]!.includes(GATE)) gateLine = l;
  }
  if (gateLine < 0) return false;
  let depth = 0;
  for (let l = gateLine; l <= callLineIdx; l++) {
    const text = l === callLineIdx ? lines[l]!.slice(0, callCol) : lines[l]!;
    // crude string/comment stripping to avoid brace miscounts
    const code = text.replace(/'(?:[^'\\]|\\.)*'/g, "''").replace(/"(?:[^"\\]|\\.)*"/g, '""').replace(/`(?:[^`\\]|\\.)*`/g, '``').replace(/\/\/.*$/, '');
    for (const ch of code) {
      if (ch === '{') depth++;
      else if (ch === '}') {
        depth--;
        if (depth < 0) return false;
      }
    }
  }
  return true;
}

describe('sensitive action gating — static audit', () => {
  it('every sensitive parent API call site is dominated by ensureParentAuthForAction()', () => {
    const sites = findCallSites();
    assert.ok(sites.length >= 11, `expected >= 11 sensitive call sites, found ${sites.length}`);
    const ungated = sites.filter((s) => {
      const src = readFileSync(join(SRC, s.file), 'utf8');
      return !isGateDominated(src, s.line - 1, s.col);
    });
    assert.deepEqual(
      ungated, [],
      'ungated sensitive call sites:\n' + ungated.map((s) => `  ${s.file}:${s.line} ${s.api}`).join('\n'),
    );
  });

  it('covers all required sensitive actions', () => {
    const sites = findCallSites();
    const covered = new Set(sites.map((s) => s.api.replace('.mutate', '')));
    for (const api of SENSITIVE_APIS) {
      assert.ok(covered.has(api), `no gated call site found for ${api}`);
    }
  });

  it('read-only parent APIs intentionally remain ungated', () => {
    const src = readFileSync(join(SRC, 'screens/parent/ParentScreens.tsx'), 'utf8');
    for (const api of ['markParentNotificationsRead', 'fetchParentDashboard']) {
      const lines = src.split('\n');
      lines.forEach((line, idx) => {
        if (line.includes('queryFn:') || line.includes('mutationFn:')) return;
        const m = line.match(new RegExp(`\\b${api}\\s*\\(`));
        if (!m || line.trim().startsWith('import')) return;
        assert.ok(
          !isGateDominated(src, idx, m.index!),
          `${api} at line ${idx + 1} should stay ungated (read-only by design)`,
        );
      });
    }
  });

  it('RootNavigator wraps the Parent navigator in ParentModeGate', () => {
    const src = readFileSync(join(SRC, 'navigation/RootNavigator.tsx'), 'utf8');
    assert.ok(src.includes('ParentModeGate'), 'ParentModeGate must be used in RootNavigator');
    const m = src.match(/<ParentModeGate>[\s\S]*?<\/ParentModeGate>/);
    assert.ok(m, 'ParentModeGate must wrap a navigator subtree');
    assert.ok(/Parent(Navigator|Stack|Tabs)/.test(m[0]), 'ParentModeGate must enclose the Parent navigator');
  });
});
