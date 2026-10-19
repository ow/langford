import { expect, it } from "vitest";
import { fetchRelevantVotesForAlignment } from "../../app/services/people";

it("includes shared ballots beyond the REST row limit for a long-serving member", async () => {
  const motionIds = Array.from({ length: 1001 }, (_, index) => index + 1);
  const target = motionIds.map((motion_id) => ({ motion_id }));
  const ballots = motionIds.flatMap((motion_id) => [21, 1].map((person_id) => ({
    motion_id, person_id, vote: "Yes",
    motions: { vote_coverage: "reconstructed_complete", meetings: { municipality_id: 1 } },
  })));
  // Model the independently imposed PostgREST default of at most 1,000 rows.
  const supabase = {
    from() {
      let targetQuery = false;
      let selectedIds: number[] = [];
      let start = 0;
      let end = 999;
      const query = {
        select(columns: string) { targetQuery = columns === "motion_id"; return query; },
        eq() { return query; },
        order() { return query; },
        range(first: number, last: number) { start = first; end = last; return query; },
        in(column: string, values: number[] | string[]) {
          if (column === "motion_id") selectedIds = values as number[];
          return query;
        },
        then(resolve: (value: unknown) => unknown) {
          const rows = targetQuery ? target : ballots.filter((vote) => selectedIds.includes(vote.motion_id));
          return Promise.resolve({ data: rows.slice(start, end + 1), error: null }).then(resolve);
        },
      };
      return query;
    },
  };
  const votes = await fetchRelevantVotesForAlignment(supabase as any, 21, 1);
  expect(votes).toHaveLength(2002);
  expect(votes.filter((vote) => vote.motion_id === 1001).map((vote) => vote.person_id)).toEqual([21, 1]);
});
