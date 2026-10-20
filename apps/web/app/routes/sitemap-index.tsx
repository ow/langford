import { SITE_ORIGIN } from "../lib/og";
import { sitemapIndex } from "../lib/sitemap";
import { SITEMAP_SECTIONS } from "../services/sitemap.server";

/** GET /sitemap.xml — index of per-section sitemaps (robots.txt points here). */
export async function loader() {
  const today = new Date().toISOString().slice(0, 10);
  const xml = sitemapIndex(
    SITE_ORIGIN,
    SITEMAP_SECTIONS.map((section) => ({ path: `/sitemaps/${section}.xml`, lastmod: today })),
  );
  return new Response(xml, {
    headers: { "Content-Type": "application/xml; charset=utf-8", "Cache-Control": "public, max-age=3600, s-maxage=86400" },
  });
}
