/** Shared anonymous-cache admission. Unknown cookies always fail closed. */
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

export function anonymousPublicRequest(request: Request, posthogKey?: string): boolean {
  const url = new URL(request.url);
  if (url.origin !== "https://openlangford.ca" || request.method !== "GET") return false;
  const cookie = request.headers.get("cookie");
  return (cookie === null || onlyPostHogCookie(cookie, posthogKey)) &&
    !["authorization", "range", "if-none-match", "if-modified-since", "cache-control", "pragma"].some((header) => request.headers.has(header));
}
