import { describe, expect, it } from "vitest";
import { civicToday, councilRoster, councilTermStatus, membershipIsActiveOn } from "../../app/lib/council-terms";

const outgoing = { start_date: "2022-11-07", end_date: "2026-11-01", name: "2022–2026" };
const incoming = { start_date: "2026-11-02", end_date: null, name: "2026–2030" };
const membership = (start: string, end: string | null = null, role = "Councillor") => ({
  start_date: start, end_date: end, role, organization: { classification: "Council" },
});

describe("council transition", () => {
  it.each([
    ["2026-10-17", "current", "upcoming"],
    ["2026-11-01", "current", "upcoming"],
    ["2026-11-02", "past", "current"],
  ])("uses taking office rather than election day on %s", (date, oldStatus, newStatus) => {
    expect(councilTermStatus(outgoing, date)).toBe(oldStatus);
    expect(councilTermStatus(incoming, date)).toBe(newStatus);
  });

  it("shows the incoming roster before it has any meetings without treating it as serving", () => {
    const people = [
      { name: "Outgoing", memberships: [membership("2022-11-07", "2026-11-01")] },
      { name: "New", memberships: [membership("2026-11-02")] },
      { name: "Re-elected", memberships: [membership("2022-11-07", "2026-11-01"), membership("2026-11-02")] },
      { name: "Staff", memberships: [{ start_date: "2026-11-02", organization: { classification: "Staff" } }] },
    ];
    expect(councilRoster(people, incoming, "2026-10-18").map(({ person, status }) => [person.name, status])).toEqual([
      ["New", "upcoming"], ["Re-elected", "upcoming"],
    ]);
    expect(councilRoster(people, outgoing, "2026-10-18").map(({ person }) => person.name)).toEqual(["Outgoing", "Re-elected"]);
  });

  it("preserves a returning member's service gap and an early departure", () => {
    const returning = { name: "Returning", memberships: [membership("2018-11-05", "2022-11-06"), membership("2026-11-02")] };
    const resigned = { name: "Resigned", memberships: [membership("2022-11-07", "2026-05-02")] };
    expect(councilRoster([returning, resigned], outgoing, "2026-10-18").map(({ person, status }) => [person.name, status])).toEqual([["Resigned", "past"]]);
    expect(membershipIsActiveOn(resigned.memberships[0], "2026-05-02")).toBe(true);
    expect(membershipIsActiveOn(resigned.memberships[0], "2026-05-03")).toBe(false);
  });

  it("uses the Vancouver calendar across the taking-office date", () => {
    // Straddle local midnight with either version of Vancouver's timezone data.
    // 07:30Z depends on whether the runtime includes the 2026 offset update.
    expect(civicToday(new Date("2026-11-02T06:30:00Z"))).toBe("2026-11-01");
    expect(civicToday(new Date("2026-11-02T08:30:00Z"))).toBe("2026-11-02");
  });
});
