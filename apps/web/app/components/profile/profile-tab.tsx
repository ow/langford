import { formatDate } from "../../lib/utils";
import type { CouncillorHighlights } from "../../services/profiling";

interface ProfileTabProps {
  highlights: CouncillorHighlights | null;
  attendanceRate: number;
  /** Number of meetings the attendance rate is based on (0 = no data). */
  attendanceExpected?: number;
  totalVotes: number;
  totalMoved: number;
  totalSeconded: number;
  hoursSpoken: number | null;
  speakingRank: number | undefined;
  totalCouncillors: number;
  speakingCoverageLabel: string;
  topTopics: { name: string; percent: number }[];
  personName?: string;
  /** Show the council statistics grid (hidden for public participants). */
  showStats?: boolean;
  /** A public participation section is rendered above this tab. */
  hasParticipation?: boolean;
}

export function ProfileTab({
  highlights,
  attendanceRate,
  attendanceExpected,
  totalVotes,
  totalMoved,
  totalSeconded,
  hoursSpoken,
  speakingCoverageLabel,
  topTopics,
  personName,
  showStats: showStatsProp = true,
  hasParticipation = false,
}: ProfileTabProps) {
  const narrative = highlights?.narrative;
  const overview = highlights?.overview;
  const displayText = narrative || overview;
  const updatedAt = highlights?.narrative_generated_at || highlights?.generated_at;
  const hasAttendance = attendanceExpected === undefined || attendanceExpected > 0;
  const proposals = totalMoved + totalSeconded;
  const hasAnyStats =
    totalVotes > 0 || proposals > 0 || hoursSpoken !== null || (attendanceExpected ?? 0) > 0;
  const showStats = showStatsProp && hasAnyStats;
  const who = personName || "this person";
  const emptyDetail = showStats
    ? "The figures above come straight from minutes, attendance records and meeting transcripts — see the Votes, Speaking and Attendance tabs for detail."
    : showStatsProp
      ? "There are no council votes, attendance or recorded speech for them yet; these will appear once they take part in meetings."
      : hasParticipation
        ? "Their appearances at council meetings are listed above."
        : `${who} appears in meeting records but hasn't served on council, so there are no votes or attendance to summarize.`;

  return (
    <div className="space-y-6">
      {showStats && (
        <section className="overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm">
          <h3 className="sr-only">At a glance</h3>
          <dl className="grid grid-cols-2 divide-zinc-100 md:grid-cols-4 md:divide-x [&>div]:p-4 sm:[&>div]:p-5">
            <StatItem
              label="Recorded votes"
              value={totalVotes > 0 ? totalVotes.toLocaleString() : "—"}
              subtext={totalVotes > 0 ? undefined : "None documented"}
            />
            <StatItem
              label="Attendance"
              value={hasAttendance ? `${attendanceRate}%` : "—"}
              subtext={hasAttendance ? attendanceExpected ? `of ${attendanceExpected} meetings` : undefined : "No meetings on record"}
            />
            <StatItem
              label="Hours of speech"
              value={hoursSpoken !== null ? hoursSpoken.toFixed(1) : "—"}
              subtext={speakingCoverageLabel}
            />
            <StatItem
              label="Motions"
              value={proposals.toLocaleString()}
              subtext={`${totalMoved} moved · ${totalSeconded} seconded`}
            />
          </dl>

          {topTopics.length > 0 && (
            <div className="border-t border-zinc-100 px-4 py-4 sm:px-5">
              <h4 className="mb-2 text-sm text-zinc-500">Most discussed topics</h4>
              <div className="flex flex-wrap gap-2">
                {topTopics.map((topic) => (
                  <span
                    key={topic.name}
                    className="inline-flex items-center gap-1.5 rounded-full border border-zinc-200 bg-zinc-50 px-3 py-1 text-xs"
                  >
                    <span className="font-medium text-zinc-700">{topic.name}</span>
                    <span className="tabular-nums text-zinc-500">{topic.percent}%</span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </section>
      )}

      {displayText ? (
        <section className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm sm:p-6">
          <h3 className="text-base font-semibold text-zinc-900">Overview</h3>
          <div className="mt-3 space-y-4">
            {displayText.split("\n\n").map((paragraph, i) => (
              <p key={i} className="text-sm leading-relaxed text-zinc-700">
                {paragraph}
              </p>
            ))}
          </div>
          <p className="mt-4 border-t border-zinc-100 pt-3 text-xs text-zinc-500">
            AI-generated summary of recorded statements and votes
            {updatedAt ? ` · Updated ${formatDate(updatedAt)}` : ""}
          </p>
        </section>
      ) : (
        <div className="rounded-2xl border border-dashed border-zinc-300 bg-white/60 p-5 text-sm text-zinc-500">
          <p className="font-medium text-zinc-700">No written overview yet</p>
          <p className="mt-1 leading-relaxed">
            {personName ? `An overview of ${personName}'s` : "An overview of this person's"} record
            hasn't been generated. {emptyDetail}
          </p>
        </div>
      )}
    </div>
  );
}

// ── Stat Item ──

function StatItem({
  label,
  value,
  subtext,
}: {
  label: string;
  value: string;
  subtext?: string;
}) {
  return (
    <div className="min-w-0 space-y-1">
      <dt className="text-sm text-zinc-500">{label}</dt>
      <dd className="text-2xl font-bold tabular-nums tracking-tight text-zinc-900">{value}</dd>
      {subtext && <dd className="text-xs leading-snug text-zinc-500">{subtext}</dd>}
    </div>
  );
}
