import type { SupabaseClient } from "@supabase/supabase-js";

async function fetchAllVotesForAlignment(
  supabase: SupabaseClient,
): Promise<any[]> {
  const allData: any[] = [];
  let page = 0;
  const pageSize = 1000;

  while (true) {
    const { data, error } = await supabase
      .from("votes")
      .select(
        "motion_id, person_id, vote, motions(meta, meeting_id, meetings(meeting_date))",
      )
      .in("vote", ["Yes", "No", "Opposed", "In Favour"])
      .order("id", { ascending: true })
      .range(page * pageSize, (page + 1) * pageSize - 1);

    if (error) throw error;
    if (!data || data.length === 0) break;

    // Named-dissent-only recoveries are not complete roll calls and would bias agreement rates.
    allData.push(...data.filter((vote: any) => vote.motions?.meta?.individual_vote_coverage !== "named_only"));
    if (data.length < pageSize) break;
    page++;
  }

  return allData;
}

async function fetchAllMotionsForAlignment(
  supabase: SupabaseClient,
  municipalityId: number,
): Promise<any[]> {
  const allData: any[] = [];
  let page = 0;
  const pageSize = 1000;

  while (true) {
    const { data, error } = await supabase
      .from("motions")
      .select("id, result, meetings!inner(meeting_date, municipality_id)")
      .eq("meetings.municipality_id", municipalityId)
      .order("id", { ascending: true })
      .range(page * pageSize, (page + 1) * pageSize - 1);

    if (error) throw error;
    if (!data || data.length === 0) break;

    allData.push(...data);
    if (data.length < pageSize) break;
    page++;
  }

  return allData;
}

export async function getVotingAlignment(
  supabase: SupabaseClient,
  municipalityId = 1,
) {
  // 1. Get the 'Council' organization ID dynamically
  const { data: councilOrg } = await supabase
    .from("organizations")
    .select("id")
    .eq("classification", "Council")
    .eq("municipality_id", municipalityId)
    .single();

  const councilId = councilOrg?.id;
  if (!councilId) {
    return {
      people: [],
      votes: [],
      motions: [],
      memberships: [],
    };
  }

  const [peopleRes, votes, motions, membershipsRes] = await Promise.all([
    supabase.from("people").select("id, name, image_url, is_councillor"),
    fetchAllVotesForAlignment(supabase),
    fetchAllMotionsForAlignment(supabase, municipalityId),
    supabase
      .from("memberships")
      .select("*, people(id, name, image_url)")
      .eq("organization_id", councilId),
  ]);

  const municipalMotionIds = new Set(motions.map((motion: any) => motion.id));
  return {
    people: peopleRes.data || [],
    votes: (votes || []).filter((vote: any) => municipalMotionIds.has(vote.motion_id)),
    motions: motions || [],
    memberships: membershipsRes.data || [],
  };
}
