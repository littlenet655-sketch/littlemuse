/// <reference types="node" />
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

process.env.EXPO_PUBLIC_API_BASE_URL = 'https://backend.test.invalid';

import { setUnauthorizedHandler } from '../src/api/client';
import { deletePost, deleteStory } from '../src/api/kidsSocial';

let seen: Array<{ url: string; init: RequestInit }> = [];
let nextPayload: unknown = { ok: true };
let nextStatus = 200;

function stub() {
  seen = [];
  (globalThis as unknown as Record<string, unknown>).fetch = async (url: unknown, init?: RequestInit) => {
    seen.push({ url: String(url), init: init ?? {} });
    return { ok: nextStatus >= 200 && nextStatus < 300, status: nextStatus, json: async () => nextPayload };
  };
}

describe('kids post/story soft-delete API', () => {
  it('deletes a post with DELETE on the v1 post route', async () => {
    stub();
    setUnauthorizedHandler(null);
    nextStatus = 200;
    nextPayload = { ok: true };
    const res = await deletePost('tok', 123);
    assert.equal(res.ok, true);
    assert.ok(seen[0]?.url.endsWith('/api/mobile/v1/kids/posts/123'), seen[0]?.url);
    assert.equal(String(seen[0]?.init.method).toUpperCase(), 'DELETE');
  });

  it('deletes a story with DELETE on the v2 story route', async () => {
    stub();
    setUnauthorizedHandler(null);
    nextStatus = 200;
    nextPayload = { ok: true };
    const res = await deleteStory('tok', 456);
    assert.equal(res.ok, true);
    assert.ok(seen[0]?.url.endsWith('/api/mobile/v2/kids/stories/456'), seen[0]?.url);
    assert.equal(String(seen[0]?.init.method).toUpperCase(), 'DELETE');
  });
});
