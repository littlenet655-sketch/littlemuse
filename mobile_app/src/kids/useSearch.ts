import { useEffect, useRef, useState } from 'react';
import { createSearchGuard } from '../kids/social';

/** Debounced search with cancellation + stale-query protection. */
export function useDebouncedSearch(delayMs = 300) {
  const [raw, setRaw] = useState('');
  const [debounced, setDebounced] = useState('');
  const guard = useRef(createSearchGuard());
  const controller = useRef<AbortController | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => {
      controller.current?.abort();
      controller.current = new AbortController();
      guard.current.next();
      setDebounced(raw.trim());
    }, delayMs);
    return () => clearTimeout(timer);
  }, [raw, delayMs]);

  return {
    raw,
    setRaw,
    debounced,
    guard: guard.current,
    signal: controller.current?.signal,
    cancel: () => controller.current?.abort(),
  };
}
