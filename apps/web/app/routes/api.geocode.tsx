import { SITE_NAME } from "../lib/site-name";
import { DEFAULT_MUNICIPALITY } from "../lib/site-config";
import type { Route } from "./+types/api.geocode";
import { createSupabaseServerClient } from "../lib/supabase.server";

/**
 * POST /api/geocode
 * Body: { address: string }
 * Returns: { lat: number, lng: number } or { error: string }
 *
 * Server-side geocoding via Nominatim, biased to the site's municipality.
 * Requires authentication.
 */
export async function action({ request }: Route.ActionArgs) {
  const { supabase } = createSupabaseServerClient(request);
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    return Response.json({ error: "Not authenticated" }, { status: 401 });
  }

  try {
    const body = (await request.json()) as { address?: string };
    const address = body.address?.trim();

    if (!address) {
      return Response.json(
        { error: "address is required" },
        { status: 400 },
      );
    }

    // Bias results to the municipality's area (see lib/site-config.ts)
    const viewBox = DEFAULT_MUNICIPALITY.geocodeViewBox;
    const query = `${address}, ${DEFAULT_MUNICIPALITY.short_name}, ${DEFAULT_MUNICIPALITY.province}, Canada`;
    const url = `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(query)}&format=json&limit=1&viewbox=${viewBox}&bounded=0`;

    const response = await fetch(url, {
      headers: {
        "User-Agent": `${SITE_NAME}/1.0 (civic platform)`,
      },
    });

    if (!response.ok) {
      console.error("Nominatim API error:", response.status, response.statusText);
      return Response.json(
        { error: "Geocoding service unavailable" },
        { status: 502 },
      );
    }

    const results = (await response.json()) as Array<{
      lat: string;
      lon: string;
      display_name: string;
    }>;

    if (results.length === 0) {
      return Response.json({ error: "Address not found" }, { status: 404 });
    }

    return Response.json({
      lat: parseFloat(results[0].lat),
      lng: parseFloat(results[0].lon),
      display_name: results[0].display_name,
    });
  } catch (err) {
    console.error("Geocode action error:", err);
    return Response.json(
      {
        error:
          err instanceof Error ? err.message : "Internal server error",
      },
      { status: 500 },
    );
  }
}
