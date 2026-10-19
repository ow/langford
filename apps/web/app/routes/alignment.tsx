import { civicToday, councilTermStatus, membershipIsActiveOn, membershipOverlapsRange } from "../lib/council-terms";
import { getCouncilTerms } from "../services/council-terms";
import type { Route } from "./+types/alignment";
import { getVotingAlignment } from "../services/analytics";
import { getSupabaseAdminClient } from "../lib/supabase.server";
import { getMunicipality } from "../services/municipality";
import {
  TrendingUp,
  Users,
  Info,
  ArrowRight,
  ShieldCheck,
  Scale,
  Calendar,
  Grid3X3,
} from "lucide-react";
import { cn } from "../lib/utils";
import { useMemo, useState } from "react";
import { Card, CardContent } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import { ogImageUrl, ogUrl } from "../lib/og";

export const meta: Route.MetaFunction = () => {
  return [
    { title: "Voting Alignment | ViewRoyal.ai" },
    { name: "description", content: "See how View Royal council members vote together — alignment matrix and trends" },
    { property: "og:title", content: "Voting Alignment | ViewRoyal.ai" },
    { property: "og:description", content: "See how View Royal council members vote together — alignment matrix and trends" },
    { property: "og:type", content: "website" },
    { property: "og:url", content: ogUrl("/alignment") },
    { property: "og:image", content: ogImageUrl("Voting Alignment", { type: "person" }) },
    { property: "og:image:width", content: "1200" },
    { property: "og:image:height", content: "630" },
    { name: "twitter:card", content: "summary_large_image" },
  ];
};

export async function loader() {
  try {
    const supabase = getSupabaseAdminClient();
    const municipality = await getMunicipality(supabase);
    const [data, councilTerms] = await Promise.all([
      getVotingAlignment(supabase, municipality.id),
      getCouncilTerms(supabase, municipality.id),
    ]);
    return { ...data, councilTerms };
  } catch (error) {
    console.error("Error loading alignment data:", error);
    throw new Response("Error loading alignment", { status: 500 });
  }
}

// Helper to parse dates without timezone shifts
const parseDate = (dateStr: string | null | undefined) => {
  if (!dateStr) return null;
  const [y, m, d] = dateStr.split(/[- : T]/).map(Number);
  return new Date(y, m - 1, d || 1);
};

export default function VotingAlignment({ loaderData }: Route.ComponentProps) {
  const { people, votes, motions, memberships, councilTerms } = loaderData;

  const today = civicToday();
  const terms = useMemo(() => councilTerms
    .filter((term) => councilTermStatus(term, today) !== "upcoming")
    .map((term) => {
      const termMemberships = memberships.filter((m: any) => membershipOverlapsRange(m, term.start_date, term.end_date));
      const members = new Map<number, any>();
      termMemberships.forEach((m: any) => {
        if (m.people) members.set(m.people.id, m.people);
      });
      return { ...term, start: parseDate(term.start_date)!, end: parseDate(term.end_date || today)!, members: [...members.values()] };
    }), [councilTerms, memberships, today]);
  const defaultTerm = terms.find((term) => councilTermStatus(term, today) === "current") || terms[0];
  const [selectedTermId, setSelectedId] = useState<number | null>(defaultTerm?.id || null);
  const selectedTerm = terms.find((term) => term.id === selectedTermId) || defaultTerm;
  const servedOn = (personId: number, date: Date) => {
    const day = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
    return memberships.some((m: any) => (m.person_id || m.people?.id) === personId && membershipIsActiveOn(m, day));
  };

  const { alignmentMatrix, consensusRate, dataQuality } = useMemo(() => {
    if (!selectedTerm) {
      return {
        alignmentMatrix: {} as Record<string, { total: number; matches: number }>,
        consensusRate: null,
        dataQuality: {
          hasExplicitDissent: false,
          contestedOutcomeCount: 0,
          recordedVoteCount: 0,
        },
      };
    }

    // Group votes by motion and store date
    const votesByMotion: Record<
      number,
      { date: Date; votes: Record<number, string> }
    > = {};
    votes.forEach((v: any) => {
      const d = parseDate(v.motions?.meetings?.meeting_date);
      if (d && d >= selectedTerm.start && d <= selectedTerm.end) {
        if (!votesByMotion[v.motion_id]) {
          votesByMotion[v.motion_id] = { date: d, votes: {} };
        }
        votesByMotion[v.motion_id].votes[v.person_id] = v.vote;
      }
    });

    const termMotions = (motions || []).filter((motion: any) => {
      const d = parseDate(motion.meetings?.meeting_date);
      return d && d >= selectedTerm.start && d <= selectedTerm.end;
    });
    const termVotes = votes.filter((vote: any) => {
      const date = parseDate(vote.motions?.meetings?.meeting_date);
      return date && date >= selectedTerm.start && date <= selectedTerm.end;
    });
    const explicitDissentVotes = termVotes.filter((vote: any) => ["No", "Opposed", "Abstain"].includes(vote.vote));
    const contestedOutcomeCount = termMotions.filter((motion: any) => {
      const result = String(motion.result || "").toUpperCase();
      return (
        result.includes("DEFEATED") ||
        result.includes("FAILED") ||
        result.includes("LOST")
      );
    }).length;
    const hasExplicitDissent = explicitDissentVotes.length > 0;

    const matrix: Record<string, { total: number; matches: number }> = {};
    const members = selectedTerm.members;

    members.forEach((p1: any) => {
      members.forEach((p2: any) => {
        if (p1.id === p2.id) return;
        const key = `${p1.id}-${p2.id}`;
        matrix[key] = { total: 0, matches: 0 };

        Object.values(votesByMotion).forEach((motionData) => {
          // Check if both members were active on this specific motion date
          const isActive1 = servedOn(p1.id, motionData.date);
          const isActive2 = servedOn(p2.id, motionData.date);

          if (
            isActive1 &&
            isActive2 &&
            motionData.votes[p1.id] &&
            motionData.votes[p2.id]
          ) {
            matrix[key].total++;
            if (motionData.votes[p1.id] === motionData.votes[p2.id]) {
              matrix[key].matches++;
            }
          }
        });
      });
    });

    // Calculate term consensus
    const motionVoteGroups = Object.values(votesByMotion);
    let unanimousCount = 0;
    let motionsWithQuorum = 0;

    motionVoteGroups.forEach((motionData) => {
      // Find members who were active on this date
      const activeMembersAtTime = members.filter(
        (m: any) =>
          servedOn(m.id, motionData.date),
      );

      const castVotes = activeMembersAtTime
        .map((m: any) => motionData.votes[m.id])
        .filter((v) => v !== undefined);

      if (castVotes.length > 1) {
        motionsWithQuorum++;
        const firstVote = castVotes[0];
        if (castVotes.every((v) => v === firstVote)) {
          unanimousCount++;
        }
      }
    });

    return {
      alignmentMatrix: matrix,
      consensusRate:
        motionsWithQuorum > 0 ? (unanimousCount / motionsWithQuorum) * 100 : null,
      dataQuality: {
        hasExplicitDissent,
        contestedOutcomeCount,
        recordedVoteCount: termVotes.length,
      },
    };
  }, [selectedTerm, votes, motions, memberships]);

  const hasIncompleteDissentAttribution =
    dataQuality.contestedOutcomeCount > 0 && !dataQuality.hasExplicitDissent;

  return (
    <div className="min-h-screen bg-zinc-50">
      <div className="container mx-auto py-12 px-4 max-w-6xl">
        <header className="mb-12">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-indigo-600 rounded-lg shadow-lg">
                <Scale className="h-6 w-6 text-white" />
              </div>
              <div>
                <h1 className="text-4xl font-extrabold tracking-tight text-zinc-900">
                  Council Alignment
                </h1>
                <p className="text-zinc-500 mt-1">
                  Measuring consensus and voting blocs across council terms.
                </p>
              </div>
            </div>

            <div className="flex bg-white p-1 rounded-xl border border-zinc-200 shadow-sm">
              {terms.map((term) => (
                <button
                  key={term.id}
                  onClick={() => setSelectedId(term.id)}
                  className={cn(
                    "px-4 py-2 rounded-lg text-sm font-bold transition-all",
                    selectedTermId === term.id
                      ? "bg-indigo-600 text-white shadow-md"
                      : "text-zinc-500 hover:text-zinc-900",
                  )}
                >
                  {term.name}
                </button>
              ))}
            </div>
          </div>
        </header>

        <p className="mb-6 text-sm text-muted-foreground">Terms use recorded service dates. Incoming councils appear here once their term begins. {terms.length === 0 && "No verified council term dates are available yet."}</p>
        {selectedTerm && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
            {/* Term Summary */}
            <div className="lg:col-span-4 space-y-6">
              <Card className="border-none shadow-sm ring-1 ring-zinc-200 bg-white overflow-hidden">
                <div className="p-6 bg-indigo-50/50 border-b border-zinc-100">
                  <div className="text-[10px] font-black text-indigo-400 uppercase tracking-[0.2em] mb-1">
                    Council Snapshot
                  </div>
                  <h2 className="text-2xl font-black text-indigo-900">
                    {selectedTerm.name} Term
                  </h2>
                </div>
                <CardContent className="p-6 space-y-8">
                  <div>
                    <div className="flex justify-between items-end mb-2">
                      <span className="text-sm font-bold text-zinc-500">
                        Consensus Rate
                      </span>
                      <span className="text-2xl font-black text-zinc-900">
                        {consensusRate === null
                          ? "N/A"
                          : `${consensusRate.toFixed(0)}%`}
                      </span>
                    </div>
                    <div className="w-full bg-zinc-100 rounded-full h-2 overflow-hidden">
                      <div
                        className="bg-indigo-600 h-full rounded-full transition-all duration-1000"
                        style={{
                          width:
                            consensusRate === null
                              ? "0%"
                              : `${consensusRate}%`,
                        }}
                      />
                    </div>
                    <p className="text-[10px] text-zinc-400 mt-2 italic">
                      Based only on explicit per-councillor vote records.
                    </p>
                    {hasIncompleteDissentAttribution && (
                      <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs leading-relaxed text-amber-900">
                        This term has {dataQuality.contestedOutcomeCount} defeated
                        motion{dataQuality.contestedOutcomeCount === 1 ? "" : "s"},
                        but no explicit No/Opposed votes have been extracted yet.
                        Agreement percentages below only reflect recorded individual votes.
                      </div>
                    )}
                  </div>

                  <div className="space-y-3">
                    <h3 className="text-xs font-black text-zinc-400 uppercase tracking-widest">
                      Council Members
                    </h3>
                    <div className="grid gap-2">
                      {selectedTerm.members.map((m: any) => (
                        <div
                          key={m.id}
                          className="flex items-center gap-3 p-2 rounded-xl bg-zinc-50 border border-zinc-100"
                        >
                          <div className="h-8 w-8 rounded-full bg-zinc-200 overflow-hidden border border-white shrink-0">
                            {m.image_url ? (
                              <img
                                src={m.image_url}
                                alt={m.name}
                                className="h-full w-full object-cover"
                              />
                            ) : (
                              <Users className="h-4 w-4 m-2 text-zinc-400" />
                            )}
                          </div>
                          <span className="text-sm font-bold text-zinc-700">
                            {m.name}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </CardContent>
              </Card>

              <Card className="bg-indigo-900 border-none shadow-xl">
                <CardContent className="p-8 flex items-start gap-6 text-white">
                  <div className="space-y-2">
                    <h4 className="font-bold flex items-center gap-2">
                      <Info className="h-4 w-4 text-indigo-300" />
                      Term Analysis
                    </h4>
                    <p className="text-indigo-200 text-xs leading-relaxed">
                      By looking at the whole term, we can identify "core"
                      members who frequently represent the council majority and
                      "independent" members who often cast dissenting votes.
                    </p>
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Alignment Matrix / Grid */}
            <div className="lg:col-span-8 space-y-6">
              <h2 className="text-sm font-black uppercase tracking-widest text-zinc-400 px-2 flex items-center gap-2">
                <Grid3X3 className="h-4 w-4" />
                Alignment Matrix
              </h2>

              <div className="grid gap-4">
                {selectedTerm.members.map((p1: any) => (
                  <div
                    key={p1.id}
                    className="bg-white rounded-2xl border border-zinc-200 shadow-sm overflow-hidden"
                  >
                    <div className="p-4 bg-zinc-50 border-b border-zinc-100 flex items-center gap-3">
                      <div className="h-8 w-8 rounded-full bg-zinc-200 border border-white overflow-hidden shrink-0">
                        {p1.image_url ? (
                          <img
                            src={p1.image_url}
                            alt={p1.name}
                            className="h-full w-full object-cover"
                          />
                        ) : (
                          <Users className="h-4 w-4 m-2 text-zinc-400" />
                        )}
                      </div>
                      <span className="font-bold text-zinc-900">{p1.name}</span>
                    </div>
                    <div className="p-4 flex flex-wrap gap-3">
                      {selectedTerm.members
                        .filter((p2: any) => p2.id !== p1.id)
                        .map((p2: any) => {
                          const data = alignmentMatrix[`${p1.id}-${p2.id}`];
                          const rate =
                            data && data.total > 0
                              ? (data.matches / data.total) * 100
                              : null;

                          return (
                            <div
                              key={p2.id}
                              className={cn(
                                "flex-1 min-w-[140px] p-3 rounded-xl border flex flex-col items-center justify-center gap-1 transition-all",
                                !rate
                                  ? "bg-zinc-50 border-zinc-100 opacity-50"
                                  : rate > 90
                                    ? "bg-green-50 border-green-100"
                                    : rate > 75
                                      ? "bg-brand-50 border-brand-100"
                                      : "bg-amber-50 border-amber-100",
                              )}
                            >
                              <div className="text-[9px] font-black text-zinc-400 uppercase tracking-tighter truncate w-full text-center">
                                with {p2.name.split(" ").pop()}
                              </div>
                              <div
                                className={cn(
                                  "text-xl font-black tabular-nums",
                                  !rate
                                    ? "text-zinc-300"
                                    : rate > 90
                                      ? "text-green-600"
                                      : rate > 75
                                        ? "text-brand-600"
                                        : "text-amber-600",
                                )}
                              >
                                {rate ? `${rate.toFixed(0)}%` : "N/A"}
                              </div>
                            </div>
                          );
                        })}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
