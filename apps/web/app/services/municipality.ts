import type { SupabaseClient } from "@supabase/supabase-js";
import type { Municipality } from "../lib/types";

const cache = new Map<string, { data: Municipality; expires: number }>();

export async function getMunicipality(
  supabase: SupabaseClient,
  slug = "langford",
): Promise<Municipality> {
  const cached = cache.get(slug);
  if (cached && cached.expires > Date.now()) return cached.data;
  const { data, error } = await supabase
    .from("municipalities")
    .select(
      "id, slug, name, short_name, province, classification, website_url, rss_url, contact_email, map_center_lat, map_center_lng, ocd_id, meta, created_at, updated_at",
    )
    .eq("slug", slug)
    .single();

  if (error || !data) {
    throw new Error(`Municipality not found: ${slug}`);
  }

  cache.set(slug, { data: data as Municipality, expires: Date.now() + 60_000 });
  return data as Municipality;
}
