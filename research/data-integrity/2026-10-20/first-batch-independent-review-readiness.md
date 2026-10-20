# Independent review and next finite source cohort

## PR #2 review result

One independent reviewer examined PR #2 at `47fd1e437df93bf907277b08be1d70aac0b7830b`, the private 18-target proposal, actual own formal frames for all 14 ballots, the four non-ballots, and full frozen before/after evidence. The reviewer independently re-extracted the eight target minutes with native `pdftotext` and obtained exactly the cached clean text. No database action, new OCR, paid API, broad source scan, merge, or deployment occurred.

The review found one **P1 in the code**, not in the proposed 18 corrections. An incidental extension reference could consume a subsequent operative extension:

> THAT Council direct staff to review the need for unanimous consent to extend public participation; AND THAT Council extend the meeting until 11:00 pm.

The first PR revision incorrectly inferred a complete ballot. The fix checks each `extend` occurrence independently, so a reference cannot hide a later action. The exact source-loader/merge regression was RED before the change and GREEN afterward. The same independent reviewer inspected the narrow correction and reproduced the required `special_voting_threshold_needs_validation` result with zero choices. No other substantive finding remained in this bounded review.

Root final validation passed **219 tests**. The corrected guard is `e253524ad7e79a07e3351184d26e8853769936d095b681a6b28e9ae70a084af9`. All 1,844 full selected replay result payloads are exactly equal to the previously reviewed outputs; only the runtime binding changes. That includes all 1,348 existing complete ballots and the original 496 targets. Thus the first-batch outcome remains **14 ballot candidates / 98 inferred choices + 4 non-ballot classifications + 478 holds**. The original reviewed proposal is retained; a separately versioned v2 changes the guard binding and records review lineage without changing any of the 18 target payloads.

Independent report SHA: `259039dbea1ebd49c792ab9de1dc3356c7f641261b619e434694bb529df99eac`.
Reviewed v2 exact proposal SHA: `f2efac23268a90cec8c58a68f6365b0af41c6549de3a3e0529a89929750d8309`.
The local full report and proposal stay in the task's `repair-private` folder; the public evidence JSON contains minimized hashes and scope facts.

## Count reconciliation

The latest verified live receipt is still **2026-10-20 01:32:42 UTC**, not a new database observation. No proposed correction has been applied.

| Scope | Complete ballots | Choices in complete ballots |
|---|---:|---:|
| Current term, starting 2022-11-07 | 1,223 | 8,253 |
| Older Langford meetings, 2020-03-19–2022-09-06 | 125 | 781 |
| All-history preservation replay | **1,348** | **9,034** |

The current-term **8,275 total choice rows** also include 22 partial choices. The entire database has 9,057 rows, including 23 partial choices across all dates. Therefore 1,348 is the regression/preservation corpus, not a competing current-term coverage count.

If the first batch is later separately executed, hypothetical current-term accounting becomes **1,237 complete, 478 held ballot targets, four non-ballot outcomes**, with 8,373 total current-term choices. Until then, report **1,223 complete / 496 unresolved** as the latest verified live state.

## Next source cohort: proposals only

The existing exact-body proposal and two prior source reviews were reused. For only these three records, current frozen full rows and all 50 meeting claim projections match the reviewed corpus; three original PDFs and four existing native clips rehash correctly. Exact body/envelope spans, own CARRIED outcomes, heading/action identity, and both-direction ownership ledgers remain bound. No parser recovery, ordinal shift, source-store enrollment, identity admission, or text update was performed.

| Motion / meeting | Proposed correction | Text length before → after | Counterfactual ordinary gate |
|---|---|---:|---|
| 988 / 49 | Restore both numbered bylaw-reading clauses | 238 → 296 | Pass; 6 choices |
| 3174 / 318 | Keep “777 Station Avenue” in heading context rather than append it to the formal body | 115 → 107 | Pass; 7 choices |
| 2443 / 238 | Restore all reporting clauses, including 3.7.1(a–d) | 308 → 806 | Pass; 6 choices |

These **19 counterfactual choices are not admitted ballots**, and the three records still belong to the 478 first-batch holds. Existing vote counts are zero for each. Existing metadata is SQL NULL, preserved exactly in the before rows. All three active embeddings are non-null; a text restoration would require a separately reviewed SQL-NULL vector update while retaining exact old vectors privately for rollback. No new embeddings or vector transfer is proposed.

`next-three-source-evidence-summary-v1.json` records source URLs/hashes, exact before-row hashes, before/after text lengths and counterfactual gates. The full private evidence proposal includes the exact proposed bodies, old full rows/vectors, own source spans, ledger hashes, current/shadow claims and complete counterfactual results. Full proposal SHA: `83034a3d252cdb2eea058684493e4c34526893902de68b4b9baf52796f458c65`.

The separate source-hierarchy negative 3008 and unowned participation row 2441 remain held. They are not alternatives to these three proposals and were not retried or repaired.

## Exact readiness boundary

**First batch:** independent code/source scope review is complete and its P1 is closed. The 18-target correction payloads are source-supported and unchanged. This is ready for parent review of the corrected PR and bounded executor preparation; it is **not ready for an immediate live write**. Remaining execution gates are a fresh read-only capture of only the target/claim/policy context, strict target CAS, a separately reviewed idempotent executor, receipt-owned rollback rehearsal, and independent after/rollback readback. No fresh capture, executor, rehearsal or live readback was attempted or denied here.

**Next three:** exact source/body evidence and shadow gate checks are ready as proposals. Live text/vector/history mutations, source identity admission and any later ballot admission are still held. A later exact restoration plan must preserve full old rows, vectors, SQL-NULL metadata, IDs, keys, ordinals and competing claims; verify committed source text independently; and only then reevaluate ballots from the actual committed state. Do not apply the counterfactual choice payloads directly.

No broader census rescan is needed to decide these two bounded scopes. All other cases retain the existing explicit evidence holds, with no automatic retries or recurring schedule.
