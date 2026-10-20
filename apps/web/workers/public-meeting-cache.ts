/// <reference types="@cloudflare/workers-types" />

// Deliberately small first rollout. Each deployment gets a new namespace;
// corrections made between deployments become visible within five minutes.
const TTL_SECONDS = 300;

type PublicMeetingCacheConfig = { version?: string; posthogKey?: string };

function onlyPostHogCookie(header: string, key: string | undefined) {
  if (!key) return false;
  // posthog-js parseName(), with this app's default persistence_name. This is
  // one configured project's exact cookie, never a ph_* or consent wildcard.
  const name = `ph_${key.replace(/\+/g, "PL").replace(/\//g, "SL").replace(/=/g, "EQ")}_posthog`;
  return header.split(";").every((part) => {
    const separator = part.indexOf("=");
    return separator > 0 && part.slice(0, separator).trim() === name;
  });
}

function cacheKey(request: Request, { version, posthogKey }: PublicMeetingCacheConfig): Request | null {
  const url = new URL(request.url);
  if (url.origin !== "https://openlangford.ca" || request.method !== "GET") return null;
  // All unknown/session cookies still bypass, even alongside valid analytics.
  const cookie = request.headers.get("cookie");
  if (cookie !== null && !onlyPostHogCookie(cookie, posthogKey)) return null;
  if (["authorization", "range", "if-none-match", "if-modified-since", "cache-control", "pragma"].some((h) => request.headers.has(h))) return null;

  const match = /^\/meetings\/(\d{4}-\d{2}-\d{2})-[a-z0-9-]+(\/documents)?(\.data)?$/.exec(url.pathname);
  if (!match) return null;
  const date = Date.parse(`${match[1]}T00:00:00Z`);
  if (!Number.isFinite(date) || new Date(date).toISOString().slice(0, 10) !== match[1] || date > Date.now() - 2 * 86400_000) return null;

  const isData = !!match[3];
  const accept = request.headers.get("accept") || "";
  if (isData ? !["", "*/*", "text/x-script"].includes(accept) : !accept.includes("text/html") || /markdown|json/i.test(accept)) return null;
  // React Router uses _routes to request only the loaders it needs. Never
  // conflate that with a full navigation payload, or with another route.
  const allowedRoute = match[2] ? "routes/meeting-documents" : "routes/meeting-detail";
  for (const [name, value] of url.searchParams) {
    if (!isData || name !== "_routes" || url.searchParams.getAll(name).length !== 1) return null;
    const routes = value.split(",");
    if (!routes.length || new Set(routes).size !== routes.length || routes.some((route) => route !== "root" && route !== allowedRoute)) return null;
  }
  // Synthetic keys are not routes. Original path (including .data), complete
  // safe query, and Worker version keep representations/deployments separate.
  url.pathname = `/__public-meeting-cache/${version}${url.pathname}`;
  return new Request(url, { method: "GET" });
}

function canStore(response: Response, isData: boolean) {
  const headers = response.headers;
  const type = headers.get("content-type") || "";
  return response.status === 200 &&
    (isData ? type.startsWith("text/x-script") : type.startsWith("text/html")) &&
    !headers.has("set-cookie") && !headers.has("location") &&
    !/private|no-store|no-cache|(?:s-maxage|max-age)\s*=\s*0(?:,|$)/i.test(headers.get("cache-control") || "") &&
    (headers.get("vary") || "").split(",").every((v) => ["", "accept", "accept-encoding"].includes(v.trim().toLowerCase()));
}

function delivery(response: Response, state: "HIT" | "MISS") {
  const delivered = new Response(response.body, response);
  // Cache only inside this guarded Worker path. Browsers/downstream proxies
  // must re-enter the session guard on every request, including after login.
  delivered.headers.set("Cache-Control", "private, no-store");
  delivered.headers.set("X-Public-Meeting-Cache", state);
  return delivered;
}

export async function publicMeetingCache(
  request: Request,
  config: PublicMeetingCacheConfig,
  ctx: Pick<ExecutionContext, "waitUntil">,
  render: (request: Request) => Promise<Response>,
): Promise<Response> {
  const key = config.version ? cacheKey(request, config) : null;
  if (!key) return render(request);
  const cache = (caches as CacheStorage & { default: Cache }).default;
  try {
    const hit = await cache.match(key);
    if (hit) return delivery(hit, "HIT");
  } catch {
    // Cache availability must never make a working page unavailable.
  }
  // The browser keeps its analytics cookie; SSR gets a cookie-free request.
  // Thus even future loader changes cannot personalize the shared response
  // from PostHog identifiers. Auth/unknown requests took the bypass above.
  const headers = new Headers(request.headers);
  headers.delete("cookie");
  const response = await render(new Request(request, { headers }));
  if (!canStore(response, new URL(request.url).pathname.endsWith(".data"))) return response;
  const stored = new Response(response.clone().body, response);
  stored.headers.set("Cache-Control", `public, max-age=${TTL_SECONDS}`);
  ctx.waitUntil(cache.put(key, stored).catch(() => {}));
  return delivery(response, "MISS");
}
