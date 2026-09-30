import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchProcessingStatus, redriveProcessing, type ProcessingStatus } from '../api/kidsUpload';
import { useAuth } from '../auth/AuthProvider';
import { invalidateSocialCaches } from '../query/keys';
import { MAX_POLL_ATTEMPTS, MAX_POLL_DURATION_MS, isTerminalStage, processingStage, type ProcessingStage } from './social';

/**
 * Foreground-only bounded processing polling with a manual refresh escape hatch.
 *
 * The hook never invents moderation outcomes: it only surfaces the server's
 * authoritative status/moderation_status. Callers reconcile their local UI
 * against `stage` — a 'blocked' stage means the post must NOT be shown as
 * published anywhere.
 */
export function useProcessingStatus(postId: number | null, active: boolean) {
  const { session } = useAuth();
  const [status, setStatus] = useState('PROCESSING');
  const [moderation, setModeration] = useState<string | null>(null);
  const [retryable, setRetryable] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [attempts, setAttempts] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const [redriving, setRedriving] = useState(false);
  const [redriveError, setRedriveError] = useState<unknown>(null);
  const [result, setResult] = useState<ProcessingStatus | null>(null);
  const attemptsRef = useRef(0);
  const startedAtRef = useRef(Date.now());
  const stage: ProcessingStage = processingStage(status, moderation, retryable);
  const terminal = isTerminalStage(stage);

  useEffect(() => {
    attemptsRef.current = 0;
    startedAtRef.current = Date.now();
    setAttempts(0);
    setStatus('PROCESSING');
    setModeration(null);
    setRetryable(false);
    setError(null);
    setRedriveError(null);
    setResult(null);
  }, [postId]);

  const fetchOnce = useCallback(async () => {
    if (!session || !postId) return null;
    const next = await fetchProcessingStatus(session.token, postId);
    setResult(next);
    setStatus(next.status);
    setModeration(next.moderation_status ?? null);
    setRetryable(Boolean(next.retryable));
    setError(next.error ?? null);
    if (isTerminalStage(processingStage(next.status, next.moderation_status, Boolean(next.retryable)))) {
      void invalidateSocialCaches([postId]);
    }
    return next;
  }, [postId, session?.token]);

  useEffect(() => {
    if (!active || !postId) return;
    attemptsRef.current = 0;
    startedAtRef.current = Date.now();
    setAttempts(0);
    // One reconciliation on foreground also observes a parent's REVIEW decision.
    if (terminal) void fetchOnce().catch(setError);
  }, [active, postId, fetchOnce]);

  useEffect(() => {
    if (!postId || !active || !session || terminal) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    async function tick() {
      if (cancelled) return;
      if (attemptsRef.current >= MAX_POLL_ATTEMPTS || Date.now() - startedAtRef.current >= MAX_POLL_DURATION_MS) return;
      attemptsRef.current += 1;
      setAttempts(attemptsRef.current);
      try {
        const next = await fetchOnce();
        if (cancelled || !next) return;
        const nextStage = processingStage(next.status, next.moderation_status, Boolean(next.retryable));
        if (isTerminalStage(nextStage)) return;
      } catch (reason) {
        if (cancelled) return;
        setError(reason);
      }
      if (attemptsRef.current < MAX_POLL_ATTEMPTS && Date.now() - startedAtRef.current < MAX_POLL_DURATION_MS) {
        timer = setTimeout(tick, Math.min(2000 + attemptsRef.current * 500, 8000));
      }
    }

    void tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [active, fetchOnce, postId, session?.token, terminal]);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try { await fetchOnce(); } catch (reason) { setError(reason); } finally { setRefreshing(false); }
  }, [fetchOnce]);

  /** Ask the server to re-dispatch a failed processing job, then resume polling. */
  const redrive = useCallback(async () => {
    if (!session || !postId) return;
    setRedriving(true);
    setRedriveError(null);
    try {
      await redriveProcessing(session.token, postId);
      // Restart the polling budget so the fresh job gets a full window.
      attemptsRef.current = 0;
      startedAtRef.current = Date.now();
      setAttempts(0);
      setStatus('PROCESSING');
      setRetryable(false);
      setError(null);
      await fetchOnce();
    } catch (reason) {
      setRedriveError(reason);
    } finally {
      setRedriving(false);
    }
  }, [fetchOnce, postId, session?.token]);

  return {
    status,
    moderation,
    error,
    attempts,
    stage,
    terminal,
    refreshing,
    refresh,
    redrive,
    redriving,
    redriveError,
    /** Full authoritative server result (includes media_url/poster_url when ready). */
    result,
  };
}
