import { SITE_NAME } from "./site-name";
import { ogImageUrl, ogUrl } from "./og";

/** Date-only civic records must not shift a day with the server timezone. */
export function recordDate(value: string): string {
  const date = new Date(`${value.slice(0, 10)}T12:00:00Z`);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleDateString("en-CA", {
    year: "numeric", month: "long", day: "numeric", timeZone: "UTC",
  });
}

export function pageMeta(title: string, description: string, path: string, type = "website") {
  const fullTitle = `${title} | ${SITE_NAME}`;
  const image = ogImageUrl(title);
  return [
    { title: fullTitle },
    { name: "description", content: description },
    { property: "og:title", content: fullTitle },
    { property: "og:description", content: description },
    { property: "og:type", content: type },
    { property: "og:url", content: ogUrl(path) },
    { property: "og:site_name", content: SITE_NAME },
    { property: "og:image", content: image },
    { property: "og:image:width", content: "1200" },
    { property: "og:image:height", content: "630" },
    { name: "twitter:card", content: "summary_large_image" },
    { name: "twitter:title", content: fullTitle },
    { name: "twitter:description", content: description },
    { name: "twitter:image", content: image },
  ];
}

export function markdownAlternate(path: string) {
  return { tagName: "link" as const, rel: "alternate", type: "text/markdown", href: ogUrl(path), title: "Markdown representation" };
}
