import { useState, useMemo, useEffect } from "react";
import { Link, useSearchParams } from "react-router";
import type { Meeting } from "../lib/types";
import { cn } from "../lib/utils";
import { ChevronLeft, ChevronRight } from "lucide-react";

interface CalendarViewProps {
  meetings: Meeting[];
}

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

/** Local YYYY-MM-DD key (avoids the UTC shift of toISOString). */
function dateKey(date: Date) {
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${m}-${d}`;
}

type Tone = "upcoming" | "past" | "cancelled";

function meetingTone(meeting: Meeting, todayKey: string): Tone {
  if (meeting.status === "Cancelled") return "cancelled";
  return meeting.meeting_date >= todayKey ? "upcoming" : "past";
}

const chipTone: Record<Tone, string> = {
  upcoming:
    "bg-brand-50 text-brand-800 ring-1 ring-inset ring-brand-200 hover:bg-brand-100",
  past: "bg-zinc-100 text-zinc-700 hover:bg-zinc-200",
  cancelled: "bg-zinc-50 text-zinc-400 line-through hover:bg-zinc-100",
};

function meetingLabel(meeting: Meeting) {
  return meeting.type || meeting.organization?.name || meeting.title;
}

export function CalendarView({ meetings }: CalendarViewProps) {
  const [searchParams, setSearchParams] = useSearchParams();
  const urlYear = parseInt(
    searchParams.get("year") || new Date().getFullYear().toString(),
  );

  // Track the current view date (month/year) for the calendar UI
  // Open on the current month if it has meetings; otherwise on the most
  // recent month (in the selected year) that does.
  const [currentDate, setCurrentDate] = useState(() => {
    const now = new Date();
    const month = urlYear === now.getFullYear() ? now.getMonth() : 11;
    const prefix = `${urlYear}-${String(month + 1).padStart(2, "0")}`;
    if (meetings.some((m) => m.meeting_date?.startsWith(prefix))) {
      return new Date(urlYear, month, 1);
    }
    const latest = meetings
      .map((m) => m.meeting_date)
      .filter((d): d is string => !!d && d.startsWith(String(urlYear)) && d.slice(0, 7) <= prefix)
      .sort()
      .at(-1);
    return latest
      ? new Date(Number(latest.slice(0, 4)), Number(latest.slice(5, 7)) - 1, 1)
      : new Date(urlYear, month, 1);
  });

  // Sync the calendar month when the URL year changes from the parent selector
  useEffect(() => {
    if (currentDate.getFullYear() !== urlYear) {
      setCurrentDate(new Date(urlYear, 0, 1));
    }
  }, [urlYear]);

  const year = currentDate.getFullYear();
  const month = currentDate.getMonth();
  const todayKey = dateKey(new Date());

  const firstDayOfMonth = new Date(year, month, 1);
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const startingDayOfWeek = firstDayOfMonth.getDay();

  const calendarDays = useMemo(() => {
    const days: (Date | null)[] = [];
    for (let i = 0; i < startingDayOfWeek; i++) days.push(null);
    for (let i = 1; i <= daysInMonth; i++) days.push(new Date(year, month, i));
    while (days.length % 7 !== 0) days.push(null);
    return days;
  }, [year, month, daysInMonth, startingDayOfWeek]);

  const meetingsByDay = useMemo(() => {
    const map: Record<string, Meeting[]> = {};
    for (const m of meetings) {
      (map[m.meeting_date] ||= []).push(m);
    }
    return map;
  }, [meetings]);

  const monthMeetings = useMemo(() => {
    const prefix = `${year}-${String(month + 1).padStart(2, "0")}-`;
    return meetings
      .filter((m) => m.meeting_date.startsWith(prefix))
      .sort((a, b) => a.meeting_date.localeCompare(b.meeting_date));
  }, [meetings, year, month]);

  const updateYearParam = (newYear: number) => {
    const newParams = new URLSearchParams(searchParams);
    newParams.set("year", newYear.toString());
    setSearchParams(newParams);
  };

  const goTo = (date: Date) => {
    if (date.getFullYear() !== year) updateYearParam(date.getFullYear());
    setCurrentDate(date);
  };

  const nextMonth = () => goTo(new Date(year, month + 1, 1));
  const prevMonth = () => goTo(new Date(year, month - 1, 1));
  const goToday = () => {
    const now = new Date();
    goTo(new Date(now.getFullYear(), now.getMonth(), 1));
  };

  const monthName = new Intl.DateTimeFormat("en-US", { month: "long" }).format(
    currentDate,
  );
  const isCurrentMonth = todayKey.startsWith(
    `${year}-${String(month + 1).padStart(2, "0")}`,
  );

  const navButton =
    "inline-flex h-8 w-8 items-center justify-center rounded-md text-zinc-500 transition-colors hover:bg-zinc-100 hover:text-zinc-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500";

  return (
    <div className="bg-white">
      {/* Month navigation */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-100 px-4 py-3 sm:px-5">
        <div className="flex items-center gap-1">
          <button type="button" onClick={prevMonth} className={navButton} aria-label="Previous month">
            <ChevronLeft className="h-4 w-4" />
          </button>
          <h2 className="min-w-[9.5rem] text-center text-base font-semibold text-zinc-900" aria-live="polite">
            {monthName} <span className="font-normal text-zinc-500 tabular-nums">{year}</span>
          </h2>
          <button type="button" onClick={nextMonth} className={navButton} aria-label="Next month">
            <ChevronRight className="h-4 w-4" />
          </button>
          {!isCurrentMonth && (
            <button
              type="button"
              onClick={goToday}
              className="ml-2 rounded-md border border-zinc-200 px-2.5 py-1 text-xs font-medium text-zinc-600 transition-colors hover:border-brand-300 hover:text-brand-700"
            >
              Today
            </button>
          )}
        </div>

        <div className="flex items-center gap-4 text-xs text-zinc-500">
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-brand-100 ring-1 ring-inset ring-brand-300" />
            Upcoming
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-sm bg-zinc-200" />
            Past
          </span>
        </div>
      </div>

      {/* Weekday headers */}
      <div className="grid grid-cols-7 border-b border-zinc-100">
        {WEEKDAYS.map((day) => (
          <div key={day} className="py-2 text-center text-xs font-medium text-zinc-500">
            <span className="sm:hidden">{day[0]}</span>
            <span className="hidden sm:inline">{day}</span>
          </div>
        ))}
      </div>

      {/* Desktop grid with meeting chips */}
      <div className="hidden grid-cols-7 sm:grid">
        {calendarDays.map((date, idx) => {
          if (!date) {
            return (
              <div
                key={`empty-${idx}`}
                className="min-h-[104px] border-b border-r border-zinc-100 bg-zinc-50/50 [&:nth-child(7n)]:border-r-0"
              />
            );
          }
          const key = dateKey(date);
          const dayMeetings = meetingsByDay[key] || [];
          const isToday = key === todayKey;

          return (
            <div
              key={key}
              className={cn(
                "min-h-[104px] border-b border-r border-zinc-100 p-1.5 [&:nth-child(7n)]:border-r-0",
                isToday && "bg-brand-50/40",
              )}
            >
              <span
                className={cn(
                  "mb-1 inline-flex h-6 min-w-6 items-center justify-center rounded-full px-1 text-xs tabular-nums",
                  isToday
                    ? "bg-brand-100 font-semibold text-brand-800"
                    : "text-zinc-500",
                )}
                aria-label={isToday ? `${date.getDate()} (today)` : undefined}
              >
                {date.getDate()}
              </span>
              <div className="space-y-1">
                {dayMeetings.map((meeting) => {
                  const tone = meetingTone(meeting, todayKey);
                  return (
                    <Link
                      key={meeting.id}
                      to={`/meetings/${meeting.id}`}
                      title={meeting.title}
                      className={cn(
                        "block truncate rounded-md px-1.5 py-1 text-xs font-medium leading-tight transition-colors",
                        chipTone[tone],
                      )}
                    >
                      {meetingLabel(meeting)}
                    </Link>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

      {monthMeetings.length === 0 && (
        <p className="hidden px-5 py-3 text-sm text-zinc-500 sm:block">
          No meetings in {monthName} {year}.
        </p>
      )}

      {/* Mobile: compact month grid + agenda list */}
      <div className="sm:hidden">
        <div className="grid grid-cols-7 gap-y-1 px-2 py-2">
          {calendarDays.map((date, idx) => {
            if (!date) return <div key={`m-empty-${idx}`} />;
            const key = dateKey(date);
            const dayMeetings = meetingsByDay[key] || [];
            const isToday = key === todayKey;
            const hasUpcoming = dayMeetings.some(
              (m) => meetingTone(m, todayKey) === "upcoming",
            );
            return (
              <div key={key} className="flex flex-col items-center gap-0.5 py-1">
                <span
                  className={cn(
                    "inline-flex h-7 w-7 items-center justify-center rounded-full text-xs tabular-nums",
                    isToday
                      ? "bg-brand-100 font-semibold text-brand-800"
                      : dayMeetings.length
                        ? "font-semibold text-zinc-900"
                        : "text-zinc-400",
                  )}
                >
                  {date.getDate()}
                </span>
                <span
                  className={cn(
                    "h-1 w-1 rounded-full",
                    dayMeetings.length === 0
                      ? "bg-transparent"
                      : hasUpcoming
                        ? "bg-brand-500"
                        : "bg-zinc-400",
                  )}
                  aria-hidden="true"
                />
              </div>
            );
          })}
        </div>

        <div className="border-t border-zinc-100">
          {monthMeetings.length === 0 ? (
            <p className="px-4 py-5 text-sm text-zinc-500">
              No meetings in {monthName} {year}.
            </p>
          ) : (
            <ul className="divide-y divide-zinc-100">
              {monthMeetings.map((meeting) => {
                const tone = meetingTone(meeting, todayKey);
                const [y, m, d] = meeting.meeting_date.split("-").map(Number);
                const date = new Date(y, m - 1, d);
                return (
                  <li key={meeting.id}>
                    <Link
                      to={`/meetings/${meeting.id}`}
                      className="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-zinc-50"
                    >
                      <div
                        className={cn(
                          "flex w-11 shrink-0 flex-col items-center rounded-lg py-1",
                          tone === "upcoming" ? "bg-brand-50 text-brand-800" : "bg-zinc-100 text-zinc-600",
                        )}
                      >
                        <span className="text-[11px] leading-none">{WEEKDAYS[date.getDay()]}</span>
                        <span className="mt-0.5 text-base font-semibold leading-none tabular-nums">{d}</span>
                      </div>
                      <div className="min-w-0 flex-1">
                        <p
                          className={cn(
                            "truncate text-sm font-medium",
                            tone === "cancelled" ? "text-zinc-400 line-through" : "text-zinc-900",
                          )}
                        >
                          {meetingLabel(meeting)}
                        </p>
                        <p className="truncate text-xs text-zinc-500">
                          {tone === "upcoming" ? "Upcoming" : tone === "cancelled" ? "Cancelled" : "Past"}
                          {meeting.title !== meetingLabel(meeting) && ` · ${meeting.title}`}
                        </p>
                      </div>
                      <ChevronRight className="h-4 w-4 shrink-0 text-zinc-300" aria-hidden="true" />
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
