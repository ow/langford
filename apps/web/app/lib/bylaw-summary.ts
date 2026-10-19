/**
 * Client-safe helpers for bylaw records.
 *
 * The pipeline (pipeline/ingestion/langford_bylaws.py, format_summary) stores
 * a structured plain-English summary in `bylaws.plain_english_summary`:
 *
 *   <2-3 sentence summary>
 *
 *   Key rules:
 *   - <rule>
 *
 *   Who it affects: <sentence>
 *
 * Older rows hold a single paragraph, which parses to just `summary`.
 */

export interface BylawSummaryParts {
  summary: string;
  keyRules: string[];
  whoItAffects: string | null;
}

export function parseBylawSummary(text: string | null | undefined): BylawSummaryParts {
  const parts: BylawSummaryParts = { summary: "", keyRules: [], whoItAffects: null };
  if (!text) return parts;
  const summary: string[] = [];
  for (const block of text.split(/\n\s*\n/)) {
    const trimmed = block.trim();
    if (/^key rules:/i.test(trimmed)) {
      parts.keyRules = trimmed
        .replace(/^key rules:\s*/i, "")
        .split("\n")
        .map((line) => line.replace(/^\s*[-*•]\s*/, "").trim())
        .filter(Boolean);
    } else if (/^who it affects:/i.test(trimmed)) {
      parts.whoItAffects = trimmed.replace(/^who it affects:\s*/i, "").trim() || null;
    } else if (trimmed) {
      summary.push(trimmed);
    }
  }
  parts.summary = summary.join(" ");
  return parts;
}

/** Short summary for list rows and cards. */
export function bylawLead(text: string | null | undefined): string {
  return parseBylawSummary(text).summary;
}

export type BylawStatusTone = "success" | "danger" | "muted";

/** Human label for bylaws.status ("In force" | "Amended" | "Repealed" | legacy "Active"). */
export function bylawStatus(status: string | null | undefined): { label: string; tone: BylawStatusTone } | null {
  if (!status) return null;
  const s = status.trim().toLowerCase();
  if (s === "amended") return { label: "In force, as amended", tone: "success" };
  if (s === "in force" || s === "active") return { label: "In force", tone: "success" };
  if (s.includes("repeal")) return { label: "Repealed", tone: "danger" };
  return { label: status, tone: "muted" };
}

export interface BylawAmendment {
  bylawNumber: string;
  adopted: string;
}

/**
 * Amending bylaws from a consolidation's "List of Amendments" table (mirrors
 * amendments_from_consolidation in pipeline/bylaw_numbers.py).
 */
export function amendmentsFromText(fullText: string | null | undefined): BylawAmendment[] {
  if (!fullText || !/consolidat/i.test(fullText.slice(0, 3000))) return [];
  const re = /Amendment\s*#?\s*\d+[^\n]*\n\s*(\d{3,4})\s*\n\s*([A-Z][a-z]+\.?\s+\d{1,2},\s*(?:19|20)\d{2})/g;
  const out: BylawAmendment[] = [];
  for (const m of fullText.slice(0, 6000).matchAll(re)) {
    const n = String(Number(m[1]));
    if (!out.some((a) => a.bylawNumber === n)) {
      out.push({ bylawNumber: n, adopted: m[2].replace(/\s+/g, " ") });
    }
  }
  return out;
}
