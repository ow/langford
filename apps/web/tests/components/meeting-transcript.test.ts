// @vitest-environment jsdom
import { act, createElement as h } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useMeetingTranscript } from "../../app/hooks/useMeetingTranscript";

let root: Root;
let host: HTMLDivElement;
let state: ReturnType<typeof useMeetingTranscript>;
function Reader({ id = 4, enabled = false, hasTranscript = true }) {
  state = useMeetingTranscript(id, hasTranscript, enabled);
  return h("output", null, JSON.stringify({ status: state.status, texts: state.texts }));
}
async function show(props = {}) { await act(async () => root.render(h(Reader, props))); }
beforeEach(() => {
  (globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
  host = document.createElement("div"); document.body.appendChild(host); root = createRoot(host);
});
afterEach(async () => { await act(async () => root.unmount()); host.remove(); vi.unstubAllGlobals(); });

it("transfers no transcript on a summary view, then loads searchable text on demand", async () => {
  const words = { 41: "A complete phrase to find in transcript search" };
  const fetcher = vi.fn(async () => Response.json({ texts: words })); vi.stubGlobal("fetch", fetcher);
  await show(); expect(fetcher).not.toHaveBeenCalled(); expect(state.status).toBe("idle");
  await show({ enabled: true });
  expect(fetcher).toHaveBeenCalledTimes(1); expect(state.texts).toEqual(words); expect(state.status).toBe("ready");
  await show({ enabled: true }); expect(fetcher).toHaveBeenCalledTimes(1);
});

it("does not let a previous meeting's late response overwrite the new meeting", async () => {
  const pending: ((response: Response) => void)[] = [];
  vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(resolve => pending.push(resolve))));
  await show({ enabled: true }); await show({ id: 5, enabled: true });
  expect(state.texts).toBeNull();
  await act(async () => pending[1](Response.json({ texts: { 51: "New meeting" } })));
  await act(async () => pending[0](Response.json({ texts: { 41: "Old meeting" } })));
  expect(state.texts).toEqual({ 51: "New meeting" });
});

it("shows failure and permits retry without treating an error payload as an empty transcript", async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(Response.json({ error: "unavailable" }, { status: 503 }))
    .mockResolvedValueOnce(Response.json({ texts: { 41: "Recovered" } })); vi.stubGlobal("fetch", fetcher);
  await show({ enabled: true }); expect(state.status).toBe("error"); expect(state.texts).toBeNull();
  await act(async () => state.retry()); expect(state.status).toBe("ready"); expect(state.texts).toEqual({ 41: "Recovered" });
});

it("does not fetch a meeting with no transcript even when requested", async () => {
  const fetcher = vi.fn(); vi.stubGlobal("fetch", fetcher);
  await show({ enabled: true, hasTranscript: false }); expect(fetcher).not.toHaveBeenCalled();
});
