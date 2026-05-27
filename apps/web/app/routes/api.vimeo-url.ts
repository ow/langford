import { getVimeoVideoData } from "../services/vimeo.server";
import { createSupabaseServerClient } from "../lib/supabase.server";
import { getMunicipality } from "../services/municipality";

function extractHtmlAttr(html: string, attr: string): string | null {
  const pattern = new RegExp(`${attr}=["']([^"']+)["']`, "i");
  return html.match(pattern)?.[1] || null;
}

async function getIsiVideoData(videoUrl: string) {
  const parsed = new URL(videoUrl);
  if (!parsed.hostname.includes("escribemeetings.com")) return null;
  if (!parsed.pathname.toLowerCase().includes("/players/isistandaloneplayer.aspx")) {
    return null;
  }

  const response = await fetch(videoUrl, {
    headers: {
      "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    },
  });
  if (!response.ok) return null;

  const html = await response.text();
  const clientId = extractHtmlAttr(html, "data-client_id");
  const fileName = extractHtmlAttr(html, "data-file_name");
  if (!clientId || !fileName) return null;

  return {
    direct_url: `https://video.isilive.ca/${encodeURIComponent(clientId)}/${encodeURIComponent(fileName)}`,
    direct_audio_url: null,
  };
}

export async function loader({ request }: { request: Request }) {
  const url = new URL(request.url);
  const videoUrl = url.searchParams.get("video_url");
  const meetingId = url.searchParams.get("meeting_id");

  if (!videoUrl) {
    return Response.json({ error: "video_url required" }, { status: 400 });
  }

  try {
    const isiResult = await getIsiVideoData(videoUrl);
    if (isiResult) return Response.json(isiResult);

    const { supabase } = createSupabaseServerClient(request);
    const municipality = await getMunicipality(supabase);
    const result = await getVimeoVideoData(videoUrl, meetingId || undefined, municipality.website_url);
    return Response.json({
      direct_url: result?.direct_url || null,
      direct_audio_url: result?.direct_audio_url || null,
    });
  } catch {
    return Response.json({ direct_url: null, direct_audio_url: null });
  }
}
