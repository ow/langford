# AI refactor: before/after quality check (dry run)

Date: 2026-10-19. Model: gpt-6-luna (both runs). No database writes: `refresh_matter_summaries(..., dry_run=True)`, `summarize_participation(..., dry_run=True)`, and local-package boundary detection on a read-only archive PDF.

- **Before**: base commit `11a017d` (prompt-only JSON + regex parse for matter summaries; `json_object` mode for participation; prompt-only JSON array + regex for boundaries).
- **After**: `pipeline.ai` client with strict structured outputs (`MatterSummaries`, `Participation`, `DocumentBoundaries`).

Model output is not deterministic, so wording differs run to run. What matters: same fields, same shapes, comparable content.

## Summary

| Check | Before | After |
|---|---|---|
| Matter 1283 | 3405 Happy Valley Road rezoning · Development/Adopted · 6 headlines | 3405 Happy Valley Road rezoning · Development/Adopted · 6 headlines |
| Matter 41 | Public bins and curbside waste collection · Environment/Active · 1 headlines | Langford waste management options · Environment/Active · 1 headlines |
| Matter 1665 | Residential solid waste collection bylaw · Environment/Adopted · 2 headlines | Residential garbage and organics collection · Environment/Adopted · 2 headlines |
| Participation item 6700 | 16 speakers | 16 speakers |
| Boundaries (953 Walfred Rd rezoning, 18 pp) | p1-16 staff_report; p17-17 appendix; p18-18 appendix | p1-16 staff_report; p17-17 appendix; p18-18 appendix |
| Wall time (matters / participation / boundaries) | 20.0s / 24.3s / 20.6s | 11.7s / 13.0s / 15.5s |

Stored field names and shapes are unchanged: matters write `plain_english_summary`, `category`, `status`, `meta.display_title`, `meta.status_line`, `meta.timeline_headlines` (item id -> headline); participation writes `{overview, speakers: [{who, position, point, topic}]}`; boundaries keep `{title, page_start, page_end, type, agenda_item, summary, key_facts}`.

Also checked live after the change (not compared with the old code): agenda-only `refine_meeting_data` against the strict `MeetingRefinement` schema (API accepted it; 4 planned items), and the provider-PDF fallback path (`pdf_extractor.detect_boundaries` + `extract_content`) on `19203 - 1234 Goldstream Adoption` (one staff_report boundary, p1-3).

## Matter summaries

### Matter 1283

**Before**: *3405 Happy Valley Road rezoning* (Development, Adopted)

> The rezoning allows a subdivision of 13 single-family lots on the eastern part of 3405 Happy Valley Road, accessed by an extension of Vision Way. The existing detached duplex would remain on a larger lot at the western end, with access from Happy Valley Road.

Status line: Rezoning bylaw adopted Mar 18, 2024.

Timeline headlines:

- 4363: Application proposes rezoning for 13 homes and existing duplex
- 3602: First reading given to the rezoning bylaw
- 2787: First reading repeated with the missing property map
- 5867: Second and third readings given to the rezoning bylaw
- 5852: Public hearing held on the proposed 13-lot subdivision
- 4549: Rezoning bylaw adopted

**After**: *3405 Happy Valley Road rezoning* (Development, Adopted)

> The rezoning allows 13 small-lot single-family homes on the eastern part of the 2.2-acre property, plus a larger lot retaining the existing duplex, at 3405 Happy Valley Road. The new homes would be accessed by an extension of Vision Way; qualifying lots are subject to amenity contributions for general amenities and affordable housing.

Status line: Zoning amendment adopted Mar 18, 2024.

Timeline headlines:

- 4363: Application proposes 13 homes and a lot for the existing duplex
- 3602: First reading given to the rezoning bylaw
- 2787: First reading repeated with the missing property map added
- 5867: Second and third readings given to the rezoning bylaw
- 5852: Public hearing held on the proposed rezoning
- 4549: Rezoning bylaw adopted

### Matter 41

**Before**: *Public bins and curbside waste collection* (Environment, Active)

> The city plans to collect public garbage bins more often and replace them with standard designs, while checking whether to contract residential curbside collection for properties with one to four units. The proposed short-term work could cost up to $285,000, including a feasibility study.

Status line: Staff directed to increase bin service and assess curbside collection on Dec 16, 2025; follow-up work remains.

Timeline headlines:

- 5514: Staff directed to improve public bins and assess curbside collection

**After**: *Langford waste management options* (Environment, Active)

> The city plans more frequent pickups and new designs for public garbage bins, while checking whether to provide curbside garbage collection through a municipal contract. The proposed review focuses on homes with one to four units and is intended to address overflowing bins, wildlife risks and the costs of multiple collection providers.

Status line: Staff were directed to increase public-bin service and assess municipal curbside collection on Dec 16, 2025; further work is pending.

Timeline headlines:

- 5514: Staff directed to increase public-bin pickups and assess curbside service

### Matter 1665

**Before**: *Residential solid waste collection bylaw* (Environment, Adopted)

> The bylaw establishes city-contracted garbage and organic waste collection for homes in properties with up to six dwelling units. A 120-litre bin for each service costs $140 per year, or $280 for both, with fees rising 3% annually starting in 2028; the city expects the shared service to save residents money on average and reduce collection traffic.

Status line: Bylaw adopted Oct 5, 2026, with a maximum service rate of $280.

Timeline headlines:

- 6592: Three readings given to the proposed waste collection bylaw
- 6740: Waste collection bylaw adopted with a $280 maximum rate

**After**: *Residential garbage and organics collection* (Environment, Adopted)

> The bylaw establishes municipal garbage and organic-waste collection for properties with up to six dwelling units, replacing the current system of residents arranging service with private providers. The maximum annual charge is $280 for a 120-litre garbage bin and a 120-litre organics bin; the city expects the unified service to save residents money on average and reduce collection traffic and emissions.

Status line: Bylaw adopted Oct 5, 2026, with a maximum service rate of $280.

Timeline headlines:

- 6592: Three readings given to the proposed municipal collection bylaw
- 6740: Bylaw adopted with a $280 maximum service rate

## Participation summary (agenda item 6700)

### Before

> Sixteen residents spoke about the Transportation Master Plan, mainly opposing or raising concerns about the proposed Hoffman Avenue connector and requesting further engagement or transportation alternatives.

| Who | Position | Point | Topic |
|---|---|---|---|
| A resident | opposes | Opposes the Hoffman through connector. | Hoffman Avenue connector |
| Johnny Lang (Hoffman Ave) | concerned | Asks council to explain how opening Hoffman Avenue would calm traffic and present the reasoning to residents. | Hoffman Avenue connector |
| Jay Clays (Hoffman Ave) | opposes | Opposes making Hoffman Avenue a through road because children use the street and park, and the route serves as a multipurpose pathway. | Hoffman Avenue connector |
| A resident (Langford) | concerned | Questions the timing of the Transportation Master Plan and urges safe options for all users while recognizing residents’ reliance on vehicles. | Transportation Master Plan |
| Aaron Miller (Hoffman Ave) | opposes | Opposes the Hoffman connector, citing bedrock excavation, potential blasting damage, and safety risks beside homes and a playground. | Hoffman Avenue connector |
| Lisa Foxall | concerned | Questions the plan’s travel targets and project costs, and calls for balanced transportation options and more engagement with Mill Hill residents. | Transportation Master Plan |
| Mike Morton | asks | Asks council to allow more time and public engagement before approving a long-term plan affecting Hoffman Avenue residents. | Transportation Master Plan |
| Harley Schultz | opposes | Urges planners to inspect Hoffman Avenue’s steep driveways and street conditions before approving the proposed connection. | Hoffman Avenue connector |
| Mark Burfind (Hoffman Ave) | opposes | Opposes the plan, arguing Hoffman’s curves, driveways, and children’s activity make it less suitable for through traffic than Atkins Avenue. | Transportation Master Plan |
| Evan Mills (Mill Hill) | concerned | Says the Hoffman connector will not solve access problems and asks for better highway access, more time, and protection of the neighborhood. | Transportation Master Plan |
| Alex Johnston (Hoffman Ave) | mixed | Supports several plan improvements but opposes the Hoffman connector and asks council to remove it or consult residents on alternatives. | Transportation Master Plan |
| L Plomp (Langford) | mixed | Supports approving the plan if council commits to meaningful, direct engagement with affected residents before implementing neighborhood changes. | Transportation Master Plan |
| Andrew Ward (Cornerstone Terrace) | opposes | Opposes opening Hoffman Avenue, citing speeding, stop-sign violations, and risks to children using the street and park. | Hoffman Avenue connector |
| Dax Ryan (Cornerstone Terrace) | concerned | Questions the value of a parallel Hoffman road that would add cost without resolving the nearby intersection issue. | Hoffman Avenue connector |
| Rick Joel (Hoffman Ave) | concerned | Questions the Hoffman routing and bus plans, suggests restoring a former traffic lane, and asks the city to address a property acquisition dispute. | Transportation Master Plan |
| Glenn Sauer (Horner Place) | opposes | Opposes opening Hoffman Avenue, warning that diverted traffic could endanger children and people walking dogs in the neighborhood. | Hoffman Avenue connector |

### After

> Sixteen people spoke about the Transportation Master Plan, especially the proposed Hoffman Avenue connector, traffic safety, public engagement, and transportation priorities.

| Who | Position | Point | Topic |
|---|---|---|---|
| A resident | opposes | Opposes the Hoffman through connector. | Hoffman Avenue connector |
| Johnny Lang (Hoffman Ave) | concerned | Asks council to explain how opening Hoffman Avenue would calm traffic and to present the reasoning to residents. | Hoffman Avenue connector |
| Jay Clays (Hoffman Ave) | opposes | Opposes making Hoffman Avenue a through road, citing its use as a pathway and play area for children. | Hoffman Avenue connector |
| A resident (Langford) | concerned | Questions the timing of the Transportation Master Plan and urges balanced, safe options for all users, including drivers. | Transportation Master Plan |
| Aaron Miller (Hoffman Ave) | opposes | Opposes the connector, citing excavation, blasting, property impacts, and safety risks near homes and the playground. | Hoffman Avenue connector |
| Lisa Foxall | concerned | Questions the plan’s travel-mode target and project costs, and urges balanced transportation planning and more engagement with Mill Hill residents. | Transportation Master Plan |
| Mike Morton (Langford) | asks | Urges council to allow more time and public engagement before deciding on long-term transportation changes affecting Hoffman Avenue residents. | Transportation Master Plan |
| Harley Schultz (Hoffman Ave) | opposes | Opposes the Hoffman connection and urges planners to inspect the steep driveways and street conditions before approving it. | Hoffman Avenue connector |
| Mark Burfind (Hoffman Ave) | opposes | Opposes the plan, arguing Hoffman’s curves, playground, homes, and intersections make it less safe for through traffic than Atkins Avenue. | Hoffman Avenue connector |
| Evan Mills (Mill Hill) | concerned | Questions whether the Hoffman connector solves traffic problems and urges more time, careful use of tax dollars, and safe access to the highway. | Transportation Master Plan |
| Alex Johnston (Hoffman Ave) | mixed | Supports several plan improvements but opposes the Hoffman through road and asks council to remove it or consult residents further. | Transportation Master Plan |
| L Plomp | mixed | Recognizes residents’ concerns and the plan’s urgency, and urges one-on-one engagement before transportation changes are contemplated. | Transportation Master Plan |
| Andrew Ward (Cornerstone Terrace) | opposes | Opposes opening Hoffman, citing speeding, stop-sign violations, and risks to children using the park and street. | Hoffman Avenue connector |
| Dax Ryan (Cornerstone Terrace) | asks | Questions the purpose of a parallel Hoffman road and the expense of building it without a clear traffic benefit. | Hoffman Avenue connector |
| Rick Joel (Hoffman Ave) | mixed | Opposes using Hoffman as a through road and urges better transit access while asking the city to address property impacts in the plan. | Transportation Master Plan |
| Glenn Sauer (Horner Place) | opposes | Opposes opening Hoffman, warning that diverted traffic would endanger children and pets in the long-standing residential neighborhood. | Hoffman Avenue connector |

## Document boundaries (local package, `19205 - 953 Walfred Rd Rezoning Z26-0002`)

### Before

- **p1-16 staff_report**: Staff Report to Sustainable Development Advisory Committee (agenda_item: None)
  - Planning staff report on application Z26-0002 to rezone 953 Walfred Road for a townhouse and apartment development. It reviews the proposal, requested variances, servicing and transportation considerations, charges, and conditions for moving Bylaw No. 2279 forward.
  - key facts: Date: August 31, 2026; Address: 953 Walfred Road; Application: Z26-0002; Proposed rezoning: RR5 to RT3, with a site-specific amendment to permit apartments; Proposal: approximately 17 townhouses and a 3-unit apartment building; Proposed parkland dedication: approximately 280 m²; Inclusionary zoning option: one attainable housing unit or $27,100 cash-in-lieu; Estimated total development cost charges: $208,223.37; Amenity cost charges: $57,950
- **p17-17 appendix**: Appendix A – Site Map (agenda_item: None)
  - Appendix map showing the site associated with the 953 Walfred Road rezoning application.
  - key facts: Related application: Z26-0002; Site: 953 Walfred Road
- **p18-18 appendix**: Appendix B – Location Map (agenda_item: None)
  - Appendix map showing the location of the 953 Walfred Road rezoning application in its surrounding area.
  - key facts: Related application: Z26-0002; Site: 953 Walfred Road

### After

- **p1-16 staff_report**: Staff Report to Sustainable Development Advisory Committee – Bylaw No. 2279 – Application to Rezone 953 Walfred Road (agenda_item: None)
  - Staff report on application Z26-0002 to rezone 953 Walfred Road from Rural Residential 5 (RR5) to Residential Townhouse (RT3), with a site-specific text amendment, to enable a townhouse and apartment development. The report discusses requested variances, site and infrastructure conditions, charges, and options for committee consideration.
  - key facts: Dated August 31, 2026; application Z26-0002.; Applicant: Rachael Sansom of Grayland Consulting Ltd., on behalf of 1509532 BC Ltd.; Property: 953 Walfred Road; 4,773 m²; Lot 3, Section 84, Esquimalt District, Plan VIP86631; PID 027-919-030.; Proposal: approximately 17 townhouse units in four blocks and a three-unit apartment building.; Proposed parkland dedication: approximately 280 m²; proposed public pedestrian trail through the site.; Requested western interior side setback variance: 3.0 m to 1.25 m.; Attainable housing requirement: one unit or $27,100 cash-in-lieu.; Estimated total development cost charges: $208,223.37; amenity cost charges: $57,950.
- **p17-17 appendix**: Appendix A – Site Map (agenda_item: None)
  - Appendix map identifying the subject site for the 953 Walfred Road rezoning application.
  - key facts: Identified as Appendix A in the staff report.
- **p18-18 appendix**: Appendix B – Location Map (agenda_item: None)
  - Appendix location map showing the broader location of the 953 Walfred Road rezoning application.
  - key facts: Identified as Appendix B in the staff report.

