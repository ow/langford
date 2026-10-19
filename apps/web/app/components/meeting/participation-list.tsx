import { cn } from "../../lib/utils";

export type ParticipationSpeaker = { who: string; position: string; point: string; topic: string };
export type Participation = { overview?: string; speakers?: ParticipationSpeaker[] };

const POSITION_LABEL: Record<string, string> = {
  supports: "Supports",
  opposes: "Opposes",
  concerned: "Concerned",
  asks: "Asks",
  mixed: "Mixed",
};

const POSITION_TONE: Record<string, string> = {
  supports: "text-emerald-700",
  opposes: "text-red-700",
  concerned: "text-amber-700",
};

const STOP = new Set(["the", "and", "for", "with", "from", "bylaw", "city", "langford", "plan", "road", "avenue"]);
const words = (t: string) =>
  new Set(t.toLowerCase().split(/[^a-z0-9]+/).filter((w) => w.length >= 4 && !STOP.has(w)));

/** Speakers relevant to a matter, by overlap between their topic and the matter's title/summary. */
export function speakersAbout(p: Participation | undefined, about: string): ParticipationSpeaker[] {
  const target = words(about);
  return (p?.speakers || []).filter((s) => [...words(`${s.topic} ${s.point}`)].some((w) => target.has(w)));
}

/** Public comment, one line per speaker (from the meeting transcript). */
export function ParticipationList({
  participation,
  speakers,
  className,
}: {
  participation?: Participation;
  speakers?: ParticipationSpeaker[];
  className?: string;
}) {
  const list = speakers ?? participation?.speakers ?? [];
  if (!list.length) return null;
  return (
    <ul className={cn("space-y-2", className)}>
      {list.map((s, i) => (
        <li key={i} className="text-sm leading-relaxed text-zinc-700">
          <span className="font-medium text-zinc-900">{s.who}</span>
          {POSITION_LABEL[s.position] && (
            <span className={cn("ml-1.5 text-xs font-medium", POSITION_TONE[s.position] || "text-zinc-500")}>
              {POSITION_LABEL[s.position]}
            </span>
          )}
          <span className="text-zinc-400"> · {s.topic}</span>
          <br />
          {s.point}
        </li>
      ))}
    </ul>
  );
}
