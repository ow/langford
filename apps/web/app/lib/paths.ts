/**
 * Public URLs use human slugs (/meetings/2026-07-20-regular-council,
 * /matters/residential-garbage-and-organics-collection), never numeric ids.
 * Slugs are set by BEFORE INSERT triggers (migration 47-10) and stay stable.
 *
 * Each helper takes any object carrying `slug` (and `id` as a fallback). The
 * id fallback still works — detail loaders 301 an all-digit param to the
 * slug URL — but every query feeding a link should select `slug`.
 * People live in people-paths.ts (personPath).
 */
export type SlugRef = {
  id?: number | string | null;
  slug?: string | null;
};

function segment(ref: SlugRef | null | undefined): string {
  if (!ref) return "";
  return ref.slug || (ref.id != null ? String(ref.id) : "");
}

/** `suffix` is appended verbatim: "/explorer", "#decisions", "?t=120". */
export function meetingPath(meeting: SlugRef | null | undefined, suffix = ""): string {
  return `/meetings/${segment(meeting)}${suffix}`;
}

export function meetingDocumentsPath(meeting: SlugRef | null | undefined): string {
  return meetingPath(meeting, "/documents");
}

/** Document viewer: meeting part is the slug; the document id stays numeric. */
export function documentPath(
  meeting: SlugRef | null | undefined,
  documentId: number | string,
  suffix = "",
): string {
  return meetingPath(meeting, `/documents/${documentId}${suffix}`);
}

export function matterPath(matter: SlugRef | null | undefined, suffix = ""): string {
  return `/matters/${segment(matter)}${suffix}`;
}

export function bylawPath(bylaw: SlugRef | null | undefined, suffix = ""): string {
  return `/bylaws/${segment(bylaw)}${suffix}`;
}

export function electionPath(election: SlugRef | null | undefined, suffix = ""): string {
  return `/elections/${segment(election)}${suffix}`;
}

/** Build a SlugRef from flat `{x_id, x_slug}` style fields. */
export function ref(id: number | string | null | undefined, slug?: string | null): SlugRef {
  return { id, slug };
}
