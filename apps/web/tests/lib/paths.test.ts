import { describe, it, expect } from "vitest";
import { bylawPath, documentPath, electionPath, matterPath, meetingPath } from "../../app/lib/paths";
import { sourceHref } from "../../app/lib/source-links";
import { resolveSlugParam } from "../../app/lib/slug-params.server";

describe("path helpers", () => {
  it("prefer slugs and fall back to ids", () => {
    expect(meetingPath({ id: 389, slug: "2026-09-28-special-council" })).toBe("/meetings/2026-09-28-special-council");
    expect(meetingPath({ id: 389 })).toBe("/meetings/389");
    expect(meetingPath({ id: 389, slug: "m" }, "#decisions")).toBe("/meetings/m#decisions");
    expect(documentPath({ id: 1, slug: "m" }, 42)).toBe("/meetings/m/documents/42");
    expect(matterPath({ id: 1665, slug: "garbage" })).toBe("/matters/garbage");
    expect(bylawPath({ id: 3, slug: "bylaw-2299" })).toBe("/bylaws/bylaw-2299");
    expect(electionPath({ id: 1, slug: "2022-general-local-election" })).toBe("/elections/2022-general-local-election");
  });

  it("builds citation links from source slugs", () => {
    expect(sourceHref({ type: "transcript", id: 7, meeting_id: 389, meeting_slug: "m" })).toBe("/meetings/m#transcript=7");
    expect(sourceHref({ type: "motion", id: 7, meeting_id: 389, meeting_slug: "m" })).toBe("/meetings/m#decisions");
    expect(sourceHref({ type: "matter", id: 5, matter_slug: "x" })).toBe("/matters/x");
    expect(sourceHref({ type: "transcript", id: 7, meeting_id: 389 })).toBe("/meetings/389#transcript=7");
  });
});

function mockSupabase(rows: { id: number; slug: string }[]) {
  return {
    from: () => {
      const filters: Record<string, unknown> = {};
      const q: any = {
        select: () => q,
        limit: () => q,
        eq: (col: string, val: unknown) => ((filters[col] = val), q),
        maybeSingle: async () => ({
          data: rows.find((r) => Object.entries(filters).every(([k, v]) => (r as any)[k] === v)) ?? null,
        }),
      };
      return q;
    },
  } as any;
}

async function thrown(p: Promise<unknown>): Promise<Response> {
  try {
    await p;
  } catch (e) {
    return e as Response;
  }
  throw new Error("expected a thrown Response");
}

describe("resolveSlugParam", () => {
  const supabase = mockSupabase([{ id: 389, slug: "2026-09-28-special-council" }]);
  const build = (m: { slug: string }) => `/meetings/${m.slug}/explorer`;

  it("returns the row for a slug", async () => {
    const row = await resolveSlugParam(supabase, "meetings", "2026-09-28-special-council", new Request("http://x/"), build);
    expect(row.id).toBe(389);
  });

  it("301s numeric ids to the slug URL, keeping the query string", async () => {
    const res = await thrown(resolveSlugParam(supabase, "meetings", "389", new Request("http://x/meetings/389/explorer?t=5"), build));
    expect(res.status).toBe(301);
    expect(res.headers.get("Location")).toBe("/meetings/2026-09-28-special-council/explorer?t=5");
  });

  it("404s unknown params", async () => {
    expect((await thrown(resolveSlugParam(supabase, "meetings", "nope", new Request("http://x/"), build))).status).toBe(404);
    expect((await thrown(resolveSlugParam(supabase, "meetings", "999", new Request("http://x/"), build))).status).toBe(404);
  });

  it("301s old id-prefixed matter slugs", async () => {
    const matters = mockSupabase([{ id: 1665, slug: "residential-garbage" }]);
    const res = await thrown(resolveSlugParam(matters, "matters", "1665-solid-waste-collection", new Request("http://x/"), (m) => `/matters/${m.slug}`));
    expect(res.status).toBe(301);
    expect(res.headers.get("Location")).toBe("/matters/residential-garbage");
  });
});
