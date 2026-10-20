import { createClient } from "@supabase/supabase-js";
import { expect, it } from "vitest";
import { getMeetingById, getDocumentSectionsForMeeting } from "../../app/services/meetings";

it("loads meeting timing/section metadata without transferring deferred text, while explorer callers retain full text", async () => {
  const transcriptText = "public transcript ".repeat(50_000);
  const reportText = "public report ".repeat(50_000);
  const records: Record<string, Record<string, unknown>[]> = {
    meetings: [{ id: 1, meeting_date: "2026-10-05", chair_person_id: null }],
    documents: [{ id: 20 }],
    transcript_segments: [{ id: 30, start_time: 4, end_time: 8, person_id: null, text_content: transcriptText }],
    document_sections: [{ id: 40, document_id: 20, section_title: "Report", section_order: 1, section_text: reportText }],
  };
  let transferred = 0;
  const client = createClient("https://database.example", "public-key", { global: {
    fetch: async (input) => {
      const url = new URL(String(input));
      const table = url.pathname.split("/").pop()!;
      let rows = records[table] || [];
      // PostgREST projects database columns before returning JSON; this fake
      // transport measures bytes the service actually asks it to transfer.
      if (["transcript_segments", "document_sections"].includes(table)) {
        const fields = (url.searchParams.get("select") || "").split(",").map((field) => field.trim());
        rows = rows.map((row) => Object.fromEntries(Object.entries(row).filter(([key]) => fields.includes(key))));
      }
      const body = JSON.stringify(table === "meetings" ? rows[0] : rows);
      transferred += new TextEncoder().encode(body).length;
      return new Response(body, { headers: { "Content-Type": "application/json" } });
    },
  } });

  const full = await getMeetingById(client, "1");
  const fullSections = await getDocumentSectionsForMeeting(client, "1");
  const fullBytes = transferred;
  transferred = 0;
  const metadata = await getMeetingById(client, "1", { includeText: false });
  const sections = await getDocumentSectionsForMeeting(client, "1", { includeText: false });
  expect(full.transcript[0].text_content).toBe(transcriptText);
  expect(fullSections[0].section_text).toBe(reportText);
  expect(metadata.transcript[0]).toMatchObject({ id: 30, start_time: 4, end_time: 8 });
  expect(metadata.transcript[0]).not.toHaveProperty("text_content");
  expect(sections[0]).toMatchObject({ id: 40, document_id: 20, section_title: "Report" });
  expect(sections[0]).not.toHaveProperty("section_text");
  expect(transferred).toBeLessThan(fullBytes / 100);
});
