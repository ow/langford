import { formatDate } from "../lib/utils";

export function CalendarProvenance({ meeting }: { meeting: { calendar_source_id?: number | null; calendar?: any; meeting_date: string; status?: string; has_agenda?: boolean; has_minutes?: boolean; has_transcript?: boolean; summary?: string; meta?: any } }) {
  const calendar = meeting.calendar_source_id && (meeting.calendar ?? meeting.meta?.calendar);
  if (!calendar) return null;
  const checked = new Date(calendar.verified_at);
  const stale = !Number.isFinite(checked.getTime()) || Date.now() - checked.getTime() > 48 * 60 * 60 * 1000;
  const content = meeting.has_agenda || meeting.has_minutes || meeting.has_transcript || meeting.summary;
  const datePassed = meeting.meeting_date < new Intl.DateTimeFormat("en-CA", { timeZone: "America/Vancouver" }).format(new Date());
  const label = meeting.status === "Cancelled" ? "Cancelled" : content ? "Official calendar" : datePassed ? "Scheduled date passed; occurrence unconfirmed" : "Scheduled";
  let source: URL;
  try { source = new URL(calendar.source_url); if (source.protocol !== "https:" || !["langford.ca", "pub-langford.escribemeetings.com"].includes(source.hostname)) return null; } catch { return null; }
  return <p className="mt-2 text-xs text-zinc-500">
    <span className="font-semibold">{label}</span>{" · "}
    <a href={source.href} target="_blank" rel="noopener noreferrer" className="underline">Official source</a>
    {Number.isFinite(checked.getTime()) && <> · Schedule checked {formatDate(checked.toISOString().slice(0, 10))}</>}
    {calendar.start_time ? ` · ${calendar.start_time} (Langford time)` : " · Time not published"}
    {stale && " · Schedule check overdue"}
    {!content && meeting.status !== "Cancelled" && " · Agenda not yet published"}
  </p>;
}
