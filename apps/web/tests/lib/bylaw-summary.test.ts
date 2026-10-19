import { describe, expect, it } from "vitest";
import { amendmentsFromText, bylawLead, bylawStatus, parseBylawSummary } from "../../app/lib/bylaw-summary";

const STRUCTURED = `Sets how elections run.

Key rules:
- Advance voting is 8 am to 8 pm.
- Remove signs within 48 hours.

Who it affects: Voters and candidates.`;

describe("parseBylawSummary", () => {
  it("splits the structured summary", () => {
    expect(parseBylawSummary(STRUCTURED)).toEqual({
      summary: "Sets how elections run.",
      keyRules: ["Advance voting is 8 am to 8 pm.", "Remove signs within 48 hours."],
      whoItAffects: "Voters and candidates.",
    });
  });

  it("treats a plain paragraph as the summary", () => {
    expect(parseBylawSummary("Just one paragraph.")).toEqual({
      summary: "Just one paragraph.",
      keyRules: [],
      whoItAffects: null,
    });
    expect(bylawLead(null)).toBe("");
    expect(bylawLead(STRUCTURED)).toBe("Sets how elections run.");
  });
});

describe("bylawStatus", () => {
  it("labels statuses", () => {
    expect(bylawStatus("Amended")).toEqual({ label: "In force, as amended", tone: "success" });
    expect(bylawStatus("In force")?.label).toBe("In force");
    expect(bylawStatus("Repealed")?.tone).toBe("danger");
    expect(bylawStatus(null)).toBeNull();
  });
});

describe("amendmentsFromText", () => {
  it("reads a consolidation's amendment table", () => {
    const text = "CONSOLIDATED\nELECTIONS BYLAW NO. 1819\nAmendment #1 2022 (Elections Bylaw)\n2057\nMay 16, 2022\nAmendment #2 2026 (Elections Bylaw)  \n2267\nMay 19, 2026\n";
    expect(amendmentsFromText(text)).toEqual([
      { bylawNumber: "2057", adopted: "May 16, 2022" },
      { bylawNumber: "2267", adopted: "May 19, 2026" },
    ]);
    expect(amendmentsFromText("BYLAW NO. 2239")).toEqual([]);
  });
});
