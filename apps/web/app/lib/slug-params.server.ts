import type { SupabaseClient } from "@supabase/supabase-js";
import { redirect } from "react-router";

type SlugTable = "meetings" | "matters" | "bylaws" | "elections";

export type ResolvedSlugRow = { id: number; slug: string };

/**
 * Resolve a `:id` route param that should be a slug.
 *
 * - all-digit param (legacy id URL): look the row up by id and 301 to
 *   `buildPath(row)` + the original query string.
 * - otherwise: look up by slug; 404 if missing. Old id-prefixed matter/bylaw
 *   slugs ("1665-solid-waste-...") 301 to the current slug via their id.
 *
 * `buildPath` receives the row and should rebuild the full current URL
 * (including any sub-path such as "/explorer" or "/documents/12").
 *
 * With `redirectLegacy: false` the row is returned instead of redirecting,
 * for callers that compute a different final URL (matter aliases).
 */
export async function resolveSlugParam(
  supabase: SupabaseClient,
  table: SlugTable,
  param: string | undefined,
  request: Request,
  buildPath: (row: ResolvedSlugRow) => string,
  notFound = "Not Found",
  { redirectLegacy = true }: { redirectLegacy?: boolean } = {},
): Promise<ResolvedSlugRow> {
  if (!param) throw new Response(notFound, { status: 404 });
  const { search } = new URL(request.url);

  const byId = async (id: number) => {
    const { data } = await supabase.from(table).select("id, slug").eq("id", id).maybeSingle();
    return data as ResolvedSlugRow | null;
  };

  if (/^\d+$/.test(param)) {
    const row = await byId(Number(param));
    if (!row) throw new Response(notFound, { status: 404 });
    if (!row.slug || !redirectLegacy) return row; // no slug yet: serve on the id URL
    throw redirect(buildPath(row) + search, 301);
  }

  const slug = decodeURIComponent(param).toLowerCase();
  const { data } = await supabase.from(table).select("id, slug").eq("slug", slug).limit(1).maybeSingle();
  if (data) {
    const row = data as ResolvedSlugRow;
    if (param !== row.slug && redirectLegacy) throw redirect(buildPath(row) + search, 301);
    return row;
  }

  // Pre-47-10 matter/bylaw slugs were "{id}-{title}".
  const legacy = table === "matters" || table === "bylaws" ? /^(\d+)-/.exec(slug) : null;
  if (legacy) {
    const row = await byId(Number(legacy[1]));
    if (row?.slug && row.slug !== slug) {
      if (!redirectLegacy) return row;
      throw redirect(buildPath(row) + search, 301);
    }
  }
  throw new Response(notFound, { status: 404 });
}

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
