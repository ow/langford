import { describe, expect, it } from "vitest";
import { councilServicePeriods, councilServiceRange } from "../../app/lib/council-service";
import type { Membership } from "../../app/lib/types";

function appointment(start: string, end: string | null, role = "Mayor"): Membership {
  return { id: Number(start.slice(0, 4)), person_id: 143, organization_id: 1, role,
    start_date: start, end_date: end || undefined, created_at: "2026-10-18",
    organization: { id: 1, name: "Council", classification: "Council", created_at: "2026-10-18" } };
}

describe("council service displayed to residents", () => {
  it("combines consecutive appointments while preserving the underlying terms", () => {
    const memberships = [appointment("2000-12-04", "2004-12-05"), appointment("2004-12-06", "2008-12-07"), appointment("2008-12-08", "2012-12-02")];
    const before = structuredClone(memberships);
    expect(councilServicePeriods({ memberships }, "2026-10-18").map(councilServiceRange)).toEqual(["2000–2012"]);
    expect(memberships).toEqual(before);
  });

  it("keeps a return after a gap, and a change of office, separate", () => {
    const memberships = [appointment("2000-12-04", "2004-12-05", "Councillor"), appointment("2004-12-06", "2012-12-02"), appointment("2013-01-01", "2014-01-01")];
    expect(councilServicePeriods({ memberships }, "2026-10-18").map((p) => [p.role, councilServiceRange(p)])).toEqual([
      ["Mayor", "2013–2014"], ["Mayor", "2004–2012"], ["Councillor", "2000–2004"],
    ]);
  });

  it("does not count a consecutive incoming appointment as service before inauguration", () => {
    const memberships = [appointment("2022-11-07", "2026-11-01", "Councillor"), appointment("2026-11-02", null, "Councillor")];
    expect(councilServicePeriods({ memberships }, "2026-10-18").map((p) => [p.status, councilServiceRange(p)])).toEqual([
      ["upcoming", "From 2026"], ["current", "2022–present"],
    ]);
    expect(councilServicePeriods({ memberships }, "2026-11-02").map(councilServiceRange)).toEqual(["2022–present"]);
  });

  it("shows sourced historic years without inventing exact appointment dates or bridging a service gap", () => {
    const periods = councilServicePeriods({ memberships: [appointment("2026-11-02", null)], council_service_history: [
      { organization_id: 1, role: "Mayor", start_year: 1993, end_year: 2022, source_url: "https://stewyoung.com/about" },
    ] }, "2026-10-18");
    expect(periods.map(councilServiceRange)).toEqual(["From 2026", "1993–2022"]);
    expect(periods[1].startDate).toBeUndefined();
    expect(periods[1].endDate).toBeUndefined();
  });
});
