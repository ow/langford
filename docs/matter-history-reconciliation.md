# Matter history reconciliation

## Failure and scope

The previous eligibility gate recognized words such as bylaw, permit and policy,
but rejected early named instruments whose titles did not contain those words.
The current stored input for June 29's `Proposed Parks DCC Rates` fails that old
rule. A read-only sample of the 700 most recent unassigned Langford items since
2024 found 652 generic/procedural rejections, 44 weak-title rejections and four
already eligible items. This diagnoses the current rules against stored inputs;
it does not prove the exact code/model input used at each original ingestion.

Examples rejected by the previous gate:

| Item | Date | Title |
| --- | --- | --- |
| 6651 | 2026-08-17 | Draft Climate Action Plan |
| 6652 | 2026-08-17 | Draft Housing Strategy |
| 1498 | 2026-06-15 | Arts & Culture Strategy |
| 2271 | 2026-06-01 | Economic Development Strategy |
| 2658 | 2026-02-17 | Parks and Trails Master Plan — Adoption Consideration |
| 1369 | 2026-06-29 | Proposed Parks DCC Rates |

The new rule admits a qualified instrument in the **title** (plan, strategy,
program, rates and similar instruments). Generic/procedural gates still run
first. Bare `Draft Plan`, `Program Update`, `Proposed Rates`, generic annual
reports and public-participation containers remain excluded. An incidental
instrument in a summary does not qualify a generic title. Seventeen sampled
items become eligible; that is not seventeen verified repairs. Eligibility also
affects future matter creation through the existing ingest matcher/resolver.

## Recovery is stricter than eligibility

The new `matter-history` stage runs after document relinking and before summaries.
It revisits unassigned items for affected matters and their existing one-hop
same-initiative neighbours. Automatic assignment requires a unique exact title
(after removing a trailing minute estimate), the same municipality, agreement on
explicit bylaw identities and an occurrence inside the matter's existing dated
interval. It never creates or merges matters or replaces an existing owner.
The write also guards the planned item title and meeting ID. Empty post-ingest
focus is a no-op; an unscoped manual backfill must be explicitly requested.
Ambiguous and unmatched candidates are reported for review, not guessed.

Post-ingest mention linking also revisits earlier mixed-topic records for
focused matters whose first recorded dates are in that import. Established
matters do not trigger this extra backward scan on every later update. Existing
similarity/confidence gates remain; municipalities cannot cross-match.

Accepted mentions are separate, attributed summary context. Normal generation
uses owned-only inputs for status/status lines/headlines and a separate
mention-enriched pass for descriptive fields when needed. Newly persisted
mentions trigger a context-only refresh, preserving lifecycle fields. This can
add a model pass to normal summary batches containing mentions; no live model
runs were performed for this PR.

The public chronology includes direct records/mentions of directly related
matters with an owning-matter label. It does not traverse related-of-related
matters, change ownership or redefine the current proceeding's dates. Story
queries paginate. Direct records take precedence over repeated background
references. The date label now says `This matter recorded from` rather than
suggesting the initiative's first announcement is established.

## Reviewed read-only parks dry-run; not applied

```sh
cd apps/pipeline
uv run python main.py --stage matter-history --target 1685 --since 2022-10-01 --dry-run
```

The final read-only planner against Langford project `zxcvifwkaxtdfpanlwtl`
proposes exactly one ownership assignment:

- Item **1369**, meeting **50**, **2026-06-29**, `Proposed Parks DCC Rates
  (approx. 30 min)` → existing proposal matter **208**.
- Reason: unique exact title inside its existing dated interval.
- Applied: **zero**. No bylaw mergers or new matters.
- Forty-six eligible items in the bounded city/date read have no exact candidate
  inside this targeted matter/neighbour scope. These are untouched audit
  findings, not 46 verified omissions from the parks initiative.

Do not run the non-dry historical repair as part of this PR rollout. Before an
approved apply, refresh and review the proposal, preserve affected-record
snapshots, and restrict execution to the reviewed item/owner pair. Refresh
summaries for changed owners afterwards. If a correction affects existing
public caches, follow `public-meeting-cache.md`'s correction-refresh procedure.

## Explicit remaining gaps

No historical records or generated summaries have been repaired by this PR.
The June presentation is still unassigned until that reviewed repair is applied.
Other early proposals do not gain owners merely because they are now eligible.

The 2022 Parks DCC predecessor (matter 1126, Bylaw 2024) remains separate from
the 2026 proceeding (matter 1685, Bylaw 2291). No predecessor edge is invented.
February budget references and July 14 consultation material are already in
ingested documents, but this release does not extract new dated events from
attachments. A July 14 event described in a July 20 report must retain both
dates and its quote/source; it must not be silently dated July 20 or guessed
into the timeline. This needs a separately reviewed event representation.
The UI is a chronology of linked records, not a completeness guarantee.

## Policy stages and coverage review (follow-up)

Draft presentations and decisions can have different titles (for example,
`Draft Housing Strategy (Approx. 45 min)` and `Adoption of the Housing Strategy`).
The matcher now compares an exact qualified plan/strategy subject after removing
only known stage wrappers and time estimates. Subject words and explicit years
remain part of identity. A unique same-year target without a legal identifier can
be reused without a model call. Unknown dates, ambiguous targets, a possible
cross-year continuation, and legal identifier conflicts remain unassigned for
review. Procurement, consultant scopes, implementation and amendments stay
separate, including when an address or civic-entity cluster is shared.

The historical reconciliation stage uses the same policy identity. It still
requires the occurrence to fall within the existing proceeding's dated interval
before automatically assigning historical ownership. Earlier/later dates are
review findings, not silently expanded history. It reports `new_proceedings` with
source agenda IDs when no proceeding exists; it does not create historical
proceedings automatically. Ordinary ingestion creates an eligible new proceeding
when there is no existing candidate. Post-ingest missing-proceeding findings are
limited to imported meetings, including imports with no owned matters.

`decision_review` flags substantive adoption items with no stored outcome. A
heading is not evidence that a motion carried: failed/withdrawn decisions count
as recorded outcomes, and unknown results remain unknown. Findings require the
original minutes before repair. This is a review signal, not a completeness
certificate or permission to replay a whole meeting.

The signed June 20, 2022 original is already handled across its page break by the
current native-PDF loader. The missing parks adoption is legacy decision coverage,
not a reproduced current parser defect. The original is document3364, section
13.18, printed pages18–19. A bounded repair must preserve the separate 2022 and
2026 bylaws and add only the reviewed decision; other source decisions require
their own source-to-record reconciliation. Source-refresh receipts, document
availability, decision coverage and matter association are separate measures.
