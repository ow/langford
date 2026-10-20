import type { Route } from "./+types/api.meeting-text";
import { getSupabaseAdminClient } from "../lib/supabase.server";

/**
 * Text deferred from the meeting page payload:
 *   GET /api/meeting-text?meeting=<id>&kind=transcript          -> { texts: { [segmentId]: text } }
 *   GET /api/meeting-text?kind=sections&ids=1,2,3               -> { texts: { [sectionId]: text } }
 * The meeting page ships timings/titles only; transcripts and report sections run to megabytes.
 */
export async function loader({ request }: Route.LoaderArgs) {
  const url = new URL(request.url);
  const meetingId = Number(url.searchParams.get("meeting"));
  const kind = url.searchParams.get("kind");
  if (kind === "transcript" && !meetingId) return Response.json({ error: "meeting required" }, { status: 400 });
  const supabase = getSupabaseAdminClient();
  const texts: Record<number, string> = {};

  if (kind === "transcript") {
    for (let page = 0; ; page++) {
      const { data, error } = await supabase
        .from("transcript_segments")
        .select("id, text_content")
        .eq("meeting_id", meetingId)
        .order("start_time", { ascending: true })
        .range(page * 1000, page * 1000 + 999);
      if (error) return Response.json({ error: error.message }, { status: 500 });
      for (const row of data || []) texts[row.id] = row.text_content || "";
      if (!data || data.length < 1000) break;
    }
  } else if (kind === "sections") {
    const ids = (url.searchParams.get("ids") || "").split(",").map(Number).filter(Boolean).slice(0, 200);
    if (ids.length) {
      // Report sections are public content already shown on meeting pages.
      const { data, error } = await supabase.from("document_sections").select("id, section_text").in("id", ids);
      if (error) return Response.json({ error: error.message }, { status: 500 });
      for (const row of data || []) texts[row.id] = row.section_text || "";
    }
  } else {
    return Response.json({ error: "kind must be transcript or sections" }, { status: 400 });
  }

  return Response.json({ texts }, { headers: { "Cache-Control": "public, max-age=300, s-maxage=3600" } });
}
