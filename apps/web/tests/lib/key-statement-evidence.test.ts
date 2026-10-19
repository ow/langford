import { describe, expect, it } from "vitest";
import { isSpokenStatementCandidate, hasSourceIntegrityHold } from "~/lib/key-statement-evidence";

describe("spoken statement search eligibility", () => {
  it("retains legacy unknowns without treating NULL identity as proof of speech", () => {
    const results = [
      { id: 1, person_id: null, evidence_kind: null },
      { id: 2, person_id: 9, evidence_kind: "transcript" },
      { id: 3, person_id: null, evidence_kind: "recorded_vote" },
      { id: 4, person_id: null, evidence_kind: "institutional_direction" },
      { id: 5, person_id: 9, evidence_kind: "unexpected_future_kind" },
    ];
    expect(results.filter(isSpokenStatementCandidate).map((row) => row.id)).toEqual([1, 2]);
  });
});

// The whole derived claim is held even when only one of its sources is invalid.
it("withholds a stance if any quote needs regeneration, preserving unrelated stances", () => {
  const stances = [
    { id: 1, evidence_quotes: [{ text: "current source" }] },
    { id: 2, evidence_quotes: [{ text: "current source" }, { text: "legacy vote paraphrase", source_integrity: { status: "requires_regeneration" } }] },
    { id: 3, evidence_quotes: [] },
  ];
  expect(stances.filter((stance) => !hasSourceIntegrityHold(stance)).map((stance) => stance.id)).toEqual([1, 3]);
});
