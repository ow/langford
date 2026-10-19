import { expect, it } from "vitest";
import { getPublicParticipantStats, getParticipantIdentificationCoverage } from "../../app/services/people";

// A small relational store: filters apply to source rows, including the real
// PostgREST row cap. It supplies no computed participant classifications.
function client(segments: any[], people: any[], meetings: any[] = []) {
  return { from(table: string) {
    let rows = table === "people" ? [...people] : table === "meetings" ? [...meetings] : [...segments];
    let start = 0, end = 999, head = false;
    const value = (row: any, key: string) => key.split(".").reduce((r, k) => r?.[k], row);
    const query: any = {
      select(_columns: string, options?: { head?: boolean }) { head = !!options?.head; return query; },
      not(key: string, _op: string, v: any) { rows = rows.filter(r => value(r, key) !== v); return query; },
      eq(key: string, v: any) { rows = rows.filter(r => value(r, key) === v); return query; },
      lte(key: string, v: any) { rows = rows.filter(r => value(r, key) <= v); return query; },
      in(key: string, values: any[]) { rows = rows.filter(r => values.includes(value(r, key))); return query; },
      order(key: string) { rows.sort((a, b) => value(a, key) - value(b, key)); return query; },
      range(a: number, b: number) { start = a; end = b; return query; },
      then(resolve: any) { return Promise.resolve({ data: head ? null : rows.slice(start, end + 1), count: head ? rows.length : null, error: null }).then(resolve); },
    };
    return query;
  }} as any;
}
const membership = (role: string, start_date: string, end_date: string | null, classification: string) =>
  ({ role, start_date, end_date, organization: { classification } });
const segment = (id: number, person_id: number, date: string, municipality_id = 1) => ({
  id, person_id, meeting_id: id, start_time: 0, end_time: 60,
  meetings: { id, title: "Council", meeting_date: date, municipality_id },
});

it("measures named-link coverage against all scoped transcript segments, including unidentified speech", async () => {
  const rows = [segment(1, 1, "2024-01-01"), segment(2, null as any, "2024-01-01"),
    segment(3, null as any, "2024-01-01"), segment(4, 2, "2024-01-01", 2), segment(5, 1, "2099-01-01")];
  expect(await getParticipantIdentificationCoverage(client(rows, []), 1)).toEqual({ totalSegments: 3, linkedSegments: 1 });
  expect(await getParticipantIdentificationCoverage(client([], []), 1)).toEqual({ totalSegments: 0, linkedSegments: 0 });
});

it("counts public speech outside dated council/staff service, never future or anonymous identities", async () => {
  const people = [
    { id: 1, name: "Future Councillor", is_councillor: true, memberships: [membership("Councillor", "2025-01-01", "2025-12-31", "Council")] },
    { id: 2, name: "Former Clerk", memberships: [membership("Clerk", "2020-01-01", "2022-12-31", "STAFF")] },
    { id: 3, name: "Unknown Speaker", memberships: [] },
    { id: 4, name: "Resident Example", memberships: [] },
    { id: 5, name: "Undated Councillor", is_councillor: true, memberships: [] },
  ];
  const rows = [segment(1, 1, "2024-06-01"), segment(2, 1, "2025-06-01"), segment(3, 1, "2026-01-01"),
    segment(4, 2, "2021-06-01"), segment(5, 2, "2024-06-01"), segment(6, 3, "2024-06-01"),
    segment(7, 4, "2099-01-01"), segment(8, 4, "2024-06-01", 2), segment(9, 5, "2024-06-01")];
  const result = await getPublicParticipantStats(client(rows, people), 1);
  expect(result.map(p => [p.person.id, p.meetingCount, p.totalSeconds])).toEqual([[1, 2, 120], [2, 1, 60]]);
});

it("unions minutes-confirmed and audio appearances without inventing speaking time or double-counting meetings", async () => {
  const person = { id: 353, name: "Lisa Foxall", is_councillor: true,
    memberships: [membership("Councillor", "2026-11-02", null, "Council")] };
  const history = [{ personId: 353, municipalitySlug: "langford", name: "Lisa Foxall", coverageNote: "Two original minutes.", records: [
    { meetingId: 1, date: "2024-01-01", meetingType: "Council", minutesUrl: "https://example.org/1.pdf", recordingUrl: "", summary: "Public question." },
    { meetingId: 2, date: "2024-02-01", meetingType: "Council", minutesUrl: "https://example.org/2.pdf", recordingUrl: "", summary: "Public comment." },
  ] }];
  const rows = [segment(1, 353, "2024-01-01")];
  const result = await (getPublicParticipantStats as any)(client(rows, [person]), 1, history);
  expect(result).toHaveLength(1);
  expect(result[0]).toMatchObject({ meetingCount: 2, audioMeetingCount: 1, documentedMeetingCount: 2, totalSeconds: 60, segmentCount: 1 });
  const minutesOnly = await (getPublicParticipantStats as any)(client([], [person]), 1, history);
  expect(minutesOnly[0]).toMatchObject({ meetingCount: 2, audioMeetingCount: 0, documentedMeetingCount: 2, totalSeconds: 0, segmentCount: 0 });
  expect(minutesOnly[0].recentAppearances[0]).toMatchObject({ meetingId: 2, minutesUrl: "https://example.org/2.pdf" });
});

it("excludes documented government presenters only at the meeting where their role is established", async () => {
  const presenter = { id: 25, name: "Example Presenter", memberships: [] };
  const role = { person_id: 25, classification: "government_staff", role: "Senior Manager", organization: "Regional District",
    observed_date: "2024-01-01", source_file: "archive/minutes.pdf", source_sha256: "a".repeat(64),
    source_url: "https://example.org/minutes.pdf", source_quote: "Senior Manager Example Presenter provided a presentation.",
    method: "official_minutes_explicit_role_v1" };
  const rows = [segment(1, 25, "2024-01-01"), segment(2, 25, "2024-02-01")];
  const result = await getPublicParticipantStats(client(rows, [presenter], [{ id: 1, participant_roles: { 25: role } }]), 1);
  expect(result.map(p => [p.person.id, p.meetingCount, p.totalSeconds])).toEqual([[25, 1, 60]]);
  expect(result[0].recentAppearances.map(a => a.meetingId)).toEqual([2]);
});

it("scopes a participant profile to one person and returns their complete public appearance history", async () => {
  const people = [{ id: 25, name: "Alex Resident", memberships: [] }, { id: 26, name: "Other Resident", memberships: [] }];
  const rows = Array.from({ length: 8 }, (_, i) => segment(i + 1, 25, "2024-01-01"));
  rows.push(segment(9, 26, "2024-01-01"));
  const result = await getPublicParticipantStats(client(rows, people), 1, [], 25);
  expect(result.map(p => p.person.id)).toEqual([25]);
  expect(result[0].recentAppearances).toHaveLength(8);
});
