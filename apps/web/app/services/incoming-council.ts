import type { SupabaseClient } from "@supabase/supabase-js";
import { civicToday } from "../lib/council-terms";
import { getCouncilTerms } from "./council-terms";

export interface IncomingCouncil {
  termId: number;
  startDate: string;
  preliminary: boolean;
  members: {
    id: number;
    name: string;
    slug: string | null;
    image_url: string | null;
    role: string;
  }[];
}

/** A small roster query only: no attendance, ballots, or meeting history. */
export async function getIncomingCouncil(
  supabase: SupabaseClient,
  municipalityId: number,
  today = civicToday(),
): Promise<IncomingCouncil | null> {
  const terms = await getCouncilTerms(supabase, municipalityId);
  const term = terms.filter((term) => term.start_date > today && term.election_id)
    .sort((a, b) => a.start_date.localeCompare(b.start_date))[0];
  if (!term) return null;

  const { data: election, error: electionError } = await supabase.from("elections")
    .select("election_date,results_status")
    .eq("id", term.election_id!).single();
  if (electionError) throw electionError;
  if (!election || election.election_date > today || !["preliminary", "official"].includes(election.results_status)) return null;

  const { data, error } = await supabase.from("memberships")
    .select("role,start_date,end_date,person:people!inner(id,name,slug,image_url),organization:organizations!inner(municipality_id,classification)")
    .eq("council_term_id", term.id)
    .eq("organization.municipality_id", municipalityId)
    .eq("organization.classification", "Council")
    .lte("start_date", term.start_date)
    .or(`end_date.is.null,end_date.gte.${term.start_date}`);
  if (error) throw error;
  const members = (data || []).map((row) => ({
    ...(row.person as unknown as IncomingCouncil["members"][number]),
    role: row.role,
  })).sort((a, b) => Number(b.role === "Mayor") - Number(a.role === "Mayor") || a.name.localeCompare(b.name));
  if (!members.length) return null;
  return { termId: term.id, startDate: term.start_date, preliminary: election.results_status === "preliminary", members };
}
