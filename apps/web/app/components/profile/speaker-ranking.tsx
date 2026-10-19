import { useState } from "react";
import { personPath } from "../../lib/people-paths";
import { Link } from "react-router";
import { User } from "lucide-react";
import { cn } from "../../lib/utils";
import { lastName } from "../../lib/display-text";

// ── Types ──

interface SpeakerRankingProps {
  rankings: {
    person_id: number;
    person_name: string;
    image_url?: string | null;
    total_seconds: number;
  }[];
  currentPersonId: number;
}

const INITIAL_COUNT = 10;

// ── Helpers ──

function formatHours(seconds: number): string {
  return (seconds / 3600).toFixed(1);
}

// ── Main Component ──

export function SpeakerRanking({ rankings, currentPersonId }: SpeakerRankingProps) {
  const [showAll, setShowAll] = useState(false);
  // Filter out speakers with 0 speaking time, sort descending
  const filtered = rankings
    .filter((r) => r.total_seconds > 0)
    .sort((a, b) => b.total_seconds - a.total_seconds);

  if (filtered.length === 0) {
    return (
      <p className="text-sm text-zinc-500">No speaking time data available for ranking.</p>
    );
  }

  const maxSeconds = filtered[0].total_seconds;
  const currentIndex = filtered.findIndex((r) => r.person_id === currentPersonId);
  const visible = showAll
    ? filtered.map((r, i) => ({ r, i }))
    : filtered
        .map((r, i) => ({ r, i }))
        .filter(({ i }) => i < INITIAL_COUNT || i === currentIndex);

  return (
    <div>
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h3 className="text-base font-semibold text-zinc-900">Speaker ranking</h3>
        <span className="text-xs text-zinc-500 tabular-nums">{filtered.length} identified speakers</span>
      </div>

      <ol className="space-y-0.5">
        {visible.map(({ r, i }, idx) => {
          const isCurrent = r.person_id === currentPersonId;
          const pct = maxSeconds > 0 ? (r.total_seconds / maxSeconds) * 100 : 0;
          const gap = idx > 0 && i - visible[idx - 1].i > 1;

          return (
            <li key={r.person_id} className={cn(gap && "mt-2 border-t border-dashed border-zinc-200 pt-2")}>
              <Link
                to={personPath({ id: r.person_id, name: r.person_name })}
                className={cn(
                  "group flex items-center gap-2.5 rounded-lg px-1.5 py-1",
                  isCurrent ? "bg-brand-50" : "hover:bg-zinc-50",
                )}
                aria-current={isCurrent ? "true" : undefined}
              >
                <span className="w-6 shrink-0 text-right text-xs tabular-nums text-zinc-400">{i + 1}</span>
                <span className="h-6 w-6 shrink-0 overflow-hidden rounded-full border border-zinc-200 bg-zinc-100">
                  {r.image_url ? (
                    <img src={r.image_url} alt="" className="h-full w-full object-cover" />
                  ) : (
                    <User className="m-1 h-3.5 w-3.5 text-zinc-300" aria-hidden="true" />
                  )}
                </span>
                <span
                  className={cn(
                    "w-24 shrink-0 truncate text-sm sm:w-28",
                    isCurrent ? "font-semibold text-brand-800" : "text-zinc-700 group-hover:text-zinc-900",
                  )}
                  title={r.person_name}
                >
                  {lastName(r.person_name)}
                </span>
                <span className="h-2 flex-1 overflow-hidden rounded-full bg-zinc-100">
                  <span
                    className={cn("block h-full rounded-full", isCurrent ? "bg-brand-600" : "bg-zinc-300")}
                    style={{ width: `${pct}%` }}
                  />
                </span>
                <span
                  className={cn(
                    "w-12 shrink-0 text-right text-sm tabular-nums",
                    isCurrent ? "font-semibold text-brand-800" : "text-zinc-500",
                  )}
                >
                  {formatHours(r.total_seconds)}h
                </span>
              </Link>
            </li>
          );
        })}
      </ol>

      {filtered.length > INITIAL_COUNT && (
        <button
          type="button"
          onClick={() => setShowAll(!showAll)}
          className="mt-3 text-sm font-semibold text-brand-700 hover:text-brand-800"
        >
          {showAll ? "Show top 10 only" : `Show all ${filtered.length} speakers`}
        </button>
      )}
    </div>
  );
}
