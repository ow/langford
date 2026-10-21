// @vitest-environment jsdom
import { act, createElement as h } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { DocumentSections } from "../../app/components/meeting/DocumentSections";
let root: Root, host: HTMLDivElement;
beforeEach(() => { (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true; host = document.createElement("div"); document.body.appendChild(host); root = createRoot(host); });
afterEach(async () => { await act(async () => root.unmount()); host.remove(); vi.unstubAllGlobals(); });
async function openReport(count = 202) {
  await act(async () => root.render(h(MemoryRouter, null, h(DocumentSections, { meetingId: 1,
    sections: Array.from({ length: count }, (_, i) => ({ id: i + 1, extracted_document_id: 9, section_title: `Section ${i + 1}` })) as any,
    extractedDocuments: [{ id: 9, title: "Large report" }] as any,
  }))));
  expect(fetch).not.toHaveBeenCalled();
  await act(async () => (host.querySelector("button") as HTMLButtonElement).click());
}
it("loads large reports in bounded batches only on expansion, and refetches corrections on reopening", async () => {
  let revision = "original";
  const fetcher = vi.fn(async (input: string) => {
    const ids = new URL(input, "https://openlangford.ca").searchParams.get("ids")!.split(",");
    expect(ids.length).toBeLessThanOrEqual(200);
    return Response.json({ texts: Object.fromEntries(ids.map(id => [id, `${revision} text ${id}`])) });
  }); vi.stubGlobal("fetch", fetcher);
  await openReport(); expect(fetcher).toHaveBeenCalledTimes(2); expect(host.textContent).toContain("original text 202");
  await act(async () => (host.querySelector("button") as HTMLButtonElement).click());
  revision = "corrected";
  await act(async () => (host.querySelector("button") as HTMLButtonElement).click());
  expect(fetcher).toHaveBeenCalledTimes(4); expect(host.textContent).toContain("corrected text 202");
});
it("offers retry after a failed section request", async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(new Response("offline", { status: 503 })).mockResolvedValueOnce(Response.json({ texts: { 1: "Recovered report" } })); vi.stubGlobal("fetch", fetcher);
  await openReport(1); expect(host.textContent).toContain("Text could not load");
  const retry = [...host.querySelectorAll("button")].find(button => button.textContent === "Try again")!;
  await act(async () => retry.click()); expect(host.textContent).toContain("Recovered report");
});
