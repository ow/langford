# Council terms and election transitions

Elections, council terms, and service memberships represent different events.
An election result identifies a winner; the person starts serving on their
membership start date. Re-elected or returning people keep their existing person
ID and receive a separate membership for each term. Votes/transcripts stay linked
to the original person and meeting date.

`council_terms` records verified tenure dates and links a municipality to its
election. Memberships optionally link to that term and retain their actual start
and departure dates. Dates are inclusive; a term ending November 1 and another
starting November 2 do not overlap. Unknown future end dates remain null.

The shared rules in `app/lib/council-terms.ts` use the America/Vancouver civil
date. A future membership is upcoming, not current. Resignations and gaps between
separate periods of service must not be merged into continuous tenure.

## Langford 2026 transition

Migration `46-01-council-terms-and-langford-2026-election.sql` records:

- 2022 term: November 7, 2022 through November 1, 2026.
- Incoming term: scheduled to begin November 2, 2026; end date unknown.
- October 17, 2026 election: 18 candidates, seven preliminary winners.
- Existing person IDs reused for returning candidates; earlier departures kept.

The city election page and city-linked CivicInfo results are cited in the SQL.
The official 2022 inaugural minutes establish the historical start date. The
2022 election has term metadata only; candidate results have not been imported.

When certified results are published, compare them with the preliminary snapshot,
update any differences, and mark the election `official` with its declaration
source URL. Verify the actual inauguration occurs as scheduled. This is a reviewed
data-maintenance step, not an automatic inference from the calendar or an AI
transcript. The preliminary seed deliberately does not overwrite certified results.

## UI and search

The council page defaults to the council serving today. Its selector includes
incoming and recorded past terms. People with no meetings still appear in the
roster; incoming members do not receive zero-percent attendance grades.
Profiles keep a service timeline; meeting roles use the membership on the meeting
date. Voting alignment and comparisons use verified tenure dates and actual
membership intervals, including service gaps.

Keyword search optionally filters by a verified term and intersects existing time
filters. AI policy answers still retrieve across all terms, explicitly labeled
when a keyword term filter is selected. Questions about officeholders receive
dated roster context; a recorded incoming winner must not be called the current
officeholder before taking office. This does not replace the separate evidence,
quality, caching, and spending-control work identified in the search review.
