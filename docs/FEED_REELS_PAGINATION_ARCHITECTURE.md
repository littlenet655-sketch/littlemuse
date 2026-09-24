# Feed/Reels Pagination Investigation — Physical Device 6–9 Item Stop

## Observed symptom

On a physical phone, Feed/Reels can appear to stop after roughly 6–9 items even though the project has a larger curated/social catalog.

## What is already correct

Latest PR #9 mobile code uses:
- TanStack `useInfiniteQuery`
- `getNextPageParam`
- `fetchNextPage`
- `onEndReached`
- near-end viewability prefetch.

Backend `get_feed_page()` correctly slices one materialized session by position cursor and returns `next_cursor` / `has_more`.

Therefore this is not explained by a missing client pagination API alone.

## Root architecture

A feed session is materialized once by:
1. fetching up to 60 curated candidates;
2. fetching up to 60 social candidates;
3. filtering recent impressions;
4. applying parent categories, age, safety, block/mute/discoverability rules;
5. ranking/diversity;
6. deduplicating;
7. persisting only the resulting session items.

The client can only paginate through items that survived into that one session.

If filters reduce the session to 6–9 items, `has_more=false` is technically correct even if the wider database contains more media.

Refresh may also reuse the same still-valid session.

## Required fix

Introduce explicit refill/session-rotation semantics.

Server should tell the client whether:
- the page ended because the current session ended;
- additional eligible content may exist in a new session;
- no eligible content exists under current controls.

Proposed response fields:
- `has_more`
- `next_cursor`
- `session_id`
- `total_in_session`
- `can_refill`
- `exhaustion_reason`

When page/session ends and `can_refill=true`, create a fresh session and continue.

Refresh should be able to force a new session.

Do not weaken:
- block/mute
- parent category controls
- age gates
- moderation state
- relationship authorization.

## Tests

1. 120 eligible curated items → user can scroll past 8, 20, 50, 100.
2. mixed social + curated → no duplicate source keys across pages in one session.
3. first session only 7 after recent filtering but additional eligible catalog exists → refill returns more.
4. truly only 7 eligible items → end state reports NO_ELIGIBLE_CONTENT, no infinite request loop.
5. Reels refill preserves JIT playback and Brain Break counter.
6. refresh starts new session when explicitly requested.
