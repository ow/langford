import type { SupabaseClient } from "@supabase/supabase-js";
import { completeVoteCounts } from "~/lib/vote-coverage";
import { embedQuery } from "./ai/index.server";

/** Evidence for RAG: hybrid recall, with keyword-only retrieval if embedding fails. */
export async function searchMotionContext(
  supabase: SupabaseClient,
  { query, after_date }: { query: string; after_date?: string },
): Promise<any[]> {
  let embedding: number[] | null = null;
  try {
    embedding = await embedQuery(query);
  } catch (error) {
    console.error("Motion query embedding unavailable; using keyword search:", error);
  }
  try {
    const { data, error } = await supabase.rpc("hybrid_search_motions", {
      query_text: query,
      query_embedding: embedding ? JSON.stringify(embedding) : null,
      match_count: after_date ? 30 : 15,
      full_text_weight: 1,
      semantic_weight: embedding ? 1 : 0,
      rrf_k: 50,
      date_from: after_date || null,
      date_to: null,
      // The RAG tool currently has no municipality-ID scope.
      filter_municipality_id: null,
    });
    if (error) throw error;
    // The existing RPC can emit zero-score semantic rows for a NULL query vector.
    // Keep only positive finite relevance and preserve RPC order through enrichment.
    const ranked = new Map<number, number>();
    for (const match of data || []) {
      if (Number.isFinite(match.rank_score) && match.rank_score > 0 && !ranked.has(match.id)) {
        ranked.set(match.id, match.rank_score);
      }
    }
    if (!ranked.size) return [];
    let enrich = supabase.from("motions").select(`
      id, meeting_id, text_content, plain_english_summary, result, mover, seconder, meta,
      meetings!inner(id, meeting_date), votes(vote, person_id, people(name))
    `).in("id", [...ranked.keys()]);
    if (after_date) enrich = enrich.gte("meetings.meeting_date", after_date);
    const { data: enriched, error: enrichError } = await enrich;
    if (enrichError) throw enrichError;
    const byId = new Map((enriched || []).map((motion: any) => [motion.id, motion]));
    return [...ranked].flatMap(([id, rank_score]) => {
      const motion = byId.get(id);
      if (!motion) return [];
      const counts = completeVoteCounts(motion);
      return [{ ...motion, rank_score, yes_votes: counts?.yes ?? null, no_votes: counts?.no ?? null,
        vote_count_basis: counts ? "complete_individual_vote_rows" : "incomplete_or_invalid_individual_vote_rows" }];
    });
  } catch (error) {
    console.error("Hybrid search for motions failed:", error);
    return [];
  }
}
