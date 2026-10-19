import type { ReactNode } from "react";
import { Link } from "react-router";
import { displayTitle } from "../../lib/display-text";
import { formatDate, cn } from "../../lib/utils";
import { ParticipationList } from "../meeting/participation-list";

/** Plain-language meaning of a bylaw stage, for residents who don't know what "second reading" means. */
const STAGES: { test: RegExp; label: string }[] = [
  { test: /rescind/i, label: "An earlier step was redone to correct the bylaw." },
  { test: /\badopt(ed|ion)?\b|final adoption/i, label: "Final approval. The bylaw is now in force." },
  { test: /second (and|&) third reading|second, third|2nd (and|&) 3rd/i, label: "Council approved the content and final wording. Adoption is the last step." },
  { test: /third reading|3rd reading/i, label: "Council approved the final wording. Adoption is the last step." },
  { test: /public hearing/i, label: "Residents could speak or write to council about the proposal." },
  { test: /second reading|2nd reading/i, label: "Council approved the bylaw's content in principle." },
  { test: /first reading|1st reading/i, label: "Introduced to council. A bylaw needs several readings before it becomes law." },
];

export function stageExplanation(...texts: (string | null | undefined)[]): string | null {
  const text = texts.filter(Boolean).join(" ");
  return STAGES.find((s) => s.test.test(text))?.label ?? null;
}

type Vote = { id: number; vote: string; person?: { name?: string | null } | null };
type Motion = {
  id: number;
  text_content?: string | null;
  plain_english_summary?: string | null;
  result?: string | null;
  mover?: string | null;
  seconder?: string | null;
  votes?: Vote[] | null;
};

function tally(motion: Motion) {
  const votes = motion.votes || [];
  const yes = votes.filter((v) => v.vote === "Yes").length;
  const no = votes.filter((v) => v.vote === "No");
  return { yes, no: no.length, against: no.map((v) => v.person?.name).filter(Boolean) as string[], counted: votes.length > 0 };
}

function outcome(motion: Motion) {
  const passed = /carried|passed|approved|adopted/i.test(motion.result || "");
  const failed = /defeated|failed|lost/i.test(motion.result || "");
  const t = tally(motion);
  const label = passed ? "Passed" : failed ? "Defeated" : motion.result ? displayTitle(motion.result) : null;
  return {
    label,
    tone: passed ? "text-emerald-700" : failed ? "text-red-700" : "text-zinc-600",
    count: t.counted ? `${t.yes}–${t.no}` : null,
    against: t.against,
    unanimous: t.counted ? t.no === 0 : true,
  };
}

export function isProceduralStep(item: any, extra: { hasParticipation: boolean; hasImage: boolean; headline?: string }) {
  const motions: Motion[] = item.motions || [];
  return (
    Boolean(stageExplanation(extra.headline, item.title, ...motions.map((m) => m.text_content))) &&
    !item.debate_summary &&
    !extra.hasParticipation &&
    !extra.hasImage &&
    motions.every((m) => outcome(m).unanimous)
  );
}

function Details({ children }: { children: ReactNode }) {
  return (
    <details className="group mt-2 text-sm">
      <summary className="cursor-pointer list-none text-xs font-medium text-zinc-500 hover:text-zinc-700 [&::-webkit-details-marker]:hidden">
        <span className="group-open:hidden">Details</span>
        <span className="hidden group-open:inline">Hide details</span>
      </summary>
      <div className="mt-3 space-y-3 border-l-2 border-zinc-100 pl-3">{children}</div>
    </details>
  );
}

function MotionDetail({ motion }: { motion: Motion }) {
  const o = outcome(motion);
  const votes = motion.votes || [];
  return (
    <div className="space-y-1.5">
      <p className="text-zinc-700">{motion.text_content}</p>
      {(motion.mover || motion.seconder) && (
        <p className="text-xs text-zinc-500">
          {motion.mover && <>Moved by {displayTitle(motion.mover)}</>}
          {motion.mover && motion.seconder && ", "}
          {motion.seconder && <>seconded by {displayTitle(motion.seconder)}</>}
        </p>
      )}
      {votes.length > 0 && (
        <p className="text-xs text-zinc-500">
          <span className={o.tone}>{o.label}</span>
          {o.count && ` ${o.count}`} ·{" "}
          {votes
            .map((v) => `${v.person?.name || "Unknown"}${v.vote === "Yes" ? "" : v.vote === "No" ? " (against)" : ` (${v.vote.toLowerCase()})`}`)
            .join(", ")}
        </p>
      )}
    </div>
  );
}

function DocLinks({ docs, meetingId }: { docs: any[]; meetingId: number }) {
  if (!docs.length) return null;
  return (
    <ul className="space-y-1">
      {docs.map((doc) => (
        <li key={doc.id}>
          <Link to={`/meetings/${meetingId}/documents/${doc.id}`} className="text-sm text-brand-700 hover:underline">
            {displayTitle(doc.title)}
          </Link>
        </li>
      ))}
    </ul>
  );
}

export function TimelineStep({
  item,
  headline,
  docs,
  layoutImage,
  participation,
}: {
  item: any;
  headline?: string;
  docs: any[];
  layoutImage?: { url: string; width?: number; height?: number } | null;
  participation?: any;
}) {
  const motions: Motion[] = item.motions || [];
  const hasParticipation = Boolean(participation?.speakers?.length);
  const procedural = isProceduralStep(item, { hasParticipation, hasImage: Boolean(layoutImage), headline });
  const stage = stageExplanation(headline, item.title, ...motions.map((m) => m.text_content));
  const title = headline || displayTitle(item.title);
  const meetingLine = (
    <p className="text-xs text-zinc-500">
      <Link to={`/meetings/${item.meeting_id}`} className="tabular-nums hover:text-brand-700">
        {formatDate(item.meetings?.meeting_date)}
      </Link>
      {item.meetings?.organizations?.name && <> · {item.meetings.organizations.name}</>}
    </p>
  );
  const decisions = motions.map((m) => ({ m, o: outcome(m) }));
  const details = (
    <Details>
      <p className="text-xs text-zinc-500">Agenda item: {displayTitle(item.title)}</p>
      {motions.map((m) => (
        <MotionDetail key={m.id} motion={m} />
      ))}
      {procedural && <DocLinks docs={docs} meetingId={item.meeting_id} />}
    </Details>
  );

  if (procedural) {
    return (
      <div className="py-1">
        {meetingLine}
        <div className="mt-0.5 flex flex-wrap items-baseline justify-between gap-x-3">
          <h3 className="font-semibold leading-snug text-zinc-900">{title}</h3>
          {decisions[0]?.o.label && (
            <span className={cn("shrink-0 text-xs font-medium tabular-nums", decisions[0].o.tone)}>
              {decisions[0].o.label}
              {decisions[0].o.count && ` ${decisions[0].o.count}`}
            </span>
          )}
        </div>
        {stage && <p className="mt-0.5 text-sm text-zinc-600">{stage}</p>}
        {details}
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm sm:p-6">
      {meetingLine}
      <h3 className="mt-1 text-lg font-semibold leading-snug text-zinc-900">{title}</h3>
      {item.plain_english_summary && <p className="mt-1.5 text-sm leading-relaxed text-zinc-600">{item.plain_english_summary}</p>}
      {stage && !item.plain_english_summary && <p className="mt-1.5 text-sm text-zinc-600">{stage}</p>}

      {layoutImage && (
        <figure className="mt-4">
          <a href={layoutImage.url} target="_blank" rel="noreferrer" className="block overflow-hidden rounded-xl border border-zinc-200 bg-white">
            <img src={layoutImage.url} alt="Proposed layout" width={layoutImage.width} height={layoutImage.height} className="max-h-[360px] w-full object-contain" loading="lazy" />
          </a>
          <figcaption className="mt-1.5 text-xs text-zinc-500">Proposed layout</figcaption>
        </figure>
      )}

      {item.debate_summary && (
        <div className="mt-4">
          <p className="text-xs font-semibold text-zinc-500">Discussion</p>
          <p className="mt-1 text-sm leading-relaxed text-zinc-700">{item.debate_summary}</p>
        </div>
      )}

      {hasParticipation && (
        <div className="mt-4">
          <p className="mb-2 text-xs font-semibold text-zinc-500">Who spoke</p>
          <ParticipationList participation={participation} />
        </div>
      )}

      {decisions.length > 0 && (
        <div className="mt-4 space-y-2 border-t border-zinc-100 pt-4">
          {decisions.map(({ m, o }) => (
            <div key={m.id} className="text-sm">
              <p className="text-zinc-800">
                <span className="font-medium">Decision:</span> {m.plain_english_summary || displayTitle(m.text_content || "")}
              </p>
              {o.label && (
                <p className="mt-0.5 text-xs">
                  <span className={cn("font-medium", o.tone)}>
                    {o.label}
                    {o.count && ` ${o.count}`}
                  </span>
                  {o.against.length > 0 && <span className="text-zinc-500"> · Against: {o.against.join(", ")}</span>}
                </p>
              )}
            </div>
          ))}
        </div>
      )}

      {docs.length > 0 && (
        <div className="mt-4">
          <p className="mb-1 text-xs font-semibold text-zinc-500">Documents</p>
          <DocLinks docs={docs} meetingId={item.meeting_id} />
        </div>
      )}
      {details}
    </div>
  );
}
