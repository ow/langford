import type { SupabaseClient } from "@supabase/supabase-js";

/**
 * AI-answer sources carry numeric meeting_id / bylaw_id / matter id. Attach
 * the matching slugs (meeting_slug, bylaw_slug, matter_slug) so citation
 * links (lib/source-links.ts) can use slug URLs. Mutates and returns the
 * array; on any lookup failure the sources are returned unchanged (links
 * fall back to ids, which 301 to the slug URL).
 */
export async function attachSourceSlugs<T extends Record<string, any>>(
  supabase: SupabaseClient,
  sources: T[],
): Promise<T[]> {
  if (!sources?.length) return sources;
  const meetingIds = new Set<number>();
  const matterIds = new Set<number>();
  const bylawIds = new Set<number>();
  for (const s of sources) {
    if (s?.meeting_id && !s.meeting_slug) meetingIds.add(Number(s.meeting_id));
    if (s?.type === "matter" && s.id && !s.matter_slug) matterIds.add(Number(s.id));
    if (s?.bylaw_id && !s.bylaw_slug) bylawIds.add(Number(s.bylaw_id));
  }

  const lookup = async (table: string, ids: Set<number>) => {
    if (ids.size === 0) return new Map<number, string>();
    const { data, error } = await supabase.from(table).select("id, slug").in("id", [...ids]);
    if (error) return new Map<number, string>();
    return new Map<number, string>((data || []).map((r: any) => [Number(r.id), r.slug]));
  };

  try {
    const [meetings, matters, bylaws] = await Promise.all([
      lookup("meetings", meetingIds),
      lookup("matters", matterIds),
      lookup("bylaws", bylawIds),
    ]);
    for (const s of sources as Record<string, any>[]) {
      if (!s) continue;
      if (s.meeting_id && !s.meeting_slug) s.meeting_slug = meetings.get(Number(s.meeting_id)) ?? null;
      if (s.type === "matter" && s.id && !s.matter_slug) s.matter_slug = matters.get(Number(s.id)) ?? null;
      if (s.bylaw_id && !s.bylaw_slug) s.bylaw_slug = bylaws.get(Number(s.bylaw_id)) ?? null;
    }
  } catch {
    // Links fall back to ids.
  }
  return sources;
}
