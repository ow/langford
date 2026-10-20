import { describe, expect, it } from "vitest";
import { voteTally } from "~/lib/vote-coverage";

const complete = { individual_vote_coverage: "reconstructed_complete" };
describe("complete vote tally", () => {
  it.each([
    ["named minority only", {}, [{ person_id: 1, vote: "No" }]],
    ["duplicate identities", complete, [{ person_id: 1, vote: "Yes" }, { person_id: 1, vote: "No" }]],
    ["unknown identity", complete, [{ person_id: null, vote: "Yes" }]],
    ["unsupported choice", complete, [{ person_id: 1, vote: "Unknown" }]],
    ["recusal", complete, [{ person_id: 1, vote: "Yes" }, { person_id: 2, vote: "Recused" }]],
    ["abstention", complete, [{ person_id: 1, vote: "Yes" }, { person_id: 2, vote: "Abstain" }]],
    ["empty ballot", complete, []],
  ])("does not present %s as a full tally", (_label, meta, votes) => {
    expect(voteTally({ meta, votes: votes as any })).toBeNull();
  });
  it("counts a complete ballot independently of stale legacy counters", () => {
    expect(voteTally({ meta: complete, votes: [{ person_id: 1, vote: "Yes" }, { person_id: 2, vote: "No" }] })).toBe("1–1");
  });
});
