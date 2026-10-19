/**
 * agenda_items.related_address is a text column that usually holds a JSON
 * array string ('["2023 Millstream Road"]'); older rows may be plain text or
 * a real array. Normalize to a clean string[].
 */
export function parseRelatedAddresses(value: unknown): string[] {
  const clean = (list: unknown[]) =>
    list
      .filter((a): a is string => typeof a === "string")
      .map((a) => a.trim())
      .filter(Boolean);
  if (Array.isArray(value)) return clean(value);
  if (typeof value !== "string") return [];
  const trimmed = value.trim();
  if (!trimmed || trimmed === "[]" || trimmed === "null") return [];
  if (trimmed.startsWith("[")) {
    try {
      const parsed = JSON.parse(trimmed);
      return Array.isArray(parsed) ? clean(parsed) : [];
    } catch {
      return [];
    }
  }
  return [trimmed];
}
