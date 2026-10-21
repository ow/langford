import { build } from "esbuild";
import { Miniflare } from "miniflare";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { beforeAll, expect, it } from "vitest";

let script: string;
const pdf = readFileSync(new URL("../fixtures/langford-2026-calendar.pdf", import.meta.url)).toString("base64");
beforeAll(async () => {
  const result = await build({
    stdin: {
      contents: `import { discoverCalendarEvents } from "./app/services/calendar-sync";
        export default { async fetch() {
          try { return Response.json(await discoverCalendarEvents(new Date("2026-10-20T16:00:00Z"))); }
          catch (error) { return new Response(error.message, {status:500}); }
        } };`,
      resolveDir: fileURLToPath(new URL("../../", import.meta.url)),
    },
    bundle: true, write: false, format: "esm", platform: "browser", target: "es2022",
  });
  script = result.outputFiles[0].text;
});

it.each([200, 302])("discovers official events in Workers and rejects source redirects (HTTP %s)", async status => {
  const runtime = new Miniflare({
    workers: [
      {name:"calendar", modules:true, compatibilityDate:"2026-02-10", script, outboundService:"official-sources"},
      {name:"official-sources", modules:true, compatibilityDate:"2026-02-10", bindings:{PDF:pdf, STATUS:status},
        script:`export default { async fetch(request,env) {
          const host = new URL(request.url).hostname;
          if (host === "pub-langford.escribemeetings.com") {
            return env.STATUS === 302 ? new Response(null,{status:302,headers:{Location:"https://untrusted.invalid/"}}) : Response.json({d:[]});
          }
          if (host === "langford.ca") return new Response(Uint8Array.from(atob(env.PDF),x=>x.charCodeAt(0)));
          throw new Error("Unexpected redirect destination");
        }};`},
    ],
  });
  try {
    const response = await runtime.dispatchFetch("https://calendar.test/");
    if (status === 200) {
      expect(response.status, await response.clone().text()).toBe(200);
      const discovery = await response.json() as any;
      expect(discovery.events).toHaveLength(6);
      expect(discovery.events[0]).toMatchObject({title:"Inauguration",start_time:null});
      expect(discovery.warnings).toEqual([]);
    } else {
      expect(response.status).toBe(500);
      expect(await response.text()).toContain("Official calendar HTTP 302");
    }
  } finally { await runtime.dispose(); }
}, 15_000);
