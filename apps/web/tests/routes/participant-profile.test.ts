import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { beforeEach, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({
  person: { id: 25, name: "Alex Resident", slug: "alex-resident", memberships: [] as any[] },
  councilProfile: vi.fn(),
  stances: vi.fn(async () => []),
}));
vi.mock("../../app/lib/supabase.server", () => ({ getSupabaseAdminClient: () => ({
  from: () => { const q: any = { select: () => q, eq: () => q, single: async () => ({ data: state.person, error: null }) }; return q; },
}) }));
vi.mock("../../app/lib/people.server", () => ({ resolvePersonParam: async () => state.person }));
vi.mock("../../app/services/municipality", () => ({ getMunicipality: async () => ({ id: 1, slug: "langford" }) }));
vi.mock("../../app/services/council-terms", () => ({ getCouncilTerms: async () => [] }));
vi.mock("../../app/services/people", () => ({ getPersonProfile: (...args: any[]) => state.councilProfile(...args), getPublicParticipantStats: vi.fn() }));
vi.mock("../../app/services/profiling", () => ({
  getSpeakingTimeStats: async () => [], getSpeakingTimeByMeeting: async () => [], getSpeakingTimeByTopic: async () => [],
  getCouncillorStances: state.stances, getCouncillorHighlights: async () => null, getKeyVotes: async () => [],
}));
import { loader as councilLoader } from "../../app/routes/person-profile";
import ParticipantProfile from "../../app/routes/participant-profile";

beforeEach(() => {
  state.person = { id: 25, name: "Alex Resident", slug: "alex-resident", memberships: [] };
  state.councilProfile.mockReset().mockImplementation(async () => ({ person: state.person }));
  state.stances.mockClear();
});

it("redirects old public-person URLs before loading council analytics", async () => {
  let response: unknown;
  try { await councilLoader({ params: { id: "alex-resident" }, request: new Request("https://example.org/people/alex-resident"), context: {} } as any); }
  catch (error) { response = error; }
  expect(response).toBeInstanceOf(Response);
  expect((response as Response).headers.get("Location")).toBe("/participants/alex-resident");
  expect(state.councilProfile).not.toHaveBeenCalled();
  expect(state.stances).not.toHaveBeenCalled();
});

it("retains the council profile for a person with actual council service", async () => {
  state.person.memberships = [{ id: 1, organization_id: 1, role: "Councillor", start_date: "2022-11-07", organization: { classification: "Council", name: "Council" } }];
  const data = await councilLoader({ params: { id: "alex-resident" }, request: new Request("https://example.org/people/alex-resident"), context: {} } as any);
  expect(data.person.id).toBe(25);
  expect(state.stances).toHaveBeenCalled();
});

it("shows a public participant's appearances without council-only labels or analytics", () => {
  const html = renderToStaticMarkup(createElement(MemoryRouter, null, createElement(ParticipantProfile, { loaderData: {
    person: state.person, hasCouncilService: false, history: null, participation: {
      meetingCount: 1, documentedMeetingCount: 0, totalSeconds: 42,
      recentAppearances: [{ meetingId: 10, meetingDate: "2024-01-01", meetingTitle: "Council meeting", seconds: 42, segmentCount: 1, firstStartTime: 10 }],
    },
  } } as any)));
  expect(html).toContain("Public participant");
  expect(html).toContain("/meetings/10?t=10");
  expect(html).not.toMatch(/Former|Recorded votes|Voting alignment|Attendance rate|Key votes|Policy|council service profile/i);
});
