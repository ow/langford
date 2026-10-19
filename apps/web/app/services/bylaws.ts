import type { SupabaseClient } from "@supabase/supabase-js";
import type { Bylaw } from "../lib/types";

export async function getBylaws(supabase: SupabaseClient) {
  const { data, error } = await supabase
    .from("bylaws")
    .select(
      "id, slug, title, bylaw_number, year, category, status, plain_english_summary",
    )
    .order("title", { ascending: true });

  if (error) throw error;
  return data as Bylaw[];
}

export async function getBylawById(supabase: SupabaseClient, id: string) {
  const { data, error } = await supabase
    .from("bylaws")
    .select(
      `
      *,
      matters (
        id,
        slug,
        title,
        status,
        identifier,
        plain_english_summary,
        meta,
        agenda_items (
          id,
          meetings (
            meeting_date
          )
        )
      )
    `,
    )
    .eq("id", id)
    .single();

  if (error) throw error;
  return data as Bylaw;
}
