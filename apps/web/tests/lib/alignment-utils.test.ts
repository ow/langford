import { describe, expect, it } from "vitest";
import { calculateAlignmentForPerson } from "../../app/lib/alignment-utils";

describe("voting alignment across recorded council service", () => {
  it("includes the last service day and excludes votes during a returning councillor's gap", () => {
    const memberships = [
      { people: { id: 1, name: "Returning member" }, start_date: "2020-01-01", end_date: "2020-12-31" },
      { people: { id: 1, name: "Returning member" }, start_date: "2022-01-01", end_date: "2022-12-31" },
      { people: { id: 2, name: "Other member" }, start_date: "2020-01-01", end_date: "2022-12-31" },
    ];
    const votes = ["2020-12-31", "2021-06-01", "2022-12-31"].flatMap((day, index) => [
      { motion_id: index, person_id: 1, vote: "Yes", motions: { meetings: { meeting_date: day } } },
      { motion_id: index, person_id: 2, vote: index === 1 ? "No" : "Yes", motions: { meetings: { meeting_date: day } } },
    ]);
    const results = calculateAlignmentForPerson(1, votes, memberships, new Date(2020, 0, 1), new Date(2022, 11, 31));
    expect(results).toEqual([expect.objectContaining({ personId: 2, totalMotions: 2, matchingVotes: 2, alignmentRate: 100 })]);
  });
});
