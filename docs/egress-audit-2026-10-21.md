# Egress audit: October 21, 2026 (Pacific)

Observed October 22, 2026 around 05:44–05:52 UTC, i.e. October 21 around
22:44–22:52 America/Vancouver (PDT, UTC−07:00). Fresh branch from origin/main
`646931d9758fb43ab08fc687059f081d068dcf20`; no protected historical checkout reset.

## Measured usage and attribution limits

Authenticated [organization usage](https://supabase.com/dashboard/org/graevzstyldjplbqsqbt/usage)
shows **8.513 GB** for October 6–November 6. Selecting Langford
`zxcvifwkaxtdfpanlwtl` also shows **8.513 GB**; the selector lists only Langford.
The daily tooltip initially observed at organization scope reports:

| Dashboard date label | Shared pooler | PostgREST | Other reported services |
| --- | ---: | ---: | --- |
| October 19 | 5.359 GB (86.9%) | 826.067 MB (13.1%) | Auth 991 bytes; functions 83 bytes |
| October 20 | 1.355 GB (77.0%) | 414.165 MB (23.0%) | No additional tooltip categories |
| October 21 | Unavailable | Unavailable | No readable bar/tooltip; **not established zero** |

The dashboard shows hourly refresh messaging and no timezone selector/label.
These are its date labels, **not verified Pacific-midnight aggregates**.
A Pacific October 20 window is October 20 07:00 through October 21 07:00 UTC;
October 21 is October 21 07:00 through October 22 07:00 UTC and was still ongoing.
A reliable local-day comparison needs timestamped usage buckets or a dashboard
with an explicit timezone; this audit does not invent that comparison.

Storage size, Realtime messages/connections and cached egress display zero at the
shown precision. Daily Storage/Realtime egress bytes were not separately exposed.
Do not convert a missing category or rounded total into an exact byte count.
Supabase cached egress measures its CDN, not Cloudflare Worker Cache API hits.
[Supabase's service definitions](https://supabase.com/docs/guides/platform/manage-your-usage/egress)
separate PostgREST and shared pooler traffic; they must not be counted twice.

The website's Supabase SDK uses PostgREST. Local Python/maintenance/research reads
can use the SQL pooler. The October 20 **pooler category is the dominant measured
transport**; it is not proof that one particular script generated those bytes.
PostgREST is shared by website and background SDK callers. No reliable per-client
byte split was available, and request counts cannot provide one.

Bounded read-only `pg_stat_statements` metadata, with 5-second statement limits,
returned cumulative statistics since **September 27 19:23:51 UTC**:

- 46 `SELECT id,motion_id FROM transcript_segments ORDER BY id` calls returned
  8,085,236 rows in aggregate.
- 242 full vote fingerprint reads returned 2,312,329 rows.
- 242 full motion fingerprint reads returned 901,934 rows.
- 82 JSON vote exports returned 740,732 rows; 82 JSON motion exports returned
  305,614 rows. Other bounded historical exports also appear.

These prove repeated reads occurred during the cumulative period. They neither
measure response bytes nor date those calls to October 20/21. No resets, table
exports or new large scans were run for this audit. The historical catchup owner
was sent these limits and asked to reuse snapshots and avoid unchanged rescans.

## What exists versus what is missing

Current main contains real demand-filled Cloudflare caches for home, matters and
council summaries, annual meeting lists, participation/speaking aggregates,
historical meeting/document HTML/navigation and deferred text. Historical
route-only data/text and ended annual lists can live 24 hours; current summaries
and HTML/root-inclusive responses generally live five minutes. Compact SQL
attendance aggregation reduces DB-to-Worker payload on misses.

Production `/` probes at 05:45:26 and 05:46:13 UTC returned
`X-Public-Data-Cache: MISS` then `HIT` from YVR. This confirms deployed demand-cache
behavior on that surface; it is not a site-wide hit ratio, proof of the current
main SHA being deployed, or proof of zero DB reads in root/municipality work.
Compression alone does not avoid a Supabase read; an actual edge hit does avoid
the wrapped computation's queries.

Missing: automatic publication/invalidation when ingestion/corrections complete,
persistent precomputed public read models independent of Worker region/eviction,
and per-job/per-endpoint byte attribution. The existing
[content-version refresh](public-meeting-cache.md#owner-procedure-publish-a-correction-refresh)
is manual. A database update does not automatically advance it.

## Focused change in this PR

Sitemap sections previously paginated catalog reads on every loader invocation.
Production `/sitemaps/documents.xml` returned 933,923 XML bytes with cache headers,
without the public-data reuse header. Those XML bytes are **Worker-to-crawler**
bytes, not measured Supabase egress. Headers alone do not demonstrate Worker
cache storage.

Cache each explicit **public SitemapEntry URL projection** for one hour, keyed by
municipality, section, Worker version and public content version. Keep the same
public visibility filters, pagination and XML renderer. Sessions, Authorization,
unknown cookies and explicit bypass requests use the existing bypass guard. No
user/root response, signed storage link or private document body enters the cache.
The sitemap still resolves municipality metadata (existing 60-second isolate
cache), so this is avoidance of catalog scans, not a promise of zero DB traffic.

Thrown catalog errors are not cached. New publications/corrections appear after
one-hour edge expiry (plus up to 60 seconds for nested municipality metadata) or
an earlier fresh version deployment via the owner procedure. No automatic pipeline
hook is claimed. A warm hit in one data center need not be warm in another.

Regression coverage uses the real Supabase SDK over a controlled HTTP transport:
1,002 extracted document rows across two pages, of which 1,001 belong to a public
meeting. It verifies complete public output, warm avoidance of catalog HTTP
reads, section separation, one-hour expiry, correction-version refresh, session
bypass and retry after failure. The reuse regression fails against the original
service and passes after the change. This is a measured behavioral reduction in
test reads, not a forecast of billing savings or a claim sitemaps caused yesterday's spike.

Validation: `pnpm --filter web typecheck` passed. The web suite passed 498 tests
with four PostgreSQL integration cases skipped because no disposable database was
configured. Worker tests require localhost access. No production database migration
is needed for this change.

## Recommended next architecture and order

1. **Budget background reads first.** Preserve local source snapshots by digest;
   poll compact job state/revision rows, fetch changed meetings/IDs only, and do
   verification aggregates/hashes server-side. Give future jobs descriptive
   `application_name` and track rows/estimated bytes plus their UTC window.
   Do not weaken the catchup's source-integrity or read-back checks. Historical
   catchup coordination is separate from this website-only PR.
2. **Keep PostgreSQL relational source of truth; publish public read models.**
   After a successful verified pipeline batch, record an outbox/revision in the
   same commit boundary. A bounded publisher builds allowlisted, municipality-
   scoped JSON for changed meetings, documents, matters, yearly indexes and
   public aggregates. Never export `SELECT *`, jobs, profiles, auth or admin data.
3. **Publish immutable artifacts and an atomic manifest.** Validate schema,
   counts, public eligibility and source revision before uploading content-hashed
   artifacts to reviewed object storage. Advance a small manifest only after all
   artifacts exist. Serving a manifest revision uses immutable cache keys across
   regions. Cache manifest reads briefly outside Postgres; never query a DB
   revision on every page request. Preserve the prior complete manifest on failure.
4. **Define freshness/invalidation as a pipeline contract.** Changes/deletions
   invalidate dependent yearly/list/aggregate artifacts; public-to-private
   changes need immediate withdrawal, not a day-long TTL. Every correction path,
   admin import and direct repair must enqueue publication or explicitly use the
   existing manual refresh until that integration exists. Rollback publishes a
   fresh manifest revision rather than reviving stale/private data.
5. **Render public pages from those artifacts**, with current root/session state
   separate. Use long immutable caching for historical content, short current
   index TTLs and safe bounded DB fallback while rolling out. Keep keyword/vector
   search dynamic where required, along with auth, subscriptions and admin routes.
   Preserve current canonical URLs and React Router representation isolation.
6. **Measure before extending.** Compare complete same-timezone days after
   telemetry settles, report pooler and PostgREST separately, and sample cache
   HIT/MISS/BYPASS by route alongside job read budgets. The result to seek is
   fewer origin reads and fewer Supabase bytes, not merely smaller browser HTML.

This PR creates no infrastructure, binding, secret, security change or deployment.
The publication architecture above needs a separate reviewed implementation;
this audit does not activate public exports or promise savings for unmeasured routes.
