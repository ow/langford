import { cn } from "../../lib/utils";

/**
 * Summaries are stored as Markdown bullets ("- …") by the pipeline. Return
 * the bullet texts as-is; anything else is a single paragraph.
 */
export function summaryPoints(summary: string): string[] {
  const lines = summary
    .split(/\n+/)
    .map((l) => l.trim())
    .filter(Boolean);
  if (lines.length > 0 && lines.every((l) => /^[-*•]\s+/.test(l))) {
    return lines.map((l) => l.replace(/^[-*•]\s+/, ""));
  }
  return [summary.trim()].filter(Boolean);
}

interface MeetingSummaryProps {
  summary: string;
  /** Show at most this many points (home cards, previews). */
  limit?: number;
  className?: string;
}

/** Meeting summary as a short, scannable bullet list. */
export function MeetingSummary({ summary, limit, className }: MeetingSummaryProps) {
  const points = summaryPoints(summary);
  const shown = limit ? points.slice(0, limit) : points;
  if (shown.length === 0) return null;

  if (shown.length === 1) {
    return <p className={cn("leading-relaxed text-zinc-700", className)}>{shown[0]}</p>;
  }

  return (
    <ul className={cn("space-y-2 text-zinc-700", className)}>
      {shown.map((point, i) => (
        <li key={i} className="flex gap-3 leading-relaxed">
          <span className="mt-[0.6em] h-1.5 w-1.5 shrink-0 rounded-full bg-brand-500" aria-hidden="true" />
          <span>{point}</span>
        </li>
      ))}
    </ul>
  );
}
