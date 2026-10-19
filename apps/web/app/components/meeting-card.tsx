import { Link } from "react-router";
import type { Meeting } from "../lib/types";
import { formatDate, cn } from "../lib/utils";
import { Badge } from "./ui/badge";
import { Clock, ChevronRight } from "lucide-react";
import { ProvenanceBadges } from "./meeting/ProvenanceBadges";
import { TOPIC_COLORS, TOPIC_ICONS, type TopicName, TOPICS } from "../lib/topic-utils";

export interface MeetingStats {
  motion_carried_count: number;
  motion_defeated_count: number;
  motion_other_count: number;
  topics: string[];
}

interface MeetingCardProps {
  meeting: Meeting;
  stats?: MeetingStats;
}

/** Strip markdown bullet markers so AI summaries read as prose in a preview. */
function summaryPreview(summary: string) {
  return summary
    .replace(/(^|\n)\s*[-*•]\s+/g, "$1")
    .replace(/\s*\n+\s*/g, " ")
    .replace(/\s+-\s+(?=[A-Z])/g, " ")
    .trim();
}

/**
 * A single meeting row, designed to sit inside a month-grouped list
 * (the parent provides the card chrome and dividers).
 */
export function MeetingCard({ meeting, stats }: MeetingCardProps) {
  const today = new Date().toLocaleDateString("en-CA");
  const isPast = meeting.meeting_date < today;
  const hasContent =
    meeting.has_agenda ||
    meeting.agenda_url ||
    meeting.has_transcript ||
    meeting.has_minutes ||
    meeting.video_url;

  const isCancelled = meeting.status === "Cancelled";
  const isProcessing = isPast && !isCancelled && !meeting.summary;
  const isUpcoming = !isPast && !isCancelled;

  // Only surface org/type when they add information beyond the title
  const org = meeting.organization?.name;
  const metaParts = [
    org && !meeting.title.toLowerCase().includes(org.toLowerCase()) ? org : null,
    meeting.type && meeting.type !== meeting.title && meeting.type !== org
      ? meeting.type
      : null,
  ].filter(Boolean) as string[];

  const validTopics = (stats?.topics ?? [])
    .filter((t): t is TopicName => (TOPICS as readonly string[]).includes(t) && t !== "General")
    .slice(0, 4);

  const carried = stats?.motion_carried_count ?? 0;
  const defeated = stats?.motion_defeated_count ?? 0;

  return (
    <div
      className={cn(
        "relative flex w-full items-start gap-4 px-4 py-4 sm:gap-5 sm:px-5 transition-colors",
        hasContent && "group hover:bg-zinc-50",
      )}
    >
      {/* Date */}
      <div className="w-12 shrink-0 text-center">
        <div className="text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
          {formatDate(meeting.meeting_date, { weekday: "short" })}
        </div>
        <div className="text-2xl font-bold leading-tight tabular-nums text-zinc-900">
          {formatDate(meeting.meeting_date, { day: "numeric" })}
        </div>
      </div>

      {/* Main */}
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <h3
            className={cn(
              "text-base font-semibold leading-snug text-zinc-900 group-hover:text-brand-700 transition-colors",
              isCancelled && "text-zinc-500 line-through",
            )}
          >
            {hasContent ? (
              // Stretched link: the whole row is clickable without nesting
              // the source links (ProvenanceBadges) inside an <a>.
              <Link
                to={`/meetings/${meeting.id}`}
                className="after:absolute after:inset-0 focus-visible:outline-none focus-visible:after:ring-2 focus-visible:after:ring-ring"
              >
                {meeting.title}
              </Link>
            ) : (
              meeting.title
            )}
          </h3>
          {isUpcoming && <Badge variant="brand">Upcoming</Badge>}
          {isProcessing && <Badge variant="muted">Processing</Badge>}
          {isCancelled && <Badge variant="danger">Cancelled</Badge>}
        </div>

        {metaParts.length > 0 && (
          <p className="mt-0.5 text-xs text-zinc-500">{metaParts.join(" · ")}</p>
        )}

        {meeting.summary && (
          <p className="mt-1.5 max-w-[75ch] text-sm leading-relaxed text-zinc-600 line-clamp-2">
            {summaryPreview(meeting.summary)}
          </p>
        )}

        {(validTopics.length > 0 || carried + defeated > 0) && (
          <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
            {validTopics.map((topic) => {
              const Icon = TOPIC_ICONS[topic];
              return (
                <span
                  key={topic}
                  className={cn(
                    "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium",
                    TOPIC_COLORS[topic],
                  )}
                >
                  <Icon className="h-3 w-3" />
                  {topic}
                </span>
              );
            })}
            {carried + defeated > 0 && (
              <span className="ml-1 text-xs font-medium text-zinc-500">
                {carried > 0 && <span className="text-emerald-700">{carried} carried</span>}
                {carried > 0 && defeated > 0 && ", "}
                {defeated > 0 && <span className="text-red-700">{defeated} defeated</span>}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Sources & open */}
      <div className="hidden shrink-0 items-center gap-3 self-center sm:flex">
        {meeting.video_duration_seconds ? (
          <span className="flex items-center gap-1 text-xs font-medium tabular-nums text-zinc-500">
            <Clock className="h-3.5 w-3.5" />
            {Math.round(meeting.video_duration_seconds / 60)}m
          </span>
        ) : null}
        <div className="relative z-10">
          <ProvenanceBadges meeting={meeting} compact />
        </div>
        <ChevronRight
          className={cn(
            "h-5 w-5",
            hasContent ? "text-zinc-300 group-hover:text-brand-600" : "text-transparent",
          )}
        />
      </div>
    </div>
  );
}
