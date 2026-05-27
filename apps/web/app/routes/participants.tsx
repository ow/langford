import type { Route } from "./+types/participants";
import { Link, useRouteLoaderData } from "react-router";
import {
  Calendar,
  Clock,
  MessageSquare,
  Mic,
  Search,
  Users,
} from "lucide-react";
import { useMemo, useState } from "react";
import { getSupabaseAdminClient } from "../lib/supabase.server";
import { getMunicipality } from "../services/municipality";
import {
  getPublicParticipantStats,
  type PublicParticipantStats,
} from "../services/people";
import type { Municipality } from "../lib/types";
import { Badge } from "../components/ui/badge";
import { Input } from "../components/ui/input";
import { cn, formatDate } from "../lib/utils";
import { ogImageUrl, ogUrl } from "../lib/og";
import { getMunicipalityFromMatches } from "../lib/municipality-helpers";

export const meta: Route.MetaFunction = ({ matches }) => {
  const municipality = getMunicipalityFromMatches(matches);
  const shortName = municipality?.short_name || "View Royal";
  const title = `Public Participants | ViewRoyal.ai`;
  const description = `Identified public speakers and participation patterns in ${shortName} council meetings.`;

  return [
    { title },
    { name: "description", content: description },
    { property: "og:title", content: "Public Participants" },
    { property: "og:description", content: description },
    { property: "og:type", content: "website" },
    { property: "og:url", content: ogUrl("/participants") },
    { property: "og:image", content: ogImageUrl("Public Participants", { type: "person" }) },
    { property: "og:image:width", content: "1200" },
    { property: "og:image:height", content: "630" },
    { name: "twitter:card", content: "summary_large_image" },
  ];
};

export async function loader() {
  try {
    const supabase = getSupabaseAdminClient();
    const municipality = await getMunicipality(supabase);
    const participants = await getPublicParticipantStats(supabase, municipality.id);
    return { participants };
  } catch (error) {
    console.error("Error loading public participants:", error);
    return { participants: [] };
  }
}

function formatDuration(seconds: number) {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.round((seconds % 3600) / 60);
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m`;
  return `${Math.round(seconds)}s`;
}

function ParticipantCard({
  participant,
  rank,
  totalSeconds,
}: {
  participant: PublicParticipantStats;
  rank: number;
  totalSeconds: number;
}) {
  const percent =
    totalSeconds > 0 ? (participant.totalSeconds / totalSeconds) * 100 : 0;
  const topCategory = participant.topCategories[0]?.category;
  const topAppearances = participant.recentAppearances.slice(0, 2);

  return (
    <article className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm transition-all hover:-translate-y-0.5 hover:border-blue-200 hover:shadow-md">
      <div className="flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-zinc-900 text-xs font-black text-white shadow-sm">
          {rank}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <Link
                to={`/people/${participant.person.id}`}
                className="truncate text-base font-black tracking-tight text-zinc-900 hover:text-blue-700"
              >
                {participant.person.name}
              </Link>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-zinc-500">
                <span>{participant.meetingCount} meetings</span>
                <span>{participant.segmentCount} segments</span>
                {topCategory && (
                  <Badge variant="secondary" className="rounded-full px-2 py-0 text-[10px]">
                    {topCategory}
                  </Badge>
                )}
              </div>
            </div>

            <div className="shrink-0 text-right">
              <div className="text-xl font-black tabular-nums text-zinc-950">
                {percent.toFixed(percent >= 10 ? 0 : 1)}%
              </div>
              <div className="text-[10px] font-bold uppercase tracking-wider text-zinc-400">
                {formatDuration(participant.totalSeconds)}
              </div>
            </div>
          </div>

          <div className="mt-3 h-2 overflow-hidden rounded-full bg-zinc-100">
            <div
              className="h-full rounded-full bg-blue-600"
              style={{ width: `${Math.max(percent, 1)}%` }}
            />
          </div>

          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {topAppearances.map((appearance) => (
              <Link
                key={`${appearance.meetingId}-${appearance.agendaItemId || "none"}`}
                to={`/meetings/${appearance.meetingId}${appearance.firstStartTime ? `?t=${Math.floor(appearance.firstStartTime)}` : ""}`}
                className="group min-w-0 rounded-xl border border-zinc-100 bg-zinc-50 px-3 py-2 transition-colors hover:border-blue-200 hover:bg-blue-50"
              >
                <div className="truncate text-xs font-bold text-zinc-700 group-hover:text-blue-800">
                  {appearance.agendaTitle || appearance.meetingTitle}
                </div>
                <div className="mt-0.5 flex items-center gap-2 text-[11px] text-zinc-500">
                  <span>{formatDate(appearance.meetingDate)}</span>
                  <span>{formatDuration(appearance.seconds)}</span>
                </div>
              </Link>
            ))}
          </div>
        </div>
      </div>
    </article>
  );
}

function CompactParticipantRow({
  participant,
  rank,
  totalSeconds,
}: {
  participant: PublicParticipantStats;
  rank: number;
  totalSeconds: number;
}) {
  const percent =
    totalSeconds > 0 ? (participant.totalSeconds / totalSeconds) * 100 : 0;

  return (
    <Link
      to={`/people/${participant.person.id}`}
      className="group grid grid-cols-[2rem_minmax(0,1fr)_4rem_4rem] items-center gap-3 rounded-xl px-3 py-2 transition-colors hover:bg-zinc-50"
    >
      <div className="text-xs font-black tabular-nums text-zinc-400">
        {rank}
      </div>
      <div className="min-w-0">
        <div className="truncate text-sm font-bold text-zinc-800 group-hover:text-blue-700">
          {participant.person.name}
        </div>
        <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-zinc-100">
          <div
            className="h-full rounded-full bg-zinc-900 group-hover:bg-blue-600"
            style={{ width: `${Math.max(percent, 1)}%` }}
          />
        </div>
      </div>
      <div className="text-right text-sm font-black tabular-nums text-zinc-900">
        {percent.toFixed(percent >= 10 ? 0 : 1)}%
      </div>
      <div className="text-right text-xs font-bold tabular-nums text-zinc-500">
        {formatDuration(participant.totalSeconds)}
      </div>
    </Link>
  );
}

export default function Participants({ loaderData }: Route.ComponentProps) {
  const { participants } = loaderData;
  const rootData = useRouteLoaderData("root") as { municipality?: Municipality } | undefined;
  const shortName = rootData?.municipality?.short_name || "View Royal";
  const [query, setQuery] = useState("");

  const totals = useMemo(() => {
    const totalSeconds = participants.reduce(
      (sum, participant) => sum + participant.totalSeconds,
      0,
    );

    return {
      people: participants.length,
      totalSeconds,
      minutes: Math.round(totalSeconds / 60),
      appearances: participants.reduce(
        (sum, participant) => sum + participant.meetingCount,
        0,
      ),
    };
  }, [participants]);

  const filteredParticipants = useMemo(() => {
    const lower = query.trim().toLowerCase();
    if (!lower) return participants;
    return participants.filter((participant) => {
      return (
        participant.person.name.toLowerCase().includes(lower) ||
        participant.topCategories.some((category) =>
          category.category.toLowerCase().includes(lower),
        ) ||
        participant.recentAppearances.some((appearance) =>
          `${appearance.meetingTitle} ${appearance.agendaTitle || ""}`
            .toLowerCase()
            .includes(lower),
        )
      );
    });
  }, [participants, query]);

  return (
    <div className="min-h-screen bg-zinc-50">
      <div className="container mx-auto max-w-6xl px-4 py-10">
        <header className="mb-8">
          <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-blue-100 bg-blue-50 px-3 py-1 text-xs font-bold uppercase tracking-wider text-blue-700">
            <Mic className="h-3.5 w-3.5" />
            Identified speakers only
          </div>
          <div>
            <h1 className="text-4xl font-black tracking-tight text-zinc-950">
              Public Participants
            </h1>
            <p className="mt-2 max-w-2xl text-zinc-600">
              Best-effort view of identified non-council speakers in {shortName}
              meetings. Unidentified speaker labels are omitted.
            </p>
          </div>
        </header>

        <div className="mb-6 grid gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(18rem,1fr)] lg:items-start">
          <div className="rounded-2xl border border-zinc-200 bg-white p-3 shadow-sm">
            <div className="mb-2 flex items-center justify-between px-2">
              <div className="text-[10px] font-black uppercase tracking-widest text-zinc-400">
                Share of Identified Speaking
              </div>
              <div className="text-[10px] font-bold text-zinc-400">
                Top 5
              </div>
            </div>
            <div className="space-y-0.5">
              {participants.slice(0, 5).map((participant, index) => (
                <CompactParticipantRow
                  key={participant.person.id}
                  participant={participant}
                  rank={index + 1}
                  totalSeconds={totals.totalSeconds}
                />
              ))}
            </div>
          </div>

          <div className="space-y-3">
            <div className="grid grid-cols-3 gap-2 rounded-2xl border border-zinc-200 bg-white p-2 shadow-sm lg:grid-cols-1">
              <div className="px-4 py-2 text-center lg:flex lg:items-center lg:justify-between lg:text-left">
                <div className="flex items-center justify-center gap-2 lg:justify-start">
                  <Users className="h-4 w-4 text-blue-600" />
                  <div className="text-[10px] font-bold uppercase text-zinc-400">People</div>
                </div>
                <div className="text-xl font-black text-zinc-900">{totals.people}</div>
              </div>
              <div className="px-4 py-2 text-center lg:flex lg:items-center lg:justify-between lg:border-t lg:border-zinc-100 lg:text-left">
                <div className="flex items-center justify-center gap-2 lg:justify-start">
                  <Clock className="h-4 w-4 text-emerald-600" />
                  <div className="text-[10px] font-bold uppercase text-zinc-400">Minutes</div>
                </div>
                <div className="text-xl font-black text-zinc-900">{totals.minutes}</div>
              </div>
              <div className="px-4 py-2 text-center lg:flex lg:items-center lg:justify-between lg:border-t lg:border-zinc-100 lg:text-left">
                <div className="flex items-center justify-center gap-2 lg:justify-start">
                  <Calendar className="h-4 w-4 text-amber-600" />
                  <div className="text-[10px] font-bold uppercase text-zinc-400">Appearances</div>
                </div>
                <div className="text-xl font-black text-zinc-900">{totals.appearances}</div>
              </div>
            </div>

            <div className="rounded-2xl border border-zinc-200 bg-white p-3 shadow-sm">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400" />
                <Input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search participants..."
                  className="h-10 rounded-xl border-zinc-200 pl-10"
                />
              </div>
              <div className="mt-2 px-1 text-xs font-bold text-zinc-500">
                Showing {filteredParticipants.length} of {participants.length}
              </div>
            </div>
          </div>
        </div>

        {filteredParticipants.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-zinc-200 bg-white p-12 text-center">
            <MessageSquare className="mx-auto mb-3 h-10 w-10 text-zinc-300" />
            <p className="font-semibold text-zinc-600">No matching participants found.</p>
          </div>
        ) : (
          <div className="grid gap-3 lg:grid-cols-2">
            {filteredParticipants.map((participant, index) => (
              <ParticipantCard
                key={participant.person.id}
                participant={participant}
                rank={index + 1}
                totalSeconds={totals.totalSeconds}
              />
            ))}
          </div>
        )}

        <p className={cn("mt-6 text-sm leading-relaxed text-zinc-500")}>
          This page intentionally excludes unidentified diarization labels. Speaker identity
          is based on the current transcript/person links and may improve as aliases are reviewed.
        </p>
      </div>
    </div>
  );
}
