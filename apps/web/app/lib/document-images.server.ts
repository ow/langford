const BASE = (process.env.DOCUMENT_IMAGE_PUBLIC_BASE_URL || process.env.R2_PUBLIC_URL || "").replace(/\/+$/, "");

/** Public URL for an image the pipeline extracted from a report PDF (R2). */
export function documentImageUrl(r2Key: string | null | undefined): string | null {
  if (!BASE || !r2Key) return null;
  return `${BASE}/${r2Key.replace(/^\/+/, "")}`;
}
