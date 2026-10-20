# Public meeting response cache

The Worker uses Cloudflare's Cache API for a small public archive surface:
`/meetings/YYYY-MM-DD-slug` and its `/documents` list, plus their React Router
`.data` representations. The date must be at least 48 hours old. This does not
cache individual document viewers, markdown, meeting indexes, matters, search,
APIs, admin pages, or future/recent meetings.

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

Stored entries expire after **300 seconds**. Corrections and ingestion changes
appear within that interval; requests with `Cache-Control: no-cache` bypass
the cache immediately. Each Worker version has a distinct namespace via the
`CF_VERSION_METADATA` binding, so deploying or rolling back a version invalidates
the previous version's entries for the active deployment. For an urgent global
content correction, deploy a new version rather than waiting for the TTL.

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
