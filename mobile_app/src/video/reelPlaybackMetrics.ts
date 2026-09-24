import type { FeedItem } from '../api/kidsFeed';
import type { ImpressionEventPayload, ReelMetrics } from './types';

export class ReelMetricsTracker {
  private startTime: number | null = null;
  private lastActiveTimestamp: number | null = null;
  private totalWatchMs = 0;
  private durationSec = 0;
  private hasCompleted = false;
  private replays = 0;
  private endedCount = 0;
  private hasStartedPlayback = false;
  private ttffMs: number | null = null;
  private playRequestedAt: number | null = null;
  private rebufferCount = 0;
  private totalRebufferMs = 0;
  private rebufferStartedAt: number | null = null;
  private credentialRefreshes = 0;
  private lastReportedError: string | null = null;

  constructor(
    private readonly item: FeedItem,
    private readonly surface: 'REELS' | 'FEED' = 'REELS',
  ) {
    this.playRequestedAt = Date.now();
  }

  onPlayRequested(): void {
    if (!this.playRequestedAt) {
      this.playRequestedAt = Date.now();
    }
  }

  onFirstFrame(): void {
    if (this.playRequestedAt && this.ttffMs === null) {
      this.ttffMs = Math.max(0, Date.now() - this.playRequestedAt);
    }
  }

  onPlayingStarted(): void {
    this.hasStartedPlayback = true;
    this.lastActiveTimestamp = Date.now();
    if (this.rebufferStartedAt) {
      this.totalRebufferMs += Math.max(0, Date.now() - this.rebufferStartedAt);
      this.rebufferStartedAt = null;
    }
  }

  onPlayingPaused(): void {
    if (this.lastActiveTimestamp) {
      this.totalWatchMs += Math.max(0, Date.now() - this.lastActiveTimestamp);
      this.lastActiveTimestamp = null;
    }
  }

  onBufferingStarted(): void {
    if (!this.hasStartedPlayback) {
      return;
    }
    if (this.lastActiveTimestamp) {
      this.totalWatchMs += Math.max(0, Date.now() - this.lastActiveTimestamp);
      this.lastActiveTimestamp = null;
    }
    if (!this.rebufferStartedAt) {
      this.rebufferStartedAt = Date.now();
      this.rebufferCount += 1;
    }
  }

  onTimeUpdate(currentSec: number, totalDurationSec?: number): void {
    if (totalDurationSec && totalDurationSec > 0) {
      this.durationSec = totalDurationSec;
    }

    // Check completion threshold (90% or greater)
    if (this.durationSec > 0 && currentSec / this.durationSec >= 0.9) {
      this.hasCompleted = true;
    }
  }

  onPlayToEnd(): void {
    // The first natural end is completion, not a replay. Because the player
    // loops, only subsequent completed loops count as replays.
    if (this.endedCount > 0) {
      this.replays += 1;
    }
    this.endedCount += 1;
    this.hasCompleted = true;
  }

  onCredentialRefreshed(): void {
    this.credentialRefreshes += 1;
  }

  onError(err: string): void {
    this.lastReportedError = err;
    if (this.lastActiveTimestamp) {
      this.totalWatchMs += Math.max(0, Date.now() - this.lastActiveTimestamp);
      this.lastActiveTimestamp = null;
    }
  }

  getSnapshot(): ReelMetrics {
    let watch = this.totalWatchMs;
    if (this.lastActiveTimestamp) {
      watch += Math.max(0, Date.now() - this.lastActiveTimestamp);
    }

    return {
      source_type: this.item.source_type,
      source_id: this.item.post_id || this.item.source_id,
      surface: this.surface,
      watched_ms: Math.round(watch),
      completed: this.hasCompleted,
      replay_count: this.replays,
      liked: this.item.viewer_liked,
      saved: this.item.viewer_saved,
      ttff_ms: this.ttffMs ?? undefined,
      rebuffer_count: this.rebufferCount,
      total_rebuffer_ms: Math.round(this.totalRebufferMs),
      error_type: this.lastReportedError,
      credential_refreshes: this.credentialRefreshes,
    };
  }

  toImpressionPayload(sessionId?: string): ImpressionEventPayload {
    const snap = this.getSnapshot();
    return {
      session_id: sessionId ?? this.item.feed_session_id,
      source_type: snap.source_type,
      source_id: snap.source_id,
      surface: snap.surface,
      watched_ms: snap.watched_ms,
      completed: snap.completed,
      liked: snap.liked,
      saved: snap.saved,
      replay_count: snap.replay_count,
    };
  }
}
