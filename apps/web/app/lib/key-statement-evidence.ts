/** NULL is unclassified legacy content, not a claim of verified speech. */
export type KeyStatementEvidenceKind =
  | "transcript"
  | "recorded_vote"
  | "institutional_direction"
  | null;

export const SPOKEN_STATEMENT_FILTER =
  "evidence_kind.is.null,evidence_kind.eq.transcript";

/** Nonspoken decisions must be served as motions/votes, never speech excerpts. */
export function isSpokenStatementCandidate(row: { evidence_kind?: unknown }): boolean {
  return row.evidence_kind == null || row.evidence_kind === "transcript";
}

/** Hold the entire derived stance, rather than hiding only its disputed quote. */
export function hasSourceIntegrityHold(stance: { evidence_quotes?: unknown }): boolean {
  return Array.isArray(stance.evidence_quotes) && stance.evidence_quotes.some((quote) =>
    quote != null && typeof quote === "object" &&
    quote.source_integrity?.status === "requires_regeneration",
  );
}
