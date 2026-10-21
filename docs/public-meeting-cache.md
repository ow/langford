# Public meeting response cache

The Worker uses Cloudflare's Cache API for a small public archive surface:
`/meetings/YYYY-MM-DD-slug`, its `/documents` list and `/documents/<id>` viewer, plus their React Router
`.data` representations. The date must be at least 48 hours old. This does not
cache markdown, meeting indexes, matters, search,
general APIs, admin pages, or future/recent meetings. The explicit text API
exception below now shares the same admission/storage guard.

Only GET requests on `https://openlangford.ca` without authorization qualify.
Cookie-free requests and requests carrying only the configured PostHog project's
exact analytics cookie (`ph_<project-key>_posthog`, using the SDK's token escaping)
may use the same anonymous cache. The Worker removes that Cookie header from the
request passed to React Router, so analytics identifiers cannot become server
loader data. The browser keeps the original cookie and its analytics behavior.
Every other cookie bypasses, including Supabase sessions and chunks, PKCE cookies,
unknown consent cookies, other PostHog projects and any mixture of those with the
allowed cookie. Missing PostHog configuration permits no cookie exception.

Evidence: `PostHogProvider` initializes analytics only in client-side effects,
uses the default persistence name, and renders nothing. The installed SDK derives
that exact cookie name in `posthog-persistence.js`. No application server loader
reads PostHog or consent cookies; the only server cookie consumer is Supabase SSR.
There is no app consent-banner cookie to allow; PostHog consent defaults to local
storage. Do not broaden this to `ph_*`, `sb_*`, all consent cookies or arbitrary
cookies without rechecking these consumers and extending the isolation tests.

Range/conditional requests, explicit cache bypass headers and unknown queries
also bypass. The sole accepted query is React Router's `_routes`, restricted
to the root and the matching meeting route. Its exact value stays in the key,
so a partial loader payload can never replace a full navigation payload.

Only status 200 HTML or React Router streams are stored. Errors, redirects,
Set-Cookie, private/no-store/no-cache/zero-age responses and unrecognized Vary
headers bypass storage. The original body, status and other headers are retained.
Delivered cacheable responses use `Cache-Control: private, no-store` so a browser
or downstream proxy cannot reuse an anonymous response after the visitor logs in.
The Worker checks admission before reading its shared cache on every request.

Historical route-only `.data` entries and verified historical transcript/section text
expire after **24 hours**. Historical means at least **30 days old**. Recently held
meetings retain five-minute caching; upcoming meetings are excluded from the page
response cache. Mixed/unknown-date text batches retain five minutes. Text dates
come from the existing query's public meeting relationship, never a client flag.

HTML, full `.data`, root-only and root-inclusive streams retain **300 seconds**
even on historical URLs: their root loader contains current site flags. Historical
route-only data uses only the matching meeting/document loader. All representations
and `_routes` values retain distinct keys.

**Corrections are not automatically invalidated.** Admin edits, calendar imports,
pipeline ingestion and direct SQL do not bump these caches. Without an explicit
refresh, a correction can remain stale for up to **24 hours** after a fill (plus
origin response duration). See the owner procedure below. `Cache-Control: no-cache`
bypasses one request; it neither replaces existing entries nor globally purges them.

## Owner procedure: publish a correction refresh

1. Finish and verify the intended public content correction using the established
   correction workflow. This document does not authorize database writes.
2. Change `apps/web/public-content-version.json` to a fresh unique version, e.g.
   `2026-10-21-correction-2`, and commit it through the normal reviewed main/PR flow.
3. Wait for the existing automatic Cloudflare build/deployment to complete and
   confirm that the new Worker version receives production traffic. Do not run a
   manual Wrangler deployment. Keep a record of the correction and deployed SHA.
4. Probe a known historical route-only `.data` or text selector: expect MISS then
   HIT with the corrected content. Check other relevant selectors/representations.

The key includes **both Worker version and public content version**, separately
from database revisions. The new deployment reads a new namespace in every data
center; it does not depend on a local `Cache.delete`. There is no per-request
revision lookup or new credential/binding. Old entries expire/evict naturally.
A rollback to an old Worker can revive that version's old cached content: after
corrections, publish the rollback code as a fresh build/version with a new content
version rather than activating the old deployment. This is an explicit manual
refresh path, **not an automatic import/correction hook or static publication**.

`X-Public-Meeting-Cache: MISS` identifies a qualifying origin response and
`HIT` identifies a reused response. No header means admission/storage was
bypassed. Cache failures fall through to React Router. Cache API entries are
local to the executing Cloudflare data center; this does not precompute the
archive or promise a hit for a new region or after eviction.

Hits avoid loader queries, response serialization and SSR, but the Worker still
runs its admission code. Cache misses and visitors with session/unknown cookies still need
normal compute headroom. This is not a guarantee of fitting a 10 ms Free CPU
allowance, and it does not change the account plan or configured CPU limit.

Meeting detail queries omit transcript and report-section text that the page
already loads through `/api/meeting-text`. Explorer and speaker-review callers
keep the existing full-text default. This reduces database transfer/parsing on
misses without changing the page's public loader payload or deferred text API.

The efficiency pass also admits `/api/meeting-text` JSON responses for validated
transcript/section selectors. Only these public text API requests qualify; unknown,
repeated, malformed or oversized selectors are rejected. Empty text and error responses
are not stored. The API uses the dated TTL policies above, the same version namespace, auth/cookie
exclusions and private/no-store delivery as the archive pages. See
[public-data-efficiency.md](public-data-efficiency.md) for public DTO caching,
on-demand text loading and the nested metadata freshness bound.

## Speaking summaries and research watchers

Profile and comparison speaking rankings, meeting trends and topic summaries now
use the same public data cache. Keys include municipality, person (except shared
rankings), and both date bounds. Only explicit public aggregate fields are stored.
An end date at least 30 days old uses the historical 24-hour policy; unbounded,
current and recent periods use five minutes. Existing admission rules still bypass
sessions, authorization and unknown cookies; only the configured analytics cookie
is admitted. Cache eviction or another Cloudflare location may require a cold read.
The correction-refresh procedure above applies to these summaries too.

The research CLI's `--watch-queue` mode checks small job ID/status rows every
`--refresh-interval` (120 seconds by default), reusing bulk minutes/transcripts
while those jobs are unchanged. Job completion/replacement triggers a fresh load.
`--data-refresh-interval` bounds reuse to 1800 seconds by default, so corrections
made outside that queue appear on the first poll after 30 minutes (normally up to 32 minutes, plus query/report time).
Restart the command for immediate refresh, or pass `--data-refresh-interval 0`
to reload source text every poll. Local reviewed-speaker files are reread every
poll. This cache exists only in that process: it neither persists a dataset nor
changes one-shot exports, source records or recovery snapshots.
