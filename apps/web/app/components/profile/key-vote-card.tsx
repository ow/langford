import { Link } from "react-router";
import { Badge } from "../ui/badge";
import { formatDate } from "../../lib/utils";
import { displayTitle, lastName } from "../../lib/display-text";
import type { KeyVote } from "../../lib/types";

// ── Detection type labels ──

const DETECTION_LABELS: Record<string, string> = {
  minority: "Minority vote",
  close_vote: "Close vote",
  ally_break: "Broke with usual allies",
};

// ── Component ──

interface KeyVoteCardProps {
  keyVote: KeyVote;
  personName?: string;
}

/** One key vote. Designed to sit as a row inside a `divide-y` card. */
export function KeyVoteCard({ keyVote }: KeyVoteCardProps) {
  const vote = keyVote.vote.toLowerCase();
  const variant = vote === "yes" ? "success" : vote === "no" ? "danger" : "muted";
  const title = keyVote.agenda_item_title
    ? displayTitle(keyVote.agenda_item_title)
    : keyVote.motion_text?.slice(0, 120) || "Motion";

  const meta = [
    ...keyVote.detection_type.map((type) => DETECTION_LABELS[type] || type),
    keyVote.vote_split ? `Split ${keyVote.vote_split}` : null,
  ].filter(Boolean) as string[];

  return (
    <article className="space-y-2 p-4 sm:p-5">
      <div className="flex items-start justify-between gap-3">
        <h4 className="flex-1 text-sm font-semibold leading-snug text-zinc-900">{title}</h4>
        <Badge variant={variant}>Voted {vote}</Badge>
      </div>

      {keyVote.context_summary && (
        <p className="text-sm leading-relaxed text-zinc-600">{keyVote.context_summary}</p>
      )}

      {keyVote.motion_text && keyVote.agenda_item_title && (
        <p className="line-clamp-2 border-l-2 border-zinc-200 pl-3 text-sm leading-relaxed text-zinc-500">
          &ldquo;{keyVote.motion_text.slice(0, 200)}{keyVote.motion_text.length > 200 ? "…" : ""}&rdquo;
        </p>
      )}

      {keyVote.ally_breaks && keyVote.ally_breaks.length > 0 && (
        <p className="text-sm text-zinc-600">
          Voted differently from {keyVote.ally_breaks.map((a) => lastName(a.person_name)).join(", ")}
        </p>
      )}

      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-zinc-500">
        {keyVote.meeting_id && keyVote.meeting_date && (
          <Link to={`/meetings/${keyVote.meeting_id}`} className="font-medium text-brand-700 hover:underline">
            {formatDate(keyVote.meeting_date)}
          </Link>
        )}
        {meta.map((m, i) => (
          <span key={i} className="inline-flex items-center gap-2">
            {(i > 0 || (keyVote.meeting_id && keyVote.meeting_date)) && <span aria-hidden="true" className="text-zinc-300">·</span>}
            <span className="tabular-nums">{m}</span>
          </span>
        ))}
      </p>
    </article>
  );
}
