import { DEFAULT_MUNICIPALITY } from "./site-config";

/** Site brand derived from the municipality, e.g. "Langford" → "Langford.ai". */
export function siteName(municipality?: { short_name?: string | null } | null): string {
  const base = (municipality?.short_name || DEFAULT_MUNICIPALITY.short_name).replace(/\s+/g, "");
  return `${base}.ai`;
}
