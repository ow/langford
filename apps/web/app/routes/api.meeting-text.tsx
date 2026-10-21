import type { Route } from "./+types/api.meeting-text";
import { parseMeetingTextRequest } from "../lib/meeting-text-request";
import { getSupabaseAdminClient } from "../lib/supabase.server";

/**
 * Text deferred from the meeting page payload:
 *   GET /api/meeting-text?meeting=<id>&kind=transcript          -> { texts: { [segmentId]: text } }
 *   GET /api/meeting-text?kind=sections&ids=1,2,3               -> { texts: { [sectionId]: text } }
 * The meeting page ships timings/titles only; transcripts and report sections run to megabytes.
 */
export async function loader({ request }: Route.LoaderArgs) {
  const url = new URL(request.url);
  const selection = parseMeetingTextRequest(url);
  if (!selection) return Response.json({ error: "Invalid text selection" }, { status: 400 });
  const supabase = getSupabaseAdminClient();
  const texts: Record<number, string> = {};

  if (selection.kind === "transcript") {
    for (let page = 0; ; page++) {
      const { data, error } = await supabase
        .from("transcript_segments")
        .select("id, text_content")
        .eq("meeting_id", selection.meetingId)
        .order("start_time", { ascending: true })
        .range(page * 1000, page * 1000 + 999);
      if (error) return Response.json({ error: error.message }, { status: 500 });
      for (const row of data || []) texts[row.id] = row.text_content || "";
      if (!data || data.length < 1000) break;
    }
  } else {
    const ids = selection.ids;
    if (ids.length) {
      // Report sections are public content already shown on meeting pages.
      const { data, error } = await supabase.from("document_sections").select("id, section_text").in("id", ids);
      if (error) return Response.json({ error: error.message }, { status: 500 });
      for (const row of data || []) texts[row.id] = row.section_text || "";
    }
  }

  return Response.json({ texts }, Object.keys(texts).length ? undefined : { headers: { "Cache-Control": "private, no-store" } });
}
