/// <reference types="node" />
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';

process.env.EXPO_PUBLIC_API_BASE_URL = 'https://backend.test.invalid';

import {
  clampAspectRatio,
  deliveryKindOf,
  MAX_FEED_ASPECT,
  MIN_FEED_ASPECT,
  parseAspectRatio,
} from '../src/video/types';
import { getBufferOptions } from '../src/video/playbackPolicy';
import { ReelMetricsTracker } from '../src/video/reelPlaybackMetrics';
import type { FeedItem } from '../src/api/kidsFeed';
import {
  completeUpload,
  fetchProcessingStatus,
  fetchStoryViewers,
  formatBytes,
  maxVideoDurationFor,
  mediaKindFromMimeType,
  redriveProcessing,
  requestUploadSession,
  validateMediaIdentity,
  validateVideoDuration,
} from '../src/api/kidsUpload';

// ---------------------------------------------------------------------------
// Mock network
// ---------------------------------------------------------------------------

interface SeenRequest {
  url: string;
  init: RequestInit;
}

let seen: SeenRequest[] = [];
let nextPayload: unknown = { ok: true };
let nextStatus = 200;

function stubFetch(): void {
  seen = [];
  (globalThis as unknown as Record<string, unknown>).fetch = async (url: unknown, init?: RequestInit) => {
    seen.push({ url: String(url), init: init ?? {} });
    return {
      ok: nextStatus >= 200 && nextStatus < 300,
      status: nextStatus,
      json: async () => nextPayload,
    };
  };
}

function bodyJson(index = 0): Record<string, unknown> {
  return JSON.parse(String(seen[index]?.init.body ?? '{}')) as Record<string, unknown>;
}

function authHeader(index = 0): string | null {
  const headers = seen[index]?.init.headers as Headers | undefined;
  return headers?.get('Authorization') ?? null;
}

function testItem(): FeedItem {
  return { source_type: 'SOCIAL', source_id: 7, post_id: 42 } as FeedItem;
}

/** Deterministic clock for watch-time assertions. */
function withFakeClock<T>(fn: (advance: (ms: number) => void) => T): T {
  const realNow = Date.now;
  let now = 1_000_000;
  Date.now = () => now;
  try {
    return fn((ms: number) => {
      now += ms;
    });
  } finally {
    Date.now = realNow;
  }
}

// ---------------------------------------------------------------------------
// video/types helpers
// ---------------------------------------------------------------------------

describe('parseAspectRatio', () => {
  it('parses W:H tags', () => {
    assert.equal(parseAspectRatio('9:16'), 9 / 16);
    assert.equal(parseAspectRatio('16:9'), 16 / 9);
    assert.equal(parseAspectRatio('1:1'), 1);
    assert.equal(parseAspectRatio('4/5'), 4 / 5);
    assert.equal(parseAspectRatio(' 3 : 4 '), 3 / 4);
  });

  it('rejects missing or malformed tags without inventing a ratio', () => {
    assert.equal(parseAspectRatio(null), null);
    assert.equal(parseAspectRatio(undefined), null);
    assert.equal(parseAspectRatio(''), null);
    assert.equal(parseAspectRatio('wide'), null);
    assert.equal(parseAspectRatio('16-9'), null);
    assert.equal(parseAspectRatio('0:0'), null);
    assert.equal(parseAspectRatio('16:0'), null);
  });
});

describe('clampAspectRatio', () => {
  it('clamps into the portrait..landscape display range', () => {
    assert.equal(clampAspectRatio(0.1), MIN_FEED_ASPECT);
    assert.equal(clampAspectRatio(5), MAX_FEED_ASPECT);
    assert.equal(clampAspectRatio(1), 1);
  });

  it('falls back to square for non-finite input', () => {
    assert.equal(clampAspectRatio(NaN), 1);
    assert.equal(clampAspectRatio(0), 1);
    assert.equal(clampAspectRatio(-2), 1);
  });
});

describe('deliveryKindOf', () => {
  it('trusts the declared delivery_type first', () => {
    assert.equal(deliveryKindOf({ delivery_type: 'HLS' }), 'HLS');
    assert.equal(deliveryKindOf({ delivery_type: 'MP4' }), 'MP4');
  });

  it('sniffs the URL when the type is absent', () => {
    assert.equal(deliveryKindOf({ playback_url: 'https://cdn.example/manifest/video.m3u8?token=abc' }), 'HLS');
    assert.equal(deliveryKindOf({ playback_url: 'https://cdn.example/v.mp4?sig=1' }), 'MP4');
    assert.equal(deliveryKindOf({}), 'UNKNOWN');
    assert.equal(deliveryKindOf({ playback_url: 'https://cdn.example/blob' }), 'UNKNOWN');
  });
});

// ---------------------------------------------------------------------------
// playbackPolicy
// ---------------------------------------------------------------------------

describe('getBufferOptions', () => {
  it('uses fast-startup buffers for NORMAL', () => {
    const opts = getBufferOptions('NORMAL');
    assert.equal(opts.minBufferForPlayback, 1.5);
    assert.equal(opts.preferredForwardBufferDuration, 8.0);
    assert.equal(opts.prioritizeTimeOverSizeThreshold, true);
  });

  it('uses conservative buffers for DATA_SAVER', () => {
    const opts = getBufferOptions('DATA_SAVER');
    assert.equal(opts.minBufferForPlayback, 1.0);
    assert.equal(opts.preferredForwardBufferDuration, 4.0);
  });
});

// ---------------------------------------------------------------------------
// reelPlaybackMetrics
// ---------------------------------------------------------------------------

describe('ReelMetricsTracker', () => {
  it('accumulates watch time across play/pause segments', () => {
    withFakeClock((advance) => {
      const t = new ReelMetricsTracker(testItem(), 'REELS');
      t.onPlayingStarted();
      advance(1200);
      t.onPlayingPaused();
      t.onPlayingStarted();
      advance(800);
      t.onPlayingPaused();
      assert.equal(t.getSnapshot().watched_ms, 2000);
    });
  });

  it('marks completion at the 90% threshold and on natural end', () => {
    const t = new ReelMetricsTracker(testItem(), 'REELS');
    t.onTimeUpdate(8.9, 10);
    assert.equal(t.getSnapshot().completed, false);
    t.onTimeUpdate(9.0, 10);
    assert.equal(t.getSnapshot().completed, true);
  });

  it('counts the first natural end as completion, later ends as replays', () => {
    const t = new ReelMetricsTracker(testItem(), 'REELS');
    t.onPlayToEnd();
    assert.equal(t.getSnapshot().replay_count, 0);
    assert.equal(t.getSnapshot().completed, true);
    t.onPlayToEnd();
    t.onPlayToEnd();
    assert.equal(t.getSnapshot().replay_count, 2);
  });

  it('counts rebuffers only after playback started', () => {
    withFakeClock((advance) => {
      const t = new ReelMetricsTracker(testItem(), 'REELS');
      t.onBufferingStarted(); // pre-roll stall: not a rebuffer
      assert.equal(t.getSnapshot().rebuffer_count, 0);
      t.onPlayingStarted();
      advance(500);
      t.onBufferingStarted();
      advance(700);
      t.onPlayingStarted();
      const snap = t.getSnapshot();
      assert.equal(snap.rebuffer_count, 1);
      assert.equal(snap.total_rebuffer_ms, 700);
    });
  });

  it('tracks credential refreshes and last error', () => {
    const t = new ReelMetricsTracker(testItem(), 'REELS');
    t.onCredentialRefreshed();
    t.onCredentialRefreshed();
    t.onError('expired signed url');
    const snap = t.getSnapshot();
    assert.equal(snap.credential_refreshes, 2);
    assert.equal(snap.error_type, 'expired signed url');
  });

  it('records time-to-first-frame from the play request', () => {
    withFakeClock((advance) => {
      const t = new ReelMetricsTracker(testItem(), 'REELS');
      advance(450);
      t.onFirstFrame();
      assert.equal(t.getSnapshot().ttff_ms, 450);
      advance(100);
      t.onFirstFrame(); // second call must not overwrite
      assert.equal(t.getSnapshot().ttff_ms, 450);
    });
  });

  it('builds the impression payload the reels screen batches', () => {
    withFakeClock((advance) => {
      const t = new ReelMetricsTracker(testItem(), 'REELS');
      t.onPlayingStarted();
      advance(3000);
      t.onPlayingPaused();
      t.onPlayToEnd();
      const payload = t.toImpressionPayload('sess-1');
      assert.equal(payload.session_id, 'sess-1');
      assert.equal(payload.source_type, 'SOCIAL');
      assert.equal(payload.source_id, 42);
      assert.equal(payload.surface, 'REELS');
      assert.equal(payload.watched_ms, 3000);
      assert.equal(payload.completed, true);
    });
  });
});

// ---------------------------------------------------------------------------
// kidsUpload pure helpers
// ---------------------------------------------------------------------------

describe('validateMediaIdentity', () => {
  it('accepts matching extension and MIME type', () => {
    validateMediaIdentity('photo.jpg', 'image/jpeg');
    validateMediaIdentity('PHOTO.PNG', 'image/png');
    validateMediaIdentity('clip.mov', 'video/quicktime');
    validateMediaIdentity('clip.m4v', 'video/mp4');
  });

  it('rejects mismatched or unknown pairs', () => {
    assert.throws(() => validateMediaIdentity('photo.png', 'image/jpeg'));
    assert.throws(() => validateMediaIdentity('clip.mp4', 'video/quicktime'));
    assert.throws(() => validateMediaIdentity('notes.pdf', 'image/jpeg'));
    assert.throws(() => validateMediaIdentity('photo.jpg', 'application/octet-stream'));
  });
});

describe('mediaKindFromMimeType', () => {
  it('classifies image/video and rejects the rest', () => {
    assert.equal(mediaKindFromMimeType('image/jpeg'), 'image');
    assert.equal(mediaKindFromMimeType('VIDEO/MP4'), 'video');
    assert.equal(mediaKindFromMimeType(null), null);
    assert.equal(mediaKindFromMimeType(undefined), null);
    assert.equal(mediaKindFromMimeType('application/pdf'), null);
  });
});

describe('formatBytes', () => {
  it('formats human-friendly sizes', () => {
    assert.equal(formatBytes(0), '0 B');
    assert.equal(formatBytes(512), '512 B');
    assert.equal(formatBytes(2048), '2 KB');
    assert.equal(formatBytes(5 * 1024 * 1024), '5 MB');
    assert.equal(formatBytes(Math.round(2.5 * 1024 * 1024)), '2.5 MB');
  });
});

describe('maxVideoDurationFor', () => {
  it('mirrors the server limits per creation kind', () => {
    assert.equal(maxVideoDurationFor('reel'), 45);
    assert.equal(maxVideoDurationFor('story'), 60);
    assert.equal(maxVideoDurationFor('post'), 600);
    assert.equal(maxVideoDurationFor('REEL'), 45);
    assert.equal(maxVideoDurationFor('unknown'), 600);
  });
});

describe('validateVideoDuration', () => {
  it('rejects over-limit reels before upload', () => {
    assert.throws(
      () => validateVideoDuration({ mimeType: 'video/mp4', duration: 46 }, 'reel'),
      /under 45 seconds/,
    );
  });

  it('accepts reels within the 45s cap', () => {
    validateVideoDuration({ mimeType: 'video/mp4', duration: 45 }, 'reel');
    validateVideoDuration({ mimeType: 'video/mp4', duration: 30 }, 'reel');
  });

  it('ignores images and missing durations (server enforces)', () => {
    validateVideoDuration({ mimeType: 'image/jpeg', duration: 999 }, 'reel');
    validateVideoDuration({ mimeType: 'video/mp4', duration: null }, 'reel');
    validateVideoDuration({ mimeType: 'video/mp4' }, 'reel');
  });

  it('applies the story/post caps', () => {
    assert.throws(
      () => validateVideoDuration({ mimeType: 'video/mp4', duration: 61 }, 'story'),
      /under 60 seconds/,
    );
    validateVideoDuration({ mimeType: 'video/mp4', duration: 300 }, 'post');
  });
});

// ---------------------------------------------------------------------------
// kidsUpload network contracts (mocked fetch)
// ---------------------------------------------------------------------------

describe('upload pipeline API contracts', () => {
  it('requests an upload session with the v2 control-plane shape', async () => {
    stubFetch();
    nextPayload = {
      ok: true,
      upload_id: 'up-1',
      upload_url: 'https://r2.example/put',
      object_key: 'q/up-1.mp4',
      expires_at: '2030-01-01T00:00:00Z',
      required_headers: { 'Content-Type': 'video/mp4' },
    };
    const res = await requestUploadSession('tok-1', {
      kind: 'reel',
      filename: 'clip.mp4',
      mediaType: 'VIDEO',
      sizeBytes: 1024,
      mimeType: 'video/mp4',
    });
    assert.equal(seen[0]?.url, 'https://backend.test.invalid/api/mobile/v2/uploads/session');
    assert.equal(seen[0]?.init.method, 'POST');
    assert.equal(authHeader(), 'Bearer tok-1');
    const body = bodyJson();
    assert.equal(body.kind, 'reel');
    assert.equal(body.filename, 'clip.mp4');
    assert.equal(body.media_type, 'VIDEO');
    assert.equal(body.size_bytes, 1024);
    assert.equal(body.mime_type, 'video/mp4');
    assert.equal(res.upload_id, 'up-1');
    assert.equal(res.upload_url, 'https://r2.example/put');
  });

  it('completes an upload against the session-scoped endpoint', async () => {
    stubFetch();
    nextPayload = { ok: true, post_id: 99, status: 'PROCESSING' };
    const res = await completeUpload('tok-1', 'up-1', {
      caption: 'hello',
      contentCategory: 'Fun',
      tags: ['art'],
      locationName: 'Home',
    });
    assert.equal(seen[0]?.url, 'https://backend.test.invalid/api/mobile/v2/uploads/up-1/complete');
    const body = bodyJson();
    assert.equal(body.caption, 'hello');
    assert.equal(body.content_category, 'Fun');
    assert.deepEqual(body.tags, ['art']);
    assert.equal(body.location_name, 'Home');
    assert.equal(res.post_id, 99);
  });

  it('polls processing status for the owning child', async () => {
    stubFetch();
    nextPayload = { ok: true, post_id: 99, status: 'ALLOWED', stage: 'ALLOWED', moderation_status: 'ALLOWED' };
    const res = await fetchProcessingStatus('tok-1', 99);
    assert.equal(seen[0]?.url, 'https://backend.test.invalid/api/mobile/v2/posts/99/processing-status');
    assert.equal((seen[0]?.init.method ?? 'GET').toUpperCase(), 'GET');
    assert.equal(res.status, 'ALLOWED');
  });

  it('redrives a failed job', async () => {
    stubFetch();
    nextPayload = { ok: true };
    const res = await redriveProcessing('tok-1', 99);
    assert.equal(seen[0]?.url, 'https://backend.test.invalid/api/mobile/v2/posts/99/redrive');
    assert.equal(seen[0]?.init.method, 'POST');
    assert.equal(res.ok, true);
  });

  it('fetches the viewer list for an owned story', async () => {
    stubFetch();
    nextPayload = { ok: true, viewers: [{ child_id: 5, full_name: 'Ava' }] };
    const res = await fetchStoryViewers('tok-1', 7);
    assert.equal(seen[0]?.url, 'https://backend.test.invalid/api/mobile/v2/kids/stories/7/viewers');
    assert.equal(res.viewers.length, 1);
    assert.equal(res.viewers[0]?.child_id, 5);
  });

  it('surfaces server errors as ApiError', async () => {
    stubFetch();
    nextStatus = 403;
    nextPayload = { error: 'forbidden_not_post_owner' };
    await assert.rejects(() => fetchProcessingStatus('tok-1', 1));
    nextStatus = 200;
  });
});
