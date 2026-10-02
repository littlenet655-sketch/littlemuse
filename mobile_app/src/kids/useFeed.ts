import { useInfiniteQuery, type InfiniteData } from '@tanstack/react-query';
import { fetchFeedV2, fetchReelsV2, type FeedPage } from '../api/kidsFeed';
import { useAuth } from '../auth/AuthProvider';
import { kidsKeys } from '../query/keys';
import { mergeFeedPages } from './social';

type PageParam = { cursor: number; sessionId?: string; refillFrom?: string };

/** One authoritative TanStack Query cache for cursor-paginated feed and reels. */
export function useFeed(kind: 'feed' | 'reels', limit = 10, mode: 'for_you' | 'friends' | 'learn' = 'for_you') {
  const { session } = useAuth();
  const query = useInfiniteQuery<FeedPage, Error, InfiniteData<FeedPage, PageParam>, readonly unknown[], PageParam>({
    queryKey: [...(kind === 'feed' ? [...kidsKeys.feed, mode] : kidsKeys.reels), session?.token ?? 'signed-out'],
    enabled: Boolean(session),
    initialPageParam: { cursor: 0 },
    queryFn: async ({ pageParam, signal }): Promise<FeedPage> => {
      if (!session) throw new Error('Sign in required.');
      // The fetch helpers are typed FeedPage, but the runtime payload is
      // server JSON: treat it as unknown and coerce before caching.
      const raw: unknown = kind === 'feed'
        ? await fetchFeedV2(session.token, pageParam.cursor, limit, pageParam.sessionId, mode, signal, pageParam.refillFrom)
        : await fetchReelsV2(session.token, pageParam.cursor, limit, pageParam.sessionId, signal, pageParam.refillFrom);
      // Coerce a malformed payload (null, non-object, or non-array `items`)
      // to an empty page HERE in queryFn: getNextPageParam reads
      // `last.has_more`, so a malformed page cached raw would crash
      // pagination as well as render.
      if (!raw || typeof raw !== 'object' || !Array.isArray((raw as { items?: unknown }).items)) {
        return { ok: true, items: [], next_cursor: 0, has_more: false, session_id: '' };
      }
      return raw as FeedPage;
    },
    getNextPageParam: (last) => {
      if (last.has_more && last.next_cursor != null) {
        return { cursor: last.next_cursor, sessionId: last.session_id || undefined };
      }
      if (last.can_refill && last.session_id) {
        return { cursor: 0, refillFrom: last.session_id };
      }
      return undefined;
    },
  });

  return {
    // Belt-and-braces: queryFn already coerces malformed pages, but a page
    // cached by an older client build could still be malformed. Coerce again
    // here so downstream dedupe/render only ever sees arrays.
    items: mergeFeedPages((query.data?.pages ?? []).map((p) => (p && Array.isArray(p.items) ? p.items : []))),
    sessionId: query.data?.pages[0]?.session_id,
    loading: query.isPending,
    loadingMore: query.isFetchingNextPage,
    refreshing: query.isRefetching && !query.isFetchingNextPage,
    error: query.error,
    hasMore: query.hasNextPage,
    loadMore: () => { if (query.hasNextPage && !query.isFetchingNextPage) void query.fetchNextPage(); },
    refresh: () => void query.refetch(),
    retry: () => void query.refetch(),
  };
}

