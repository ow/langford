# Public data reuse and transfer limits

The Worker explicitly stores **public JSON computations in Cloudflare's existing Cache API**.
No R2/KV binding, paid service, new credential, database migration, or precompute job is required.
This is demand-filled caching, not a build-time export of the whole website.

## What is shared

- Home summaries and incoming council: municipality, civic day and relevant metadata in the key.
- Matters list and participant/coverage aggregates: municipality in the key. `computed_cache`
  database rows are no longer read or written for these computations.
- Annual meeting lists/stats and history date bounds: municipality and selected year where relevant.
- Council list: public people and compact attendance totals per term. Raw attendance notes/history
  stay on the server. The existing evidence calculation still determines present, absent, unknown,
  conflicting, verified and legacy-recorded attendance; no evidence is invented or reclassified.
- `/api/meeting-text`: explicit anonymous response caching for full transcript words or bounded
  document-section selectors. Selectors/representations are distinct from page and navigation caches.

The public-data helper caches explicit DTOs, **never whole root/session responses**. Each loader still
renders its own response, with its own user data and headers. Admission rejects Authorization,
Supabase/unknown/consent cookies, conditional/range and explicit cache-bypass headers. Only the exact
configured PostHog cookie is allowed alongside cookie-free requests, as in the existing archive cache.
Auth/bypass requests do not join anonymous in-flight computations. Public home data uses the fixed
anonymous Supabase client; other new cached computations use fixed public projections, no request
session client. No user-dependent computation belongs in `publicData()`.

## Freshness and failure

Every edge entry expires after **300 seconds** and includes the Worker deployment version and a
schema-specific data key. Deploying or rolling back namespaces all entries. Ingestion and edits
without a deployment appear after expiry and the next origin fill. Nested municipality/council-term
metadata already has a 60-second isolate cache: roster/metadata freshness can therefore approach
**six minutes**, plus origin fetch duration. This is not immediate ingest-triggered invalidation.
For an urgent correction, publish a new deployment rather than relying on TTL.

Cache API entries are local to the Cloudflare data center and can be evicted. Misses still query
Supabase. Concurrent summary fills coalesce within one isolate. No cross-region hit or free-quota
fit is promised. Thrown errors, incomplete home summaries and failed meeting-stat computations
are not stored. Cache failures fall through to origin; no stale partial result is invented.

`X-Public-Data-Cache` reports the distinct HIT/MISS/BYPASS states of public DTO lookups in that
request. `X-Public-Meeting-Cache` still reports the guarded archive/text **response** cache.
Delivery uses private/no-store to avoid downstream reuse of a page after a session change.
Private/session responses are not themselves placed in a shared response cache.

## Text demand and query scope

Summary-only meeting visits do not request transcript words. Opening the full transcript,
following a transcript hash, selecting the video transcript sidebar or enabling/seeking playback
loads the text, preserving transcript search and captions. The full text is still fetched once
needed; playback-window chunking is not part of this pass. Meeting content remounts on meeting ID
changes so an earlier meeting's playback cannot trigger later summary-only downloads. Failed full
transcript requests offer retry in the transcript drawer.

Document sections fetch only on expansion, in batches of at most 200 unique IDs. Reopening fetches
again through the edge cache instead of retaining an indefinite browser Map. Failures offer retry.
Empty/missing text API results are not cached.

Attendance collection is paginated deterministically and restricted to the relevant Council
organization; relevant source notes and conflicting records remain available for calculation.
Meeting-stat reads filter the **existing RPC output** to shown meeting IDs in bounded batches.
This reduces transferred rows; SQL aggregate CPU savings have not been measured.

## Verification and practical limits

Regression tests exercise DOM demand/navigation/retry, real Supabase-client HTTP selectors,
attendance pagination beyond 1,000 rows, compact evidence-equivalent summaries, origin-call reuse,
municipality/year/deployment separation, auth/cookie bypass, concurrent fills and expiry/corrections.
Fixture transfer savings are not production egress/billing measurements. Organization/project/service
usage attribution still requires the Supabase usage dashboard. Search, individual document HTML,
admin, root auth and other routes have not been broadly cached by this change.
