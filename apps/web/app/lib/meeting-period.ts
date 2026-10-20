/** The list browses years; the calendar browses months. Both live in the URL. */
export function meetingPeriod(params: URLSearchParams, now = new Date()) {
  const rawYear = params.get("year") || "";
  const year =
    /^\d{4}$/.test(rawYear) && Number(rawYear) >= 1000
      ? Number(rawYear)
      : now.getFullYear();
  const rawMonth = params.get("month") || "";
  const month = /^(?:[1-9]|1[0-2])$/.test(rawMonth)
    ? Number(rawMonth)
    : year === now.getFullYear()
      ? now.getMonth() + 1
      : 12;
  return { year, month, monthly: params.get("view") === "calendar" };
}

export function shiftMeetingPeriod(
  params: URLSearchParams,
  offset: number,
  now = new Date(),
) {
  const { year, month, monthly } = meetingPeriod(params, now);
  const date = new Date(year, monthly ? month - 1 + offset : 0, 1);
  const next = new URLSearchParams(params);
  next.set("year", String(monthly ? date.getFullYear() : year + offset));
  if (monthly) next.set("month", String(date.getMonth() + 1));
  return next;
}

export function meetingPeriodLabel(year: number, month?: number) {
  return month === undefined
    ? String(year)
    : new Date(year, month - 1, 1).toLocaleDateString("en-CA", {
        month: "long",
        year: "numeric",
      });
}
