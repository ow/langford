import { DEFAULT_MUNICIPALITY } from "./site-config";

/** Site brand derived from the municipality, e.g. "Langford" → "Open Langford". */
export function siteName(municipality?: { short_name?: string | null } | null): string {
  const base = municipality?.short_name || DEFAULT_MUNICIPALITY.short_name;
  return `Open ${base}`;
}

/** Build-time site name for meta tags where loader data isn't available. */
export const SITE_NAME = siteName(DEFAULT_MUNICIPALITY);
