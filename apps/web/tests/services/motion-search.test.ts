import { beforeEach, describe, expect, it, vi } from "vitest";
import { searchMotionContext } from "~/services/motion-search.server";
import { embedQuery } from "~/services/ai/index.server";
vi.mock("~/services/ai/index.server", () => ({ embedQuery: vi.fn() }));

const complete = { individual_vote_coverage: "reconstructed_complete" };
const ballot = [{ person_id: 1, vote: "Yes" }, { person_id: 2, vote: "No" }];
function transport(matches: any[], enriched: any[]) {
  const query: any = { select: vi.fn(() => query), in: vi.fn(() => query), gte: vi.fn(() => query),
    then: (resolve: any) => Promise.resolve({ data: enriched, error: null }).then(resolve) };
  const client = { rpc: vi.fn().mockResolvedValue({ data: matches, error: null }), from: vi.fn(() => query) };
  return { client, query };
}
beforeEach(() => vi.clearAllMocks());
describe("motion evidence retrieval", () => {
  it.each(["unavailable", "throws"])("keeps keyword evidence when embedding %s and excludes zero-score candidates", async (failure) => {
    if (failure === "throws") vi.mocked(embedQuery).mockRejectedValue(new Error("offline"));
    else vi.mocked(embedQuery).mockResolvedValue(null);
    const { client } = transport([{ id: 8, rank_score: 0.01 }, { id: 9, rank_score: 0 }, { id: 10, rank_score: -1 }, { id: 11, rank_score: NaN }],
      [{ id: 9, votes: [] }, { id: 8, text_content: "body clause", meta: complete, votes: ballot, yes_votes: 0, no_votes: 0 }]);
    const result = await searchMotionContext(client as any, { query: "body clause", after_date: "2026-01-01" });
    expect(result.map((r) => r.id)).toEqual([8]);
    expect(result[0]).toMatchObject({ yes_votes: 1, no_votes: 1, rank_score: 0.01 });
    expect(client.rpc).toHaveBeenCalledWith("hybrid_search_motions", expect.objectContaining({
      query_text: "body clause", query_embedding: null, semantic_weight: 0, full_text_weight: 1,
      date_from: "2026-01-01", date_to: null, filter_municipality_id: null,
    }));
  });
  it("returns no evidence for keyword misses, including arbitrary zero-score semantic rows", async () => {
    vi.mocked(embedQuery).mockResolvedValue(null);
    const { client } = transport([{ id: 9, rank_score: 0 }], []);
    expect(await searchMotionContext(client as any, { query: "no lexical match" })).toEqual([]);
    expect(client.from).not.toHaveBeenCalled();
  });
  it("keeps RPC rank after enrichment and exposes only coverage-backed counts", async () => {
    vi.mocked(embedQuery).mockResolvedValue([0.25, 0.5]);
    const { client, query } = transport([{ id: 2, rank_score: 0.04 }, { id: 1, rank_score: 0.03 }, { id: 2, rank_score: 0.02 }],
      [{ id: 1, meta: { individual_vote_coverage: "named_only" }, votes: [{ person_id: 7, vote: "No" }], yes_votes: 0, no_votes: 0 },
       { id: 2, meta: complete, votes: ballot, yes_votes: 0, no_votes: 0 }]);
    const result = await searchMotionContext(client as any, { query: "budget" });
    expect(result.map((r) => r.id)).toEqual([2, 1]);
    expect(result[0]).toMatchObject({ yes_votes: 1, no_votes: 1 });
    expect(result[1]).toMatchObject({ yes_votes: null, no_votes: null, votes: [{ person_id: 7, vote: "No" }] });
    expect(result[1]).not.toHaveProperty("absent_votes");
    expect(query.select.mock.calls[0][0]).not.toMatch(/yes_votes|no_votes|abstain_votes|absent_votes/);
    expect(client.rpc).toHaveBeenCalledWith("hybrid_search_motions", expect.objectContaining({ query_embedding: "[0.25,0.5]", semantic_weight: 1 }));
    expect(embedQuery).toHaveBeenCalledTimes(1);
  });
});
