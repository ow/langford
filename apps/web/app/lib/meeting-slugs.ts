import type { SupabaseClient } from "@supabase/supabase-js";

/**
 * Fill `slugKey` on rows that only carry a meeting id (static JSON, RPC
 * results, computed aggregates) with one batched lookup. Mutates rows.
 */
export async function fillMeetingSlugs<T extends Record<string, any>>(
  supabase: SupabaseClient,
  rows: T[],
  idKey: string = "meetingId",
  slugKey: string = "meetingSlug",
): Promise<T[]> {
  const ids = [...new Set(rows.filter((r) => r?.[idKey] && !r[slugKey]).map((r) => Number(r[idKey])))];
  if (ids.length === 0) return rows;
  const { data } = await supabase.from("meetings").select("id, slug").in("id", ids);
  const byId = new Map<number, string>((data || []).map((m: any) => [Number(m.id), m.slug]));
  for (const row of rows as Record<string, any>[]) {
    if (row?.[idKey] && !row[slugKey]) row[slugKey] = byId.get(Number(row[idKey])) ?? null;
  }
  return rows;
}

/** Copy of a participation history (static JSON) with meeting slugs on its records. */
export async function withMeetingSlugs<T extends { records: { meetingId: number }[] }>(
  supabase: SupabaseClient,
  history: T | null,
): Promise<T | null> {
  if (!history) return history;
  const records = history.records.map((r) => ({ ...r }));
  await fillMeetingSlugs(supabase, records);
  return { ...history, records };
}
