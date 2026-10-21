// @vitest-environment jsdom
import { act, createElement as h } from "react";
import { createRoot } from "react-dom/client";
import { createMemoryRouter, RouterProvider, useLoaderData, Outlet } from "react-router";
import { expect, it, vi } from "vitest";
import MeetingDetail from "../../app/routes/meeting-detail";
vi.mock("../../app/components/meeting/VideoWithSidebar", () => ({ VideoWithSidebar: ({ videoPlayer }: any) => h("button", { onClick: () => videoPlayer.setVideoEnabled(true) }, "Play meeting") }));
function Page() { return h(MeetingDetail, { loaderData: useLoaderData() }); }
it("does not carry playback demand into a summary-only navigation to another meeting", async () => {
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  const fetcher = vi.fn(async (input: string) => Response.json(input.startsWith("/api/meeting-text") ? { texts: { 101: "First meeting words" } } : {})); vi.stubGlobal("fetch", fetcher);
  const router = createMemoryRouter([{ id: "root", loader: () => ({ user: null }), Component: Outlet, children: [{ path: "/meetings/:id", loader: ({ params }) => ({
    meeting: { id: Number(params.id), title: "Regular Council", meeting_date: "2026-01-01", video_url: "https://example.com/video", summary: "Summary" },
    agendaItems: [], transcript: [{ id: Number(params.id) * 100 + 1, start_time: 0, end_time: 20 }], attendance: [], people: {}, activeCouncilMemberIds: [], documentSections: [], extractedDocuments: [], attendanceInfo: {}, councilTerm: null,
  }), Component: Page }] }], { initialEntries: ["/meetings/1"] });
  const host = document.createElement("div"); document.body.appendChild(host); const root = createRoot(host);
  try {
    await act(async () => root.render(h(RouterProvider, { router })));
    expect(fetcher.mock.calls.filter(([url]) => url.startsWith("/api/meeting-text"))).toHaveLength(0);
    const play = [...host.querySelectorAll("button")].find(button => button.textContent === "Play meeting")!;
    await act(async () => play.click());
    expect(fetcher.mock.calls.filter(([url]) => url.startsWith("/api/meeting-text"))).toHaveLength(1);
    await act(async () => { await router.navigate("/meetings/2"); });
    expect(fetcher.mock.calls.filter(([url]) => url.startsWith("/api/meeting-text"))).toHaveLength(1);
    await act(async () => { await router.navigate("/meetings/2#transcript=201"); window.location.hash = "#transcript=201"; window.dispatchEvent(new HashChangeEvent("hashchange")); });
    expect(fetcher.mock.calls.filter(([url]) => url.startsWith("/api/meeting-text"))).toHaveLength(2);
    expect(host.querySelector('[role="dialog"][aria-label="Transcript"]')?.getAttribute("aria-hidden")).toBe("false");
  } finally { await act(async () => root.unmount()); router.dispose(); host.remove(); window.history.replaceState(null, "", "/"); vi.unstubAllGlobals(); }
});
