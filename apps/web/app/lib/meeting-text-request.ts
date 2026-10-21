/** The public text API accepts bounded, unambiguous selectors only. */
export function parseMeetingTextRequest(url: URL): { kind: "transcript"; meetingId: number } | { kind: "sections"; ids: number[] } | null {
  const params = url.searchParams;
  const kind = params.get("kind");
  const allowed = kind === "transcript" ? ["kind", "meeting"] : ["kind", "ids"];
  for (const key of params.keys()) if (!allowed.includes(key) || params.getAll(key).length !== 1) return null;
  const positiveId = (value: string) => /^[1-9]\d*$/.test(value) && Number.isSafeInteger(Number(value));
  if (kind === "transcript") {
    const meeting = params.get("meeting") || "";
    return positiveId(meeting) ? { kind, meetingId: Number(meeting) } : null;
  }
  if (kind === "sections") {
    const raw = params.get("ids") || "";
    const ids = raw ? raw.split(",") : [];
    return ids.length <= 200 && ids.every(positiveId) && new Set(ids).size === ids.length
      ? { kind, ids: ids.map(Number) } : null;
  }
  return null;
}
