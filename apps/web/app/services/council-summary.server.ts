import { getSupabaseAdminClient } from "../lib/supabase.server";
import { civicToday } from "../lib/council-terms";
import type { AttendanceSummary } from "../lib/attendance-evidence";
import type { Person, Membership } from "../lib/types";
import { getCouncilTerms } from "./council-terms";
import { publicData } from "./public-data-cache.server";

/** Public roster plus SQL evidence totals. Raw attendance/source notes stay in Postgres. */
export function getPublicCouncilSummary(municipalityId: number) {
  const today = civicToday();
  return publicData(`council-summary:${municipalityId}:${today}`, async () => {
    const supabase = getSupabaseAdminClient();
    const { data: council, error: councilError } = await supabase.from("organizations")
      .select("id").eq("classification", "Council").eq("municipality_id", municipalityId).single();
    if (councilError) throw councilError;
    if (!council) throw new Error("Council org not found");
    const [roster, summaries, terms] = await Promise.all([
      supabase.from("people").select("id, name, slug, is_councillor, image_url, council_service_history:meta->council_service_history, in_memoriam:meta->in_memoriam, memberships(id, organization_id, role, start_date, end_date, organization:organizations(name, classification))")
        .eq("memberships.organization_id", council.id),
      supabase.rpc("council_attendance_summaries", { p_municipality_id: municipalityId, p_as_of: today }),
      getCouncilTerms(supabase, municipalityId),
    ]);
    if (roster.error) throw roster.error;
    if (summaries.error) throw summaries.error; // Never turn a missing migration/error into zero attendance.
    const people = (roster.data || []).filter(person => person.memberships?.some((membership: any) => membership.organization_id === council.id)) as unknown as (Person & { memberships: Membership[] })[];
    const stats: Record<string, Record<number, AttendanceSummary>> = {};
    for (const term of terms.length ? terms.map(term => ({ key: String(term.id), sqlKey: String(term.id) })) : [{ key: "current", sqlKey: "all" }]) {
      stats[term.key] = {};
      for (const person of people) {
        const row = summaries.data?.find((row: any) => row.person_id === person.id && row.term_key === term.sqlKey);
        if (!row) throw new Error("Incomplete council attendance summary");
        const { total, attended, absent, unknown, verified, recorded, rate } = row;
        if (![total, attended, absent, unknown, verified, recorded].every(value => Number.isSafeInteger(value) && value >= 0)
          || total !== attended + absent + unknown || recorded !== attended + absent || verified > recorded
          || !(rate === null || Number.isInteger(rate) && rate >= 0 && rate <= 100)) throw new Error("Invalid council attendance summary");
        stats[term.key][person.id] = { total, attended, absent, unknown, verified, recorded, rate };
      }
    }
    return { people, terms, today, stats };
  });
}
