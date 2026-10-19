import { Link } from "react-router";
import { meetingPath } from "../../lib/paths";
import { Badge } from "../ui/badge";
import { formatDate } from "../../lib/utils";
import type { CouncillorHighlight } from "../../services/profiling";

const POSITION_STYLES = {
  for: { variant: "success", label: "Supports" },
  against: { variant: "danger", label: "Opposes" },
  nuanced: { variant: "warning", label: "Nuanced" },
} as const;

/** One notable position. Designed to sit as a row inside a `divide-y` card. */
export function HighlightCard({ highlight }: { highlight: CouncillorHighlight }) {
  const style = POSITION_STYLES[highlight.position] || POSITION_STYLES.nuanced;

  return (
    <div className="space-y-2 p-4 sm:p-5">
      <div className="flex items-start justify-between gap-3">
        <h4 className="text-sm font-semibold leading-snug text-zinc-900">{highlight.title}</h4>
        <Badge variant={style.variant}>{style.label}</Badge>
      </div>
      <p className="text-sm leading-relaxed text-zinc-600">{highlight.summary}</p>
      {highlight.evidence && highlight.evidence.length > 0 && (
        <ul className="space-y-2 pt-1">
          {highlight.evidence.map((e, i) => (
            <li key={i} className="border-l-2 border-zinc-200 pl-3 text-sm">
              <p className="leading-relaxed text-zinc-600">&ldquo;{e.text}&rdquo;</p>
              <p className="mt-0.5 text-xs text-zinc-500">
                {e.meeting_id ? (
                  <Link to={meetingPath({ id: e.meeting_id, slug: e.meeting_slug })} className="font-medium text-brand-700 hover:underline">
                    {formatDate(e.meeting_date || e.date || "")}
                  </Link>
                ) : (
                  formatDate(e.meeting_date || e.date || "")
                )}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
