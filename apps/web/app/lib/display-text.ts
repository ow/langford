/**
 * Source documents often SHOUT agenda titles ("CALL TO ORDER",
 * "BYLAW NO. 2110 - Langford Zoning…"). Convert all-caps words to normal
 * case while keeping real acronyms.
 */
const ACRONYMS = new Set([
  "ACC", "ADP", "BC", "CAO", "CRD", "DCC", "DCCS", "DP", "DPA", "DPAS", "DVP",
  "EDPA", "OCP", "RCMP", "SOFI", "YMCA", "YWCA", "BCTF", "ICBC", "UBCM",
  "MOU", "RFP", "NRFP", "TUP", "HST", "GST", "LGA", "FAQ", "CEO", "CFO",
  "II", "III", "IV", "AM", "PM",
]);

const SMALL_WORDS = new Set([
  "a", "an", "and", "as", "at", "by", "for", "from", "in", "of", "on", "or",
  "the", "to", "with", "re",
]);

export function displayTitle(input?: string | null): string {
  if (!input) return "";
  const text = input.trim();
  const shouty = !/[a-z]/.test(text);
  let first = true;

  return text.replace(/[A-Za-z][A-Za-z'’]*/g, (word) => {
    const isFirst = first;
    first = false;
    if (word !== word.toUpperCase() || word.length < 2) return word;
    const bare = word.replace(/['’]/g, "");
    if (ACRONYMS.has(bare)) return word;
    // In mixed-case titles, short all-caps words are acronyms (IPD, CRD, WSP).
    if (!shouty && bare.length <= 4) return word;
    const lower = word.toLowerCase();
    if (shouty && !isFirst && SMALL_WORDS.has(lower)) return lower;
    return lower.charAt(0).toUpperCase() + lower.slice(1);
  });
}

/** Last name for compact vote lists ("Kimberley Guiry" → "Guiry"). */
export function lastName(name?: string | null): string {
  if (!name) return "Unknown";
  const parts = name.trim().split(/\s+/);
  return parts[parts.length - 1];
}

/** A matter's short human title (pipeline-written), falling back to its raw title. */
export function matterTitle(matter?: { title?: string | null; meta?: any } | null): string {
  const short = matter?.meta && typeof matter.meta === "object" ? matter.meta.display_title : null;
  return typeof short === "string" && short.trim() ? short.trim() : displayTitle(matter?.title);
}
