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
  it("projects compact source evidence without forwarding raw audit metadata or inventing vote provenance", async () => {
    vi.mocked(embedQuery).mockResolvedValue(null);
    const rawAudit = "RAW_AUDIT_PAYLOAD_".repeat(1000);
    const { client } = transport([{ id: 21, rank_score: 0.02 }, { id: 22, rank_score: 0.01 }], [{
      id: 21, meeting_id: 5, text_content: "Exact native decision clause", plain_english_summary: "Decision",
      result: "CARRIED", mover: "Member One", seconder: "Member Two",
      meetings: { id: 5, meeting_date: "2026-01-01" },
      meta: { ...complete, unrelated_history: rawAudit, ballot_reconstruction: {
        source_block: rawAudit, prior_vectors: [rawAudit],
        choice_provenance: { person_1: "explicit_named", person_2: "inferred_official_dissent_recording_rule", person_4: "preserved_existing_choice", person_5: "explicit_named" },
        votes: [{ person_id: 5, vote: "No", evidence: "explicit_named" }],
      } },
      votes: [
        { person_id: 1, vote: "Yes", people: { name: "Member One" } },
        { person_id: 2, vote: "No", people: { name: "Member Two" } },
        { person_id: 3, vote: "Yes", people: { name: "Member Three" } },
        { person_id: 4, vote: "Yes", people: { name: "Member Four" } },
        { person_id: 5, vote: "Yes", people: { name: "Member Five" } },
      ],
    }, {
      id: 22, meta: { ...complete, ballot_reconstruction: { choice_provenance: { person_6: "explicit_named" } } },
      votes: [{ person_id: 6, vote: "Recused", people: { name: "Member Six" } }],
    }]);
    const [result, rejected] = await searchMotionContext(client as any, { query: "decision" });
    expect(rejected).toMatchObject({ vote_coverage: "unknown", yes_votes: null, no_votes: null,
      vote_count_basis: "incomplete_or_invalid_individual_vote_rows",
      votes: [{ person_id: 6, vote: "Recused", people: { name: "Member Six" }, choice_basis: "unknown" }] });
    expect("meta" in result).toBe(false);
    expect(JSON.stringify(result).includes("RAW_AUDIT_PAYLOAD_")).toBe(false);
    expect(result).toMatchObject({ id: 21, meeting_id: 5, text_content: "Exact native decision clause",
      plain_english_summary: "Decision", result: "CARRIED", mover: "Member One", seconder: "Member Two",
      meetings: { id: 5, meeting_date: "2026-01-01" }, vote_coverage: "reconstructed_complete",
      yes_votes: 4, no_votes: 1, vote_count_basis: "complete_individual_vote_rows",
      votes: [
        { person_id: 1, vote: "Yes", people: { name: "Member One" }, choice_basis: "explicit" },
        { person_id: 2, vote: "No", people: { name: "Member Two" }, choice_basis: "inferred" },
        { person_id: 3, vote: "Yes", people: { name: "Member Three" }, choice_basis: "unknown" },
        { person_id: 4, vote: "Yes", people: { name: "Member Four" }, choice_basis: "unknown" },
        { person_id: 5, vote: "Yes", people: { name: "Member Five" }, choice_basis: "unknown" },
      ] });
  });

});
