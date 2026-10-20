import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { publicMeetingCache } from "../../workers/public-meeting-cache";

const path = "/meetings/2026-10-05-regular-council";
let entries: Map<string, { response: Response; expires: number }>;
let jobs: Promise<unknown>[];
const ctx = { waitUntil: (job: Promise<unknown>) => jobs.push(job) };
const request = (suffix = "", init?: RequestInit) => new Request(`https://openlangford.ca${path}${suffix}`, {
  headers: { Accept: suffix.split("?")[0].endsWith(".data") ? "*/*" : "text/html" }, ...init,
});
const html = (body = "public meeting", init?: ResponseInit) => new Response(body, {
  headers: { "Content-Type": "text/html; charset=utf-8", "X-Record": "retained" }, ...init,
});
const serve = (req: Request, render: () => Promise<Response>, version = "deploy-a") => publicMeetingCache(req, version, ctx, render);

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-10-20T15:30:00Z"));
  entries = new Map(); jobs = [];
  // Model the platform's expiry and response cloning, not the admission policy.
  vi.stubGlobal("caches", { default: {
    match: async (key: Request) => {
      const entry = entries.get(key.url);
      return entry && entry.expires > Date.now() ? entry.response.clone() : undefined;
    },
    put: async (key: Request, response: Response) => {
      const seconds = Number(/max-age=(\d+)/.exec(response.headers.get("cache-control") || "")?.[1]);
      entries.set(key.url, { response: new Response(await response.arrayBuffer(), response), expires: Date.now() + seconds * 1000 });
    },
  } });
});
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

it("reuses anonymous historical HTML, preserves content/status/headers, expires in five minutes and invalidates on deploy", async () => {
  const render = vi.fn(async () => html());
  const first = await serve(request(), render); await Promise.all(jobs);
  const hit = await serve(request(), render);
  expect(first.headers.get("X-Public-Meeting-Cache")).toBe("MISS");
  expect(hit.headers.get("X-Public-Meeting-Cache")).toBe("HIT");
  expect(await hit.text()).toBe("public meeting");
  expect(hit.status).toBe(200);
  expect(hit.headers.get("X-Record")).toBe("retained");
  expect(hit.headers.get("Cache-Control")).toBe("private, no-store");
  expect(render).toHaveBeenCalledTimes(1);
  await serve(request(), render, "deploy-b"); await Promise.all(jobs);
  expect(render).toHaveBeenCalledTimes(2);
  vi.advanceTimersByTime(300_001);
  await serve(request(), render);
  expect(render).toHaveBeenCalledTimes(3);
});

it("keeps full and partial React Router navigation payloads, documents, and HTML separate", async () => {
  const variants = ["", ".data", ".data?_routes=routes%2Fmeeting-detail", ".data?_routes=root", ".data?_routes=root,routes%2Fmeeting-detail", "/documents", "/documents.data?_routes=routes%2Fmeeting-documents"];
  const render = vi.fn(async (suffix: string) => suffix.split("?")[0].endsWith(".data")
    ? new Response(`router-stream:${suffix}`, { headers: { "Content-Type": "text/x-script" } }) : html(`html:${suffix}`));
  for (const suffix of variants) { await serve(request(suffix), () => render(suffix)); await Promise.all(jobs); }
  for (const suffix of variants) {
    const hit = await serve(request(suffix), () => render(suffix));
    expect(hit.headers.get("X-Public-Meeting-Cache")).toBe("HIT");
    expect(await hit.text()).toBe(`${suffix.split("?")[0].endsWith(".data") ? "router-stream" : "html"}:${suffix}`);
  }
  expect(render).toHaveBeenCalledTimes(variants.length);
});

it.each([
  { Cookie: "sb-session=signed-in" }, { Cookie: "analytics=anonymous" },
  { Authorization: "Bearer session" }, { Range: "bytes=0-9" },
  { "If-None-Match": "etag" }, { "If-Modified-Since": "Mon, 05 Oct 2026 00:00:00 GMT" },
  { "Cache-Control": "no-cache" }, { Pragma: "no-cache" },
] as Record<string, string>[])("never reads or writes shared content for request headers %j", async (headers) => {
  await serve(request(), async () => html()); await Promise.all(jobs);
  const render = vi.fn(async () => html("session-specific"));
  const response = await serve(request("", { headers: { Accept: "text/html", ...headers } }), render);
  expect(await response.text()).toBe("session-specific");
  expect(render).toHaveBeenCalledTimes(1);
  expect(entries.size).toBe(1);
});

it.each([
  ["/admin/pipeline", "GET"], ["/meetings", "GET"], ["/meetings/42", "GET"],
  ["/meetings/2026-10-20-regular-council", "GET"], ["/meetings/2026-02-30-regular-council", "GET"],
  [path, "POST"], [path, "HEAD"], [path + "?q=unsafe", "GET"],
  [path + ".data?_routes=routes/admin-pipeline", "GET"],
  [path + ".data?_routes=root&_routes=routes/meeting-detail", "GET"],
  [path + ".data?_routes=", "GET"], [path + ".data?extra=unsafe", "GET"],
  [path + "/documents.data?_routes=routes/meeting-detail", "GET"],
  [path + "/summary.md", "GET"], [path + "/documents/12/content.md", "GET"],
])("bypasses unsupported route/query/method %s %s", async (pathname, method) => {
  const isData = pathname.split("?")[0].endsWith(".data");
  await serve(new Request(`https://openlangford.ca${pathname}`, { method, headers: { Accept: isData ? "*/*" : "text/html" } }), async () =>
    new Response("origin response", { headers: { "Content-Type": isData ? "text/x-script" : "text/html" } }));
  await Promise.all(jobs); expect(entries.size).toBe(0);
});

it.each(["text/markdown", "text/html, text/markdown", "application/json"])("preserves content negotiation for %s", async (accept) => {
  await serve(request(), async () => html()); await Promise.all(jobs);
  const negotiated = await serve(request("", { headers: { Accept: accept } }), async () => new Response("negotiated content"));
  expect(await negotiated.text()).toBe("negotiated content");
});

it.each([
  { status: 500 }, { status: 404 }, { status: 302, headers: { Location: "/login" } },
  { headers: { "Set-Cookie": "session=renewed" } }, { headers: { "Cache-Control": "private" } },
  { headers: { "Cache-Control": "no-store" } }, { headers: { "Cache-Control": "max-age=0" } },
  { headers: { Vary: "Cookie" } },
  { headers: { "Content-Type": "application/json" } },
] as ResponseInit[])("never caches errors, redirects or responses with unsafe headers %j", async (init) => {
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type")) headers.set("Content-Type", "text/html");
  const render = vi.fn(async () => new Response("origin response", { ...init, headers }));
  const response = await serve(request(), render); await Promise.all(jobs);
  expect(response.status).toBe(init.status || 200);
  for (const [name, value] of headers) expect(response.headers.get(name)).toBe(value);
  await serve(request(), render);
  expect(render).toHaveBeenCalledTimes(2); expect(entries.size).toBe(0);
});

it("fails open when cache reads/writes fail and bypasses missing version metadata", async () => {
  vi.stubGlobal("caches", { default: { match: async () => { throw Error("unavailable"); }, put: async () => { throw Error("unavailable"); } } });
  expect(await (await serve(request(), async () => html())).text()).toBe("public meeting");
  await Promise.all(jobs);
  const response = await publicMeetingCache(request(), undefined, ctx, async () => html("uncached"));
  expect(await response.text()).toBe("uncached");
  expect(response.headers.has("X-Public-Meeting-Cache")).toBe(false);
});
