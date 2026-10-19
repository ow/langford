import { Sparkles, VoteIcon, Mic, Calendar, TrendingUp } from "lucide-react";
import { Card, CardContent } from "../ui/card";
import { cn, formatDate } from "../../lib/utils";
import type { CouncillorHighlights } from "../../services/profiling";

interface ProfileTabProps {
  highlights: CouncillorHighlights | null;
  attendanceRate: number;
  totalVotes: number;
  totalMoved: number;
  totalSeconded: number;
  hoursSpoken: number | null;
  speakingRank: number | undefined;
  totalCouncillors: number;
  speakingCoverageLabel: string;
  topTopics: { name: string; percent: number }[];
}

export function ProfileTab({
  highlights,
  attendanceRate,
  totalVotes,
  totalMoved,
  totalSeconded,
  hoursSpoken,
  speakingRank,
  totalCouncillors,
  speakingCoverageLabel,
  topTopics,
}: ProfileTabProps) {
  const narrative = highlights?.narrative;
  const overview = highlights?.overview;
  const displayText = narrative || overview;

  return (
    <div className="space-y-6">
      {/* AI Narrative */}
      {displayText && (
        <div className="space-y-3">
          <div className="bg-white rounded-xl border border-zinc-200 p-6 shadow-sm space-y-4">
            {displayText.split("\n\n").map((paragraph, i) => (
              <p key={i} className="text-sm text-zinc-700 leading-relaxed">
                {paragraph}
              </p>
            ))}
          </div>

          {/* Disclaimer */}
          <div className="flex items-center gap-1.5 text-[10px] text-zinc-400 font-medium">
            <Sparkles className="h-3 w-3 text-amber-400" />
            <span>
              AI-generated profile
              {highlights?.narrative_generated_at
                ? ` - Updated ${formatDate(highlights.narrative_generated_at)}`
                : highlights?.generated_at
                  ? ` - Updated ${formatDate(highlights.generated_at)}`
                  : ""}
            </span>
          </div>
        </div>
      )}

      {/* At-a-glance stats card */}
      <Card className="border-zinc-200 shadow-sm bg-white py-0">
        <CardContent className="p-0">
          <h3 className="sr-only">At a glance</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 divide-zinc-100 md:divide-x [&>*]:p-5">
            <StatItem
              icon={VoteIcon}
              label="Recorded votes"
              value={totalVotes > 0 ? totalVotes.toLocaleString() : "—"}
              subtext={totalVotes > 0 ? undefined : "Not available"}
            />
            <StatItem
              icon={Calendar}
              label="Attendance"
              value={`${attendanceRate}%`}
            />
            <StatItem
              icon={Mic}
              label="Hours of speech"
              value={hoursSpoken !== null ? hoursSpoken.toFixed(1) : "--"}
              subtext={speakingCoverageLabel}
            />
            <StatItem
              icon={TrendingUp}
              label="Proposals"
              value={(totalMoved + totalSeconded).toLocaleString()}
              subtext={`${totalMoved} moved, ${totalSeconded} seconded`}
            />
          </div>

          {/* Top topics */}
          {topTopics.length > 0 && (
            <div className="mt-6 pt-4 border-t border-zinc-100">
              <h4 className="text-[10px] font-black uppercase tracking-[0.2em] text-zinc-400 mb-3">
                Top Topics by Engagement
              </h4>
              <div className="flex flex-wrap gap-2">
                {topTopics.map((topic) => (
                  <div
                    key={topic.name}
                    className="flex items-center gap-1.5 bg-zinc-50 border border-zinc-200 rounded-full px-3 py-1"
                  >
                    <span className="text-xs font-bold text-zinc-700">{topic.name}</span>
                    <span className="text-[10px] font-bold text-zinc-400">{topic.percent}%</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// ── Stat Item ──

function StatItem({
  icon: Icon,
  label,
  value,
  subtext,
}: {
  icon: typeof VoteIcon;
  label: string;
  value: string;
  subtext?: string;
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-1.5 text-sm font-medium text-zinc-500">
        <Icon className="h-4 w-4 text-brand-600" />
        {label}
      </div>
      <div className="text-2xl font-bold tabular-nums tracking-tight text-zinc-900">{value}</div>
      {subtext && (
        <div className="text-xs text-zinc-500">{subtext}</div>
      )}
    </div>
  );
}
