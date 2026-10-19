/**
 * Public URLs for people use name slugs (/people/scott-goodmanson).
 * Prefer the stored `people.slug` (set by trg_person_slug); fall back to
 * deriving it from the name (same rules as api/lib/slugs.ts) for callers
 * that only have a name to hand.
 */
export function personSlug(name: string): string {
  return name
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "")
    .slice(0, 60)
    .replace(/-$/, "");
}

type PersonRef = {
  id: number | string;
  name?: string | null;
  slug?: string | null;
};

export function personPath(person: PersonRef, suffix = ""): string {
  const slug = person.slug || (person.name ? personSlug(person.name) : "");
  return `/people/${slug || person.id}${suffix}`;
}
