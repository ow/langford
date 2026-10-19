import { Link } from "react-router";
import type { Meeting } from "../lib/types";
import { formatDate, cn } from "../lib/utils";
import { Badge } from "./ui/badge";
import {
  Calendar,
  Clock,
  ChevronRight,
} from "lucide-react";
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

export function MeetingCard({ meeting, stats }: MeetingCardProps) {
  const today = new Date().toLocaleDateString("en-CA");
  const isPast = meeting.meeting_date < today;
  const hasContent =
    meeting.has_agenda ||
    meeting.agenda_url ||
    meeting.has_transcript ||
    meeting.has_minutes ||
    meeting.video_url;

  const statusColors: Record<string, string> = {
    Scheduled: "bg-zinc-50 text-zinc-600 border-zinc-200",
    Planned: "bg-amber-50 text-amber-700 border-amber-200",
    Occurred: "bg-brand-50 text-brand-700 border-brand-200",
    Completed: "bg-emerald-50 text-emerald-700 border-emerald-200",
    Cancelled: "bg-rose-50 text-rose-700 border-rose-200",
  };

  const status = meeting.status || (isPast ? "Completed" : "Planned");
  // Filter topics to valid TopicName values, exclude General, limit to 4
  const validTopics = (stats?.topics ?? [])
    .filter((t): t is TopicName => (TOPICS as readonly string[]).includes(t) && t !== "General")
    .slice(0, 4);

  const totalMotions = stats
    ? stats.motion_carried_count + stats.motion_defeated_count + stats.motion_other_count
    : 0;

  // Truncate summary to ~150 chars
  const truncatedSummary = meeting.summary
    ? meeting.summary.length > 150
      ? meeting.summary.substring(0, 150).replace(/\s+\S*$/, "") + "..."
      : meeting.summary
    : null;

  const ContentWrapper = hasContent ? Link : "div";
  const contentWrapperProps = hasContent ? { to: `/meetings/${meeting.id}` } : {};

  return (
    <div
      className={cn(
        "block w-full bg-white rounded-xl border border-zinc-200 shadow-sm transition-all overflow-hidden",
        hasContent &&
          "group hover:shadow-md hover:border-brand-400 cursor-pointer",
      )}
    >
      <div className="flex w-full flex-col lg:flex-row items-stretch">
        <ContentWrapper
          {...(contentWrapperProps as any)}
          className={cn(
            "flex min-w-0 flex-1 flex-col lg:flex-row items-stretch",
            hasContent && "cursor-pointer",
          )}
        >
          {/* Date & Status Sidebar (Desktop) / Header (Mobile) */}
          <div className="bg-zinc-50/50 border-b lg:border-b-0 lg:border-r border-zinc-100 p-5 flex flex-row lg:flex-col justify-between lg:justify-start items-center lg:items-start gap-4 lg:w-44 lg:shrink-0">
            <div className="flex flex-col items-start gap-1">
              <div className="flex items-center gap-2 text-zinc-500 text-xs font-bold uppercase tracking-wider">
                <Calendar className="h-3.5 w-3.5" />
                {formatDate(meeting.meeting_date, {
                  month: "short",
                  year: "numeric",
                })}
              </div>
              <div className="text-2xl font-black text-zinc-900 leading-none">
                {formatDate(meeting.meeting_date, { day: "numeric" })}
              </div>
            </div>

            <Badge
              variant="outline"
              className={cn(
                "font-bold px-2 py-0.5 text-[10px] uppercase tracking-wider shadow-sm",
                statusColors[status] ||
                  "bg-zinc-50 text-zinc-600 border-zinc-200",
              )}
            >
              {status}
            </Badge>
          </div>

          {/* Main Content */}
          <div className="min-w-0 flex-1 p-5 lg:p-6 flex flex-col justify-center">
            <div className="flex items-center gap-2 mb-2">
              <Badge
                variant="secondary"
                className="bg-zinc-100 text-zinc-600 border-transparent text-[10px] font-bold uppercase tracking-tight py-0"
              >
                {meeting.organization?.name || "Meeting"}
              </Badge>
              {meeting.type && meeting.type !== meeting.organization?.name && (
                <span className="text-[10px] text-zinc-400 font-bold uppercase tracking-widest">
                  {meeting.type}
                </span>
              )}
            </div>

            <h3 className="text-xl font-extrabold text-zinc-900 group-hover:text-brand-600 transition-colors mb-2 leading-tight">
              {meeting.title}
            </h3>

            {/* Topic Chips */}
            {validTopics.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mb-2">
                {validTopics.map((topic) => {
                  const Icon = TOPIC_ICONS[topic];
                  return (
                    <span
                      key={topic}
                      className={cn(
                        "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold border",
                        TOPIC_COLORS[topic],
                      )}
                    >
                      <Icon className="h-3 w-3" />
                      {topic}
                    </span>
                  );
                })}
              </div>
            )}

            {/* Summary Text */}
            {truncatedSummary ? (
              <p className="text-zinc-600 text-sm leading-relaxed mb-2 max-w-[78ch]">
                {truncatedSummary}
              </p>
            ) : !meeting.summary ? (
              <p className="text-zinc-400 text-sm italic mb-2 max-w-[78ch]">
                Record processing in progress. Full agenda highlights available
                soon.
              </p>
            ) : null}

            {/* Motion Tally */}
            {totalMotions > 0 && (
              <div className="text-xs font-bold text-zinc-500">
                {stats!.motion_carried_count > 0 && (
                  <span className="text-green-700">
                    {stats!.motion_carried_count} carried
                  </span>
                )}
                {stats!.motion_carried_count > 0 && stats!.motion_defeated_count > 0 && (
                  <span className="text-zinc-400">, </span>
                )}
                {stats!.motion_defeated_count > 0 && (
                  <span className="text-red-700">
                    {stats!.motion_defeated_count} defeated
                  </span>
                )}
              </div>
            )}
          </div>
        </ContentWrapper>

        {/* Assets & Actions */}
        <div className="px-5 pb-5 lg:p-6 flex flex-row lg:flex-col items-center justify-between lg:justify-center gap-4 lg:border-l border-zinc-50 lg:w-36 lg:shrink-0">
          <ProvenanceBadges meeting={meeting} compact />

          <div className="flex items-center gap-4">
            {meeting.video_duration_seconds && (
              <div className="hidden sm:flex items-center gap-1.5 text-zinc-400 text-xs font-bold">
                <Clock className="h-3.5 w-3.5" />
                {Math.round(meeting.video_duration_seconds / 60)}m
              </div>
            )}
            {hasContent ? (
              <Link
                to={`/meetings/${meeting.id}`}
                aria-label={`Open ${meeting.title}`}
                className="h-10 w-10 rounded-full bg-zinc-50 flex items-center justify-center group-hover:bg-brand-600 group-hover:text-white transition-all shadow-inner"
              >
                <ChevronRight className="h-6 w-6" />
              </Link>
            ) : (
              <div className="h-10 w-10 rounded-full bg-zinc-50 flex items-center justify-center text-zinc-300 shadow-inner">
                <ChevronRight className="h-6 w-6" />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
