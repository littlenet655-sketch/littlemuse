/**
 * Bridge contract tests for src/deviceAuth/parentDeviceAuth.ts.
 *
 * The bridge talks to the native Android ParentDeviceAuth module through
 * react-native's NativeModules. These tests stub 'react-native' via the
 * CommonJS module loader so the bridge can be exercised in plain node.
 *
 * Run: npx tsc -p tsconfig.tests.json && node --test test-dist/tests/parentDeviceAuth.test.js
 */
import { describe, it, beforeEach } from 'node:test';
import assert from 'node:assert/strict';

const NodeModule: any = require('node:module');
const originalLoad: any = NodeModule._load;

function installReactNativeStub(nativeModule: any | undefined, platformOS = 'android'): void {
  const stub = {
    NativeModules: nativeModule === undefined ? {} : { ParentDeviceAuth: nativeModule },
    Platform: { OS: platformOS },
  };
  NodeModule._load = function (request: string, parent: unknown, isMain: unknown): unknown {
    if (request === 'react-native') return stub;
    return originalLoad.call(this, request, parent, isMain);
  };
}

type Bridge = typeof import('../src/deviceAuth/parentDeviceAuth');

function loadBridge(): Bridge {
  const path: string = require.resolve('../src/deviceAuth/parentDeviceAuth');
  delete require.cache[path];
  return require(path) as Bridge;
}

beforeEach(() => {
  NodeModule._load = originalLoad;
});

const ALL_FALSE = {
  biometricAvailable: false,
  biometricEnrolled: false,
  deviceCredentialAvailable: false,
  canAuthenticate: false,
};

describe('parentDeviceAuth bridge', () => {
  it('maps the native capability status to booleans', async () => {
    installReactNativeStub({
      checkParentDeviceAuth: async () => ({
        biometricAvailable: 1,
        biometricEnrolled: 0,
        deviceCredentialAvailable: 'yes',
        canAuthenticate: 1,
      }),
    });
    const bridge = loadBridge();
    assert.deepStrictEqual(await bridge.checkParentDeviceAuth(), {
      biometricAvailable: true,
      biometricEnrolled: false,
      deviceCredentialAvailable: true,
      canAuthenticate: true,
    });
    assert.equal(bridge.isParentDeviceAuthNativeAvailable(), true);
  });

  it('reports all-false when the native module is absent', async () => {
    installReactNativeStub(undefined);
    const bridge = loadBridge();
    assert.deepStrictEqual(await bridge.checkParentDeviceAuth(), ALL_FALSE);
    assert.equal(bridge.isParentDeviceAuthNativeAvailable(), false);
  });

  it('reports all-false on non-Android platforms even if a module exists', async () => {
    installReactNativeStub(
      { checkParentDeviceAuth: async () => ({ canAuthenticate: true }) },
      'ios',
    );
    const bridge = loadBridge();
    assert.deepStrictEqual(await bridge.checkParentDeviceAuth(), ALL_FALSE);
    assert.equal(bridge.isParentDeviceAuthNativeAvailable(), false);
  });

  it('reports all-false when the native status call throws', async () => {
    installReactNativeStub({
      checkParentDeviceAuth: async () => {
        throw new Error('binder transaction failed');
      },
    });
    const bridge = loadBridge();
    assert.deepStrictEqual(await bridge.checkParentDeviceAuth(), ALL_FALSE);
  });

  it('returns success with the BIOMETRIC method', async () => {
    installReactNativeStub({
      authenticateParentDevice: async () => ({ success: true, method: 'BIOMETRIC' }),
    });
    const bridge = loadBridge();
    assert.deepStrictEqual(await bridge.authenticateParentDevice(), {
      success: true,
      method: 'BIOMETRIC',
    });
  });

  it('returns success with the DEVICE_CREDENTIAL fallback method', async () => {
    installReactNativeStub({
      authenticateParentDevice: async () => ({ success: true, method: 'DEVICE_CREDENTIAL' }),
    });
    const bridge = loadBridge();
    assert.deepStrictEqual(await bridge.authenticateParentDevice(), {
      success: true,
      method: 'DEVICE_CREDENTIAL',
    });
  });

  it('maps USER_CANCEL (real Kotlin casing) distinctly from other failures', async () => {
    installReactNativeStub({
      authenticateParentDevice: async () => ({
        success: false,
        error: 'USER_CANCEL',
        message: 'Dialog dismissed',
      }),
    });
    const bridge = loadBridge();
    assert.deepStrictEqual(await bridge.authenticateParentDevice(), {
      success: false,
      error: 'user_cancel',
      message: 'Dialog dismissed',
    });
  });

  it('maps Kotlin NOT_ENROLLED, LOCKOUT, and FAILED onto the lowercase union', async () => {
    for (const [native, expected] of [
      ['NOT_ENROLLED', 'not_enrolled'],
      ['LOCKOUT', 'lockout'],
      ['FAILED', 'failure'],
    ] as const) {
      installReactNativeStub({
        authenticateParentDevice: async () => ({ success: false, error: native }),
      });
      const bridge = loadBridge();
      const result = await bridge.authenticateParentDevice();
      assert.equal(result.success, false);
      assert.equal(result.error, expected);
    }
  });

  it('falls back to failure for unknown or empty native error codes', async () => {
    for (const native of ['NO_ACTIVITY', 'SOMETHING_ELSE', '', undefined] as const) {
      installReactNativeStub({
        authenticateParentDevice: async () => ({ success: false, error: native }),
      });
      const bridge = loadBridge();
      const result = await bridge.authenticateParentDevice();
      assert.equal(result.success, false);
      assert.equal(result.error, 'failure');
    }
  });

  it('maps a native throw to a failure result', async () => {
    installReactNativeStub({
      authenticateParentDevice: async () => {
        throw new Error('crypto object init failed');
      },
    });
    const bridge = loadBridge();
    const result = await bridge.authenticateParentDevice();
    assert.equal(result.success, false);
    assert.equal(result.error, 'failure');
    assert.equal(result.message, 'crypto object init failed');
  });

  it('maps a falsy native result to a failure result', async () => {
    installReactNativeStub({ authenticateParentDevice: async () => null });
    const bridge = loadBridge();
    const result = await bridge.authenticateParentDevice();
    assert.equal(result.success, false);
    assert.equal(result.error, 'failure');
  });

  it('returns unavailable when there is no native module', async () => {
    installReactNativeStub(undefined);
    const bridge = loadBridge();
    const result = await bridge.authenticateParentDevice();
    assert.equal(result.success, false);
    assert.equal(result.error, 'unavailable');
    assert.ok(typeof result.message === 'string' && result.message.length > 0);
  });
});
