import { createClient } from "@supabase/supabase-js";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { getMeetings } from "../../app/services/meetings";
import { getRawPeopleData } from "../../app/services/people";
import { getPublicCouncilSummary } from "../../app/services/council-summary.server";
import type { Municipality } from "../../app/lib/types";
import { calculateAttendance } from "../../app/lib/attendance-evidence";
const { origin } = vi.hoisted(() => ({ origin: vi.fn() }));
const client = () => createClient("https://origin.supabase.co", "public-test-key", { global: { fetch: origin }, auth: { persistSession: false } });
vi.mock("../../app/lib/supabase.server", () => ({ getSupabaseAdminClient: () => client() }));
const member = { id: 1, name: "Member", memberships: [{ id: 1, organization_id: 10, role: "Councillor", start_date: "2026-01-01", organization: { classification: "Council" } }] };
const meetings = [1, 2, 3].map(id => ({ id, organization_id: 10, meeting_date: `2026-01-0${id}`, has_agenda: true, status: "Completed" }));
const attendance = [
  { id: 1, meeting_id: 1, person_id: 1, attendance_mode: "In Person", notes: "" },
  { id: 2, meeting_id: 2, person_id: 1, attendance_mode: "Absent", notes: "" },
  { id: 3, meeting_id: 2, person_id: 1, attendance_mode: "In Person", notes: "" },
  ...Array.from({ length: 1001 }, (_, i) => ({ id: i + 4, meeting_id: 1, person_id: i + 10, attendance_mode: "In Person", notes: "source ".repeat(100) })),
];
let transferred = 0;
beforeEach(() => {
  vi.useFakeTimers(); vi.setSystemTime(new Date("2026-10-21T12:00:00Z")); transferred = 0; origin.mockReset();
  origin.mockImplementation(async (input: string | Request, init?: RequestInit) => {
    const url = new URL(typeof input === "string" ? input : input.url); const table = url.pathname.split("/").pop(); let rows: any;
    if (table === "organizations") rows = { id: 10 };
    else if (table === "people") rows = [member];
    else if (table === "meetings") rows = meetings;
    else if (table === "council_terms") rows = [{ id: 1, name: "Term", start_date: "2026-01-01", end_date: "2026-11-01" }, { id: 2, name: "Next term", start_date: "2026-11-02", end_date: "2030-11-01" }];
    else if (table === "attendance") {
      const relevant = url.searchParams.get("meetings.organization_id") === "eq.10";
      const data = relevant ? attendance : [...attendance, ...Array.from({ length: 1000 }, (_, i) => ({ id: i + 2000, meeting_id: 9000, person_id: 9000, notes: "irrelevant ".repeat(1000) }))];
      const offset = Number(url.searchParams.get("offset") || "0"), limit = Number(url.searchParams.get("limit") || "1000"); rows = data.slice(offset, offset + limit);
    } else if (table === "get_meetings_with_stats") {
      expect(JSON.parse(String(init?.body)).filter_municipality_id).toBe(1);
      const filter = url.searchParams.get("meeting_id");
      const ids = filter ? filter.slice(4, -1).split(",").map(Number) : Array.from({ length: 500 }, (_, i) => i + 1);
      rows = ids.map(id => ({ meeting_id: id, motion_carried_count: 1, motion_defeated_count: 0, motion_other_count: 0, topics: ["Finance"] }));
    } else throw new Error(`Unexpected table ${table}`);
    transferred += JSON.stringify(rows).length; return Response.json(rows);
  });
});
afterEach(() => vi.useRealTimers());
it("transfers only selected meeting stats rather than all municipal history", async () => {
  const result = await getMeetings(client(), { id: 1 } as Municipality, { startDate: "2026-01-01", endDate: "2026-12-31" });
  expect(Object.keys(result.statsMap)).toEqual(["1", "2", "3"]); expect(result.statsMap[1].motion_carried_count).toBe(1);
  expect(transferred).toBeLessThan(2000); expect(result.statsComplete).toBe(true);
});
it("pages scoped attendance past 1000 rows without changing unknown/conflicting evidence results", async () => {
  const raw = await getRawPeopleData(client(), 1);
  expect(raw.attendance).toHaveLength(attendance.length); expect(transferred).toBeLessThan(1_000_000);
  expect(calculateAttendance(raw.people[0], raw.meetings, raw.attendance, raw.councilId)).toMatchObject({ total: 3, attended: 1, absent: 0, unknown: 2 });
  const summary = await getPublicCouncilSummary(1);
  expect(summary.stats["1"][1]).toEqual(calculateAttendance(raw.people[0], raw.meetings, raw.attendance, raw.councilId, { start: "2026-01-01", end: "2026-10-21" }));
  expect(summary.stats["2"][1].total).toBe(0);
  expect(JSON.stringify(summary)).not.toContain("source source");
  expect(JSON.stringify(summary).length).toBeLessThan(JSON.stringify(raw).length / 20);
});
