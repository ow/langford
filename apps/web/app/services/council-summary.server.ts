import { getSupabaseAdminClient } from "../lib/supabase.server";
import { civicToday } from "../lib/council-terms";
import { calculateAttendance, getRawPeopleData } from "./people";
import { getCouncilTerms } from "./council-terms";
import { publicData } from "./public-data-cache.server";

/** Precompute the same per-term evidence summaries; don't send raw source notes to every visitor. */
export function getPublicCouncilSummary(municipalityId: number) {
  const today = civicToday();
  return publicData(`council-summary:${municipalityId}:${today}`, async () => {
    const supabase = getSupabaseAdminClient();
    const [raw, terms] = await Promise.all([getRawPeopleData(supabase, municipalityId), getCouncilTerms(supabase, municipalityId)]);
    const ranges = terms.length ? terms.map(term => ({ key: String(term.id), start: term.start_date, end: term.end_date }))
      : [{ key: "current", start: "0001-01-01", end: null }];
    const stats = Object.fromEntries(ranges.map(range => [range.key, Object.fromEntries(raw.people.map(person => [person.id,
      calculateAttendance(person, raw.meetings, raw.attendance, raw.councilId, {
        start: range.start, end: range.end && range.end < today ? range.end : today,
      }),
    ]))]));
    return { people: raw.people, terms, today, stats };
  });
}
