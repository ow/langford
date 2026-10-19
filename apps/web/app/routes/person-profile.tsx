import { personPath } from "../lib/people-paths";
import { NativeSelect } from "../components/ui/native-select";
import { resolvePersonParam } from "../lib/people.server";
import { useMemo, useState, useEffect } from "react";
import type { Route } from "./+types/person-profile";
import { civicToday, membershipIsActiveOn, councilTermStatus } from "../lib/council-terms";
import { councilServicePeriods, councilServiceRange } from "../lib/council-service";
import { getCouncilTerms } from "../services/council-terms";
import { getPersonProfile } from "../services/people";
import { getSupabaseAdminClient } from "../lib/supabase.server";
import { getMunicipality } from "../services/municipality";
import { getMunicipalityFromMatches } from "../lib/municipality-helpers";
import type { Person, Municipality, Membership, Attendance, Vote } from "../lib/types";
import { Link, useRouteLoaderData, useSearchParams } from "react-router";
import { SubscribeButton } from "../components/subscribe-button";
import {
  getSpeakingTimeStats,
  getSpeakingTimeByMeeting,
  getSpeakingTimeByTopic,
  getCouncillorStances,
  getCouncillorHighlights,
  getKeyVotes,
} from "../services/profiling";
import { SpeakingTimeCard } from "../components/profile/speaking-time-card";
import { SpeakerRanking } from "../components/profile/speaker-ranking";
import { ProfileTab } from "../components/profile/profile-tab";
import { PublicParticipation } from "../components/profile/public-participation";
import { getPublicParticipationHistory } from "../services/public-participation.server";
import { PolicyTab } from "../components/profile/policy-tab";
import { KeyVotesTab } from "../components/profile/key-votes-tab";
import {
  ChevronLeft,
  ChevronRight,
  User,
  Briefcase,
  History,
  Vote as VoteIcon,
  Gavel,
  ArrowRight,
  ThumbsUp,
  ThumbsDown,
  Minus,
  Scale,
  Users,
  Target,
  Sparkles,
  Mic,
} from "lucide-react";
import { Badge } from "../components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "../components/ui/card";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "../components/ui/tabs";
import { cn, formatDate } from "../lib/utils";
import { AskQuestion } from "../components/ask-question";
import { ogImageUrl, ogUrl } from "../lib/og";

export const meta: Route.MetaFunction = ({ data, matches }) => {
  if (!data?.person) return [{ title: "Person | ViewRoyal.ai" }];
  const p = data.person as Person;
  const municipality = getMunicipalityFromMatches(matches);
  const municipalityName = municipality?.name || "Town of View Royal";
  const activeMembership = (p as any).memberships?.find(
    (m: Membership) => membershipIsActiveOn(m, civicToday()),
  );
  const upcomingMembership = p.memberships?.find((m) => m.start_date && m.start_date > civicToday());
  const role = activeMembership?.role || (upcomingMembership ? `${upcomingMembership.role}-elect` : p.is_councillor ? "Former Council Member" : "Public participant");
  const title = `${p.name} — ${role} | ViewRoyal.ai`;
  const description = p.bio || `${role} for the ${municipalityName}.`;
  const image = p.image_url || ogImageUrl(p.name, { subtitle: role, type: "person" });
  return [
    { title },
    { name: "description", content: description },
    { property: "og:title", content: `${p.name} — ${role}` },
    { property: "og:description", content: description },
    { property: "og:type", content: "profile" },
    { property: "og:url", content: ogUrl(personPath(p)) },
    { property: "og:image", content: image },
    { property: "og:image:width", content: "1200" },
    { property: "og:image:height", content: "630" },
    { name: "twitter:card", content: "summary_large_image" },
  ];
};

export async function loader({ params, request }: Route.LoaderArgs) {
  const { id } = params;
  const url = new URL(request.url);
  const page = parseInt(url.searchParams.get("page") || "0", 10);
  const timeRange = url.searchParams.get("timeRange") || "all";

  // Compute date range for speaking time queries
  const now = new Date();
  let startDate: string | undefined;
  let endDate: string | undefined;
  if (timeRange === "12m") {
    const d = new Date(now);
    d.setFullYear(d.getFullYear() - 1);
    startDate = d.toISOString().slice(0, 10);
    endDate = now.toISOString().slice(0, 10);
  } else if (timeRange === "term") {
    endDate = civicToday();
  }
  // "all" -> startDate/endDate remain undefined

  try {
    const supabase = getSupabaseAdminClient();
    const municipality = await getMunicipality(supabase);
    const terms = await getCouncilTerms(supabase, municipality.id);
    const selectedTermId = url.searchParams.get("term");
    const selectedTerm = selectedTermId ? terms.find((term) => String(term.id) === selectedTermId) : null;
    if (selectedTermId && !selectedTerm) throw new Response("Unknown council term", { status: 400 });
    const selectedPeriod = selectedTerm ? { start: selectedTerm.start_date, end: selectedTerm.end_date && selectedTerm.end_date < civicToday() ? selectedTerm.end_date : civicToday() } : undefined;
    const currentTerm = terms.find((term) => councilTermStatus(term, civicToday()) === "current");
    // Without verified term dates, show no term statistics rather than silently using all history.
    const termUnavailable = timeRange === "term" && !currentTerm && !selectedTerm;
    if (timeRange === "term") startDate = currentTerm?.start_date || "9999-12-31";
    if (selectedPeriod) { startDate = selectedPeriod.start; endDate = selectedPeriod.end; }
    const resolved = await resolvePersonParam(supabase, id, request);
    const personId = resolved.id;

    // Profile data is critical; profiling data is optional (graceful degradation)
    const [data, speakingTimeRanking, speakingTimeTrend, speakingTimeByTopic, stances, highlights, keyVotes] =
      await Promise.all([
        getPersonProfile(supabase, String(personId), page, municipality.id, selectedPeriod),
        getSpeakingTimeStats(supabase, startDate, endDate, municipality.id).catch((e) => { console.error("Speaking time stats failed:", e); return [] as Awaited<ReturnType<typeof getSpeakingTimeStats>>; }),
        getSpeakingTimeByMeeting(supabase, personId, startDate, endDate, municipality.id).catch((e) => { console.error("Speaking time by meeting failed:", e); return [] as Awaited<ReturnType<typeof getSpeakingTimeByMeeting>>; }),
        getSpeakingTimeByTopic(supabase, personId, startDate, endDate, municipality.id).catch((e) => { console.error("Speaking time by topic failed:", e); return [] as Awaited<ReturnType<typeof getSpeakingTimeByTopic>>; }),
        getCouncillorStances(supabase, personId).catch((e) => { console.error("Councillor stances failed:", e); return [] as Awaited<ReturnType<typeof getCouncillorStances>>; }),
        getCouncillorHighlights(supabase, personId).catch((e) => { console.error("Councillor highlights failed:", e); return null as Awaited<ReturnType<typeof getCouncillorHighlights>>; }),
        getKeyVotes(supabase, personId).catch((e) => { console.error("Key votes failed:", e); return [] as Awaited<ReturnType<typeof getKeyVotes>>; }),
      ]);

    // Find current person's speaking time from the ranking
    const currentPersonSpeaking = speakingTimeRanking.find(
      (r) => r.person_id === personId,
    );
    const rank = currentPersonSpeaking
      ? speakingTimeRanking
          .filter((r) => r.total_seconds > 0)
          .sort((a, b) => b.total_seconds - a.total_seconds)
          .findIndex((r) => r.person_id === personId) + 1
      : undefined;
    const totalCouncillorsWithData = speakingTimeRanking.filter(
      (r) => r.total_seconds > 0,
    ).length;

    return {
      ...data,
      publicParticipation: getPublicParticipationHistory(personId, municipality.slug),
      page,
      speakingTimeRanking,
      speakingTimeTrend,
      speakingTimeByTopic,
      stances,
      highlights,
      keyVotes,
      timeRange,
      termUnavailable,
      terms,
      selectedTerm,
      currentPersonSpeaking,
      speakingRank: rank,
      totalCouncillorsWithData,
    };
  } catch (error: any) {
    if (error instanceof Response) throw error;
    if (error.message === "Person Not Found") {
      throw new Response("Person Not Found", { status: 404 });
    }
    console.error("Error loading person profile:", error);
    throw new Response("Error loading person profile", { status: 500 });
  }
}

// ── Main Component ──

export default function PersonProfile({ loaderData }: Route.ComponentProps) {
  const {
    person,
    attendance,
    attendanceAll,
    attendanceTotal,
    allMeetings,
    candidacies,
    segments,
    stats,
    alignmentResults,
    page,
    speakingTimeRanking,
    speakingTimeTrend,
    speakingTimeByTopic,
    stances,
    highlights,
    keyVotes,
    currentPersonSpeaking,
    speakingRank,
    totalCouncillorsWithData,
    termUnavailable,
    terms,
    selectedTerm,
    timeRange,
    publicParticipation,
  } = loaderData;

  const [profileParams, setProfileParams] = useSearchParams();
  const rootData = useRouteLoaderData("root") as { municipality?: Municipality } | undefined;
  const shortName = rootData?.municipality?.short_name || "View Royal";
  const [selectedAlignId, setSelectedAlignId] = useState<number | null>(null);

  useEffect(() => {
    if (alignmentResults && alignmentResults.length > 0 && !selectedAlignId) {
      setSelectedAlignId(alignmentResults[0].personId);
    }
  }, [alignmentResults]);

  const selectedAlignment = useMemo(() => {
    return alignmentResults?.find((r: any) => r.personId === selectedAlignId);
  }, [alignmentResults, selectedAlignId]);

  const topTopics = useMemo(() => {
    const counts: Record<string, number> = {};
    let total = 0;
    segments.forEach((seg) => {
      const cat = seg.agenda_items?.category;
      if (cat && cat !== "Other") {
        counts[cat] = (counts[cat] || 0) + 1;
        total++;
      }
    });
    if (total === 0) return [];
    return Object.entries(counts)
      .sort(([, a], [, b]) => b - a)
      .slice(0, 5)
      .map(([name, count]) => ({
        name,
        percent: Math.round((count / total) * 100),
      }));
  }, [segments]);

  const today = civicToday();
  const activeMemberships = person.memberships?.filter((m) => membershipIsActiveOn(m, today)) || [];
  const upcomingMemberships = person.memberships?.filter((m) => m.start_date && m.start_date > today) || [];
  const serviceMemberships = [...(person.memberships || [])].sort(
    (a, b) => (b.start_date || "").localeCompare(a.start_date || ""),
  );
  const councilService = councilServicePeriods(person, today);
  const otherService = serviceMemberships.filter((m) => m.organization?.classification !== "Council");
  const upcomingRole = (role: string) => /mayor|councillor|councilor/i.test(role) ? `${role}-elect` : `Incoming ${role}`;

  const { attendanceStats } = useMemo(() => {
    const now = civicToday();
    const expectedMeetings = allMeetings.filter((meeting) => {
      if (meeting.meeting_date > now) return false;
      return person.memberships?.some((m) => {
        if (m.organization_id !== meeting.organization_id) return false;
        if (m.start_date && meeting.meeting_date < m.start_date) return false;
        if (m.end_date && meeting.meeting_date > m.end_date) return false;
        return true;
      });
    });
    const totalExpected = expectedMeetings.length;
    if (totalExpected === 0) return { attendanceStats: { rate: 0, total: 0 } };
    const attendedRecords = attendanceAll.filter((record) => {
      return (
        expectedMeetings.some((m) => m.id === record.meeting_id) &&
        record.attendance_mode !== "Absent" &&
        record.attendance_mode !== "Regrets"
      );
    });
    return {
      attendanceStats: {
        rate: Math.round((attendedRecords.length / totalExpected) * 100),
        total: totalExpected,
      },
    };
  }, [attendanceAll, allMeetings, person.memberships]);

  const relevantAttendance = attendance;

  const hasSpeakingData = currentPersonSpeaking && currentPersonSpeaking.total_seconds > 0;
  const speakingPeriodLabel = selectedTerm?.name || (timeRange === "12m" ? "Last 12 months" : timeRange === "term" ? "Current term" : "All recorded dates");
  const speakingCoverageLabel = hasSpeakingData ? `${currentPersonSpeaking.meeting_count} meetings · ${speakingPeriodLabel}` : "No attributed speech available";

  return (
    <div className="min-h-screen bg-zinc-50">
      <div className="container mx-auto max-w-6xl px-4 pt-8 pb-16">
        {/* Profile header */}
        <header className="mb-8 rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm sm:p-6">
          <div className="flex flex-col gap-5 sm:flex-row sm:items-center">
            <div className="h-24 w-24 shrink-0 overflow-hidden rounded-2xl bg-zinc-100 ring-1 ring-zinc-200 sm:h-28 sm:w-28">
              {person.image_url ? (
                <img src={person.image_url} alt={person.name} className="h-full w-full object-cover" />
              ) : (
                <div className="flex h-full w-full items-center justify-center">
                  <User className="h-10 w-10 text-zinc-300" />
                </div>
              )}
            </div>
            <div className="min-w-0 flex-1">
              <p className="mb-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-zinc-500">
                <Link to="/people" className="-ml-1 inline-flex items-center font-medium text-zinc-600 hover:text-brand-700">
                  <ChevronLeft className="h-4 w-4" aria-hidden="true" />
                  Council
                </Link>
                {activeMemberships.map((m) => (
                  <span key={m.id} className="inline-flex items-center gap-2">
                    <span aria-hidden="true" className="text-zinc-300">·</span>
                    <span>
                      <span className="font-medium text-brand-700">{m.role}</span>
                      {m.start_date && (
                        <>
                          {" since "}
                          {m.organization?.classification === "Council"
                            ? councilService.find((period) => period.organizationId === m.organization_id && period.role === m.role && period.status === "current")?.startYear || m.start_date.slice(0, 4)
                            : m.start_date.slice(0, 4)}
                        </>
                      )}
                    </span>
                  </span>
                ))}
                {activeMemberships.length === 0 && (
                  <span className="inline-flex items-center gap-2">
                    <span aria-hidden="true" className="text-zinc-300">·</span>
                    {upcomingMemberships.length > 0 ? upcomingRole(upcomingMemberships[0].role) : `Former ${shortName} council member`}
                  </span>
                )}
              </p>
              <h1 className="text-3xl font-extrabold tracking-tight text-zinc-900 md:text-4xl">
                {person.name}
              </h1>
            </div>
            {(person.is_councillor || person.email) && (
              <div className="flex shrink-0 flex-wrap items-center gap-2">
                {person.email && (
                  <a
                    href={`mailto:${person.email}`}
                    className="inline-flex items-center gap-1.5 rounded-full border border-zinc-200 bg-white px-3 py-1.5 text-sm font-semibold text-zinc-700 transition-colors hover:border-brand-300 hover:text-brand-700"
                  >
                    Email
                  </a>
                )}
                {person.is_councillor && (
                <Link
                  to={`/compare?a=${person.id}`}
                  className="inline-flex items-center gap-1.5 rounded-full border border-zinc-200 bg-white px-3 py-1.5 text-sm font-semibold text-zinc-700 transition-colors hover:border-brand-300 hover:text-brand-700"
                >
                  Compare
                </Link>
                )}
                {person.is_councillor && <SubscribeButton type="person" targetId={person.id} label="Follow" />}
              </div>
            )}
          </div>
          {person.bio && (
            <p className="mt-5 max-w-3xl border-t border-zinc-100 pt-4 text-sm leading-relaxed text-zinc-600">
              {person.bio}
            </p>
          )}
        </header>

        <div className="grid grid-cols-1 gap-8 lg:grid-cols-12">
          {/* Main Content with Tabs */}
          <div className="min-w-0 space-y-4 lg:col-span-8">
            <Tabs defaultValue="profile" className="space-y-6">
              <div className="sticky top-16 z-10 -mx-4 bg-zinc-50/90 px-4 backdrop-blur supports-[backdrop-filter]:bg-zinc-50/75">
                <TabsList className="flex h-auto w-full justify-start gap-0 overflow-x-auto rounded-none border-b border-zinc-200 bg-transparent p-0 [scrollbar-width:none]">
                  <TabsTrigger
                    value="profile"
                    className="relative h-11 flex-none rounded-none border-0 bg-transparent px-3 text-sm font-semibold text-zinc-500 shadow-none hover:text-zinc-800 data-[state=active]:bg-transparent data-[state=active]:text-zinc-900 data-[state=active]:shadow-none after:absolute after:inset-x-3 after:bottom-0 after:h-0.5 after:rounded-full data-[state=active]:after:bg-brand-600"
                  >
                    <Sparkles className="mr-1.5 h-4 w-4" />
                    Profile
                  </TabsTrigger>
                  <TabsTrigger
                    value="policy"
                    className="relative h-11 flex-none rounded-none border-0 bg-transparent px-3 text-sm font-semibold text-zinc-500 shadow-none hover:text-zinc-800 data-[state=active]:bg-transparent data-[state=active]:text-zinc-900 data-[state=active]:shadow-none after:absolute after:inset-x-3 after:bottom-0 after:h-0.5 after:rounded-full data-[state=active]:after:bg-brand-600"
                  >
                    <Target className="mr-1.5 h-4 w-4" />
                    Policy
                  </TabsTrigger>
                  <TabsTrigger
                    value="key-votes"
                    className="relative h-11 flex-none rounded-none border-0 bg-transparent px-3 text-sm font-semibold text-zinc-500 shadow-none hover:text-zinc-800 data-[state=active]:bg-transparent data-[state=active]:text-zinc-900 data-[state=active]:shadow-none after:absolute after:inset-x-3 after:bottom-0 after:h-0.5 after:rounded-full data-[state=active]:after:bg-brand-600"
                  >
                    <Scale className="mr-1.5 h-4 w-4" />
                    Key votes
                  </TabsTrigger>
                  <TabsTrigger
                    value="votes"
                    className="relative h-11 flex-none rounded-none border-0 bg-transparent px-3 text-sm font-semibold text-zinc-500 shadow-none hover:text-zinc-800 data-[state=active]:bg-transparent data-[state=active]:text-zinc-900 data-[state=active]:shadow-none after:absolute after:inset-x-3 after:bottom-0 after:h-0.5 after:rounded-full data-[state=active]:after:bg-brand-600"
                  >
                    <VoteIcon className="mr-1.5 h-4 w-4" />
                    Votes
                  </TabsTrigger>
                  {hasSpeakingData && (
                  <TabsTrigger
                    value="speaking"
                    className="relative h-11 flex-none rounded-none border-0 bg-transparent px-3 text-sm font-semibold text-zinc-500 shadow-none hover:text-zinc-800 data-[state=active]:bg-transparent data-[state=active]:text-zinc-900 data-[state=active]:shadow-none after:absolute after:inset-x-3 after:bottom-0 after:h-0.5 after:rounded-full data-[state=active]:after:bg-brand-600"
                  >
                    <Mic className="mr-1.5 h-4 w-4" />
                    Speaking
                  </TabsTrigger>
                  )}
                  <TabsTrigger
                    value="attendance"
                    className="relative h-11 flex-none rounded-none border-0 bg-transparent px-3 text-sm font-semibold text-zinc-500 shadow-none hover:text-zinc-800 data-[state=active]:bg-transparent data-[state=active]:text-zinc-900 data-[state=active]:shadow-none after:absolute after:inset-x-3 after:bottom-0 after:h-0.5 after:rounded-full data-[state=active]:after:bg-brand-600"
                  >
                    <History className="mr-1.5 h-4 w-4" />
                    Attendance
                  </TabsTrigger>
                </TabsList>
              </div>

              {/* Profile Tab */}
              <TabsContent value="profile" className="space-y-6">
                {publicParticipation && <PublicParticipation history={publicParticipation} />}
                <ProfileTab
                  highlights={highlights}
                  attendanceRate={attendanceStats.rate}
                  totalVotes={stats.totalVotes}
                  totalMoved={stats.totalMoved}
                  totalSeconded={stats.totalSeconded}
                  hoursSpoken={hasSpeakingData ? currentPersonSpeaking!.total_seconds / 3600 : null}
                  speakingRank={speakingRank}
                  totalCouncillors={totalCouncillorsWithData}
                  speakingCoverageLabel={speakingCoverageLabel}
                  topTopics={topTopics}
                />
              </TabsContent>

              {/* Policy Tab */}
              <TabsContent value="policy" className="space-y-6">
                <PolicyTab
                  stances={stances ?? []}
                  highlights={highlights?.highlights ?? []}
                />
              </TabsContent>

              {/* Key Votes Tab */}
              <TabsContent value="key-votes" className="space-y-6">
                <KeyVotesTab
                  keyVotes={keyVotes ?? []}
                  personName={person.name}
                />
              </TabsContent>

              {/* Votes Tab */}
              <TabsContent value="votes" className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {/* Voting Record Card */}
                  <Link to={personPath(person, "/votes")} className="group">
                    <Card className="h-full border-none shadow-sm ring-1 ring-zinc-200 hover:ring-brand-500 transition-all">
                      <CardHeader className="pb-2">
                        <CardTitle className="text-xs font-black uppercase tracking-widest text-zinc-400 flex items-center gap-2">
                          <VoteIcon className="h-4 w-4 text-brand-600" />
                          Voting Record
                        </CardTitle>
                      </CardHeader>
                      <CardContent>
                        <div className="flex items-center justify-between mb-4">
                          <div className="text-3xl font-black text-zinc-900">
                            {stats.totalVotes > 0 ? stats.totalVotes.toLocaleString() : "Not available"}
                          </div>
                          <div className="p-2 bg-brand-50 rounded-full group-hover:bg-brand-600 transition-colors">
                            <ArrowRight className="h-5 w-5 text-brand-600 group-hover:text-white" />
                          </div>
                        </div>
                        <div className="space-y-2">
                          {stats.totalVotes > 0 && stats.votesBreakdown && (
                            <>
                              <div className="flex items-center gap-2 text-xs">
                                <ThumbsUp className="h-3 w-3 text-green-600" />
                                <div className="flex-1 h-2 bg-zinc-100 rounded-full overflow-hidden">
                                  <div className="h-full bg-green-500" style={{ width: `${(stats.votesBreakdown.yes / stats.totalVotes) * 100}%` }} />
                                </div>
                                <span className="font-bold text-zinc-700 w-8 text-right">{stats.votesBreakdown.yes}</span>
                              </div>
                              <div className="flex items-center gap-2 text-xs">
                                <ThumbsDown className="h-3 w-3 text-red-600" />
                                <div className="flex-1 h-2 bg-zinc-100 rounded-full overflow-hidden">
                                  <div className="h-full bg-red-500" style={{ width: `${(stats.votesBreakdown.no / stats.totalVotes) * 100}%` }} />
                                </div>
                                <span className="font-bold text-zinc-700 w-8 text-right">{stats.votesBreakdown.no}</span>
                              </div>
                              <div className="flex items-center gap-2 text-xs">
                                <Minus className="h-3 w-3 text-zinc-400" />
                                <div className="flex-1 h-2 bg-zinc-100 rounded-full overflow-hidden">
                                  <div className="h-full bg-zinc-400" style={{ width: `${(stats.votesBreakdown.abstain / stats.totalVotes) * 100}%` }} />
                                </div>
                                <span className="font-bold text-zinc-700 w-8 text-right">{stats.votesBreakdown.abstain}</span>
                              </div>
                            </>
                          )}
                        </div>
                      </CardContent>
                    </Card>
                  </Link>

                  {/* Legislative Proposals Card */}
                  <Link to={personPath(person, "/proposals")} className="group">
                    <Card className="h-full border-none shadow-sm ring-1 ring-zinc-200 hover:ring-indigo-500 transition-all">
                      <CardHeader className="pb-2">
                        <CardTitle className="text-xs font-black uppercase tracking-widest text-zinc-400 flex items-center gap-2">
                          <Gavel className="h-4 w-4 text-indigo-600" />
                          Legislative Proposals
                        </CardTitle>
                      </CardHeader>
                      <CardContent>
                        <div className="flex items-center justify-between mb-4">
                          <div className="text-3xl font-black text-zinc-900">
                            {(stats.totalMoved + stats.totalSeconded).toLocaleString()}
                          </div>
                          <div className="p-2 bg-indigo-50 rounded-full group-hover:bg-indigo-600 transition-colors">
                            <ArrowRight className="h-5 w-5 text-indigo-600 group-hover:text-white" />
                          </div>
                        </div>
                        <div className="grid grid-cols-2 gap-4">
                          <div className="bg-zinc-50 p-3 rounded-lg border border-zinc-100">
                            <div className="text-[10px] font-black uppercase text-zinc-400 mb-1">Moved</div>
                            <div className="text-xl font-bold text-zinc-900">{stats.totalMoved}</div>
                          </div>
                          <div className="bg-zinc-50 p-3 rounded-lg border border-zinc-100">
                            <div className="text-[10px] font-black uppercase text-zinc-400 mb-1">Seconded</div>
                            <div className="text-xl font-bold text-zinc-900">{stats.totalSeconded}</div>
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                  </Link>
                </div>

                {/* Voting Alignment */}
                <Card className="border-none shadow-md ring-1 ring-zinc-200/50 bg-white transition-all overflow-hidden">
                  <CardHeader className="pb-3 border-b border-zinc-100">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-xs font-black uppercase tracking-widest text-zinc-400 flex items-center gap-2">
                        <Scale className="h-3 w-3 text-indigo-600" />
                        Voting Alignment
                      </CardTitle>
                      <Link
                        to={personPath(person, "/alignment")}
                        className="text-[10px] font-bold text-indigo-600 hover:underline flex items-center gap-0.5"
                      >
                        Full Analysis <ChevronRight className="h-2 w-2" />
                      </Link>
                    </div>
                  </CardHeader>
                  <CardContent className="p-0">
                    {alignmentResults && alignmentResults.length > 0 ? (
                      <div className="overflow-x-auto">
                        <table className="w-full text-left">
                          <thead className="bg-zinc-50 border-b border-zinc-100">
                            <tr>
                              <th className="px-4 py-2 text-[9px] font-black text-zinc-400 uppercase tracking-widest">Member</th>
                              <th className="px-4 py-2 text-[9px] font-black text-zinc-400 uppercase tracking-widest text-center">Shared</th>
                              <th className="px-4 py-2 text-[9px] font-black text-zinc-400 uppercase tracking-widest text-right">Match</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-zinc-50">
                            {alignmentResults.map((result: any) => (
                              <tr key={result.personId} className="hover:bg-zinc-50 transition-colors">
                                <td className="px-4 py-3">
                                  <div className="flex items-center gap-2">
                                    <div className="h-6 w-6 rounded-full bg-zinc-100 border border-zinc-200 overflow-hidden shrink-0">
                                      {result.imageUrl ? (
                                        <img src={result.imageUrl} alt={result.personName} className="h-full w-full object-cover" />
                                      ) : (
                                        <User className="h-3 w-3 m-1.5 text-zinc-300" />
                                      )}
                                    </div>
                                    <span className="text-xs font-bold text-zinc-700 truncate max-w-[100px]">
                                      {result.personName.split(" ").pop()}
                                    </span>
                                  </div>
                                </td>
                                <td className="px-4 py-3 text-center text-[10px] font-bold text-zinc-500 tabular-nums">{result.totalMotions}</td>
                                <td className="px-4 py-3 text-right">
                                  <span className={cn(
                                    "text-xs font-black tabular-nums",
                                    result.alignmentRate > 90 ? "text-green-600" : result.alignmentRate > 75 ? "text-indigo-600" : "text-amber-600",
                                  )}>
                                    {result.alignmentRate.toFixed(0)}%
                                  </span>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ) : (
                      <div className="text-center py-8">
                        <Users className="h-8 w-8 text-zinc-200 mx-auto mb-2" />
                        <p className="text-xs text-zinc-400 italic font-medium px-6">
                          No shared voting records found for overlapping tenures.
                        </p>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </TabsContent>

              {/* Speaking Tab */}
              {hasSpeakingData && (
                <TabsContent value="speaking" className="space-y-6">
                  <SpeakingTimeCard
                    totalSeconds={currentPersonSpeaking!.total_seconds}
                    meetingCount={currentPersonSpeaking!.meeting_count}
                    segmentCount={currentPersonSpeaking!.segment_count}
                    trendData={speakingTimeTrend}
                    topicBreakdown={speakingTimeByTopic}
                    rank={speakingRank}
                    totalCouncillors={totalCouncillorsWithData}
                    fixedPeriodLabel={selectedTerm?.name}
                  />
                  {speakingTimeRanking && speakingTimeRanking.some((r: any) => r.total_seconds > 0) && (
                    <Card className="border-none shadow-md ring-1 ring-zinc-200/50 bg-white">
                      <CardContent className="pt-4">
                        <SpeakerRanking
                          rankings={speakingTimeRanking}
                          currentPersonId={person.id}
                        />
                      </CardContent>
                    </Card>
                  )}
                </TabsContent>
              )}

              {/* Attendance Tab */}
              <TabsContent value="attendance" className="space-y-4">
                <div className="bg-white rounded-2xl border border-zinc-200 shadow-xl overflow-hidden">
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm">
                      <thead className="bg-zinc-50 border-b border-zinc-200 sticky top-0 z-10">
                        <tr>
                          <th className="px-6 py-4 font-black uppercase text-[10px] tracking-widest text-zinc-400">Meeting Date</th>
                          <th className="px-6 py-4 font-black uppercase text-[10px] tracking-widest text-zinc-400">Title</th>
                          <th className="px-6 py-4 font-black uppercase text-[10px] tracking-widest text-zinc-400 w-32">Status</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-zinc-100">
                        {relevantAttendance.map((record) => (
                          <tr key={record.id} className="hover:bg-zinc-50 transition-colors group">
                            <td className="px-6 py-4 whitespace-nowrap text-zinc-500 font-medium">
                              {formatDate(record.meetings?.meeting_date)}
                            </td>
                            <td className="px-6 py-4">
                              <Link
                                to={`/meetings/${record.meeting_id}`}
                                className="font-bold text-zinc-900 group-hover:text-brand-600 transition-colors block"
                              >
                                {record.meetings?.title}
                              </Link>
                            </td>
                            <td className="px-6 py-4 text-right">
                              <Badge
                                variant="outline"
                                className={`text-[9px] font-black uppercase px-2 py-0.5 ${
                                  record.attendance_mode === "No Record"
                                    ? "border-amber-200 text-amber-700 bg-amber-50"
                                    : record.attendance_mode === "Absent" || record.attendance_mode === "Regrets"
                                      ? "border-red-200 text-red-700 bg-red-50"
                                      : "border-green-200 text-green-700 bg-green-50"
                                }`}
                              >
                                {record.attendance_mode}
                              </Badge>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {attendanceTotal > 20 && (
                    <div className="p-4 border-t border-zinc-200 flex justify-between items-center bg-zinc-50">
                      <div className="text-xs text-zinc-500 font-bold">
                        Showing {page * 20 + 1}-{Math.min((page + 1) * 20, attendanceTotal)} of {attendanceTotal}
                      </div>
                      <div className="flex gap-2">
                        <Link
                          to={`?${new URLSearchParams({ ...Object.fromEntries(profileParams), page: String(Math.max(0, page - 1)) })}`}
                          preventScrollReset={true}
                          className={cn(
                            "px-3 py-1.5 rounded-lg border border-zinc-300 text-xs font-bold bg-white hover:bg-zinc-100 transition-colors",
                            page === 0 && "pointer-events-none opacity-50",
                          )}
                        >
                          Previous
                        </Link>
                        <Link
                          to={`?${new URLSearchParams({ ...Object.fromEntries(profileParams), page: String(page + 1) })}`}
                          preventScrollReset={true}
                          className={cn(
                            "px-3 py-1.5 rounded-lg border border-zinc-300 text-xs font-bold bg-white hover:bg-zinc-100 transition-colors",
                            (page + 1) * 20 >= attendanceTotal && "pointer-events-none opacity-50",
                          )}
                        >
                          Next
                        </Link>
                      </div>
                    </div>
                  )}
                </div>

                {/* Roles + Electoral History (moved here from separate Roles tab) */}
                <div className="space-y-8 pt-4">
                  {candidacies.length > 0 && (
                    <section>
                      <h3 className="text-xs font-black uppercase tracking-[0.2em] text-zinc-400 mb-4 px-1">
                        Electoral History
                      </h3>
                      <div className="grid gap-4">
                        {candidacies.map((can: any) => (
                          <div
                            key={can.id}
                            className="bg-white p-8 rounded-2xl border border-zinc-200 shadow-sm hover:border-brand-400 transition-all"
                          >
                            <div className="flex justify-between items-start mb-6">
                              <div>
                                <h3 className="text-xl font-black text-zinc-900">
                                  {can.election_offices?.elections?.name}
                                </h3>
                                <div className="text-sm text-zinc-500 font-medium">
                                  Candidate for {can.election_offices?.office}
                                </div>
                              </div>
                              <Badge
                                className={cn(
                                  "font-black text-[10px] uppercase px-3",
                                  can.is_elected ? "bg-green-600 shadow-lg shadow-green-200" : "bg-zinc-400",
                                )}
                              >
                                {can.is_elected ? "Elected" : "Not Elected"}
                              </Badge>
                            </div>
                            <div className="flex gap-12">
                              <div>
                                <div className="text-[10px] font-black text-zinc-400 uppercase tracking-[0.2em] mb-1">Votes Received</div>
                                <div className="text-3xl font-black text-zinc-900 tabular-nums">
                                  {can.votes_received?.toLocaleString() || "N/A"}
                                </div>
                              </div>
                              {can.election_offices?.elections?.election_date && (
                                <div>
                                  <div className="text-[10px] font-black text-zinc-400 uppercase tracking-[0.2em] mb-1">Election Date</div>
                                  <div className="text-3xl font-black text-zinc-900">
                                    {new Date(can.election_offices.elections.election_date).getFullYear()}
                                  </div>
                                </div>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </section>
                  )}
                </div>
              </TabsContent>
            </Tabs>
          </div>

          {/* Sidebar */}
          <aside className="space-y-6 lg:col-span-4">
            <div className="rounded-2xl border border-zinc-200 bg-white p-4 shadow-sm">
              <label htmlFor="profile-term" className="mb-2 block text-sm font-semibold text-zinc-900">
                Statistics period
              </label>
              <NativeSelect
                id="profile-term"
                value={selectedTerm?.id || ""}
                onChange={(event) => setProfileParams((prev) => {
                  const next = new URLSearchParams(prev);
                  if (event.target.value) next.set("term", event.target.value); else next.delete("term");
                  next.delete("page");
                  next.delete("timeRange");
                  return next;
                }, { preventScrollReset: true })}
              >
                <option value="">All available records</option>
                {terms.map((term) => <option key={term.id} value={term.id}>{term.name}</option>)}
              </NativeSelect>
              {termUnavailable && <p className="mt-3 text-sm text-zinc-600">Current term dates have not been recorded. <Link to="?timeRange=all" className="underline">View all-time speaking statistics</Link>.</p>}
              <details className="group mt-3 text-sm text-zinc-500">
                <summary className="cursor-pointer list-none font-medium text-zinc-600 hover:text-zinc-900 [&::-webkit-details-marker]:hidden">
                  <span className="inline-flex items-center gap-1">
                    About these numbers
                    <ChevronRight className="h-3.5 w-3.5 transition-transform group-open:rotate-90" />
                  </span>
                </summary>
                <div className="mt-2 space-y-2 leading-relaxed">
                  <p>Votes, motions, attendance and alignment use the selected period. {selectedTerm ? "Speaking time uses the selected term." : "Speaking time has its own range selector."} AI highlights, policy summaries and key votes cover all recorded service.</p>
                  {stats.totalVotes === 0 && <p>Individual vote records are unavailable for this period. This does not mean no votes were cast.</p>}
                  {stats.totalVotes > 0 && <p>Only individually documented votes are counted. Minutes often name dissent without listing everyone else, so this is a partial voting history; incomplete roll calls are excluded from alignment.</p>}
                  <p>Recorded speech: {speakingCoverageLabel}. Totals exclude missing transcripts and unidentified speakers.</p>
                </div>
              </details>
            </div>

            {(councilService.length > 0 || otherService.length > 0) && (
              <Card className="shadow-sm">
                <CardHeader>
                  <CardTitle className="text-base">Service</CardTitle>
                  
                </CardHeader>
                <CardContent>
                  <ol className="flex flex-col gap-5">
                    {councilService.map((period) => (
                      <li key={`${period.organizationId}-${period.role}-${period.startYear}-${period.startDate || "history"}`} className="flex flex-wrap items-start justify-between gap-3 border-l-2 border-border pl-4">
                        <div>
                          <p className="font-semibold">{period.status === "upcoming" ? upcomingRole(period.role) : period.role}</p>
                          <p className="text-sm text-muted-foreground">{period.organizationName}</p>
                          <p className="text-sm text-muted-foreground">{councilServiceRange(period)}</p>
                          {period.status === "upcoming" && period.startDate && <p className="text-xs text-muted-foreground">Takes office {formatDate(period.startDate)}</p>}
                          {period.sourceUrl && <a href={period.sourceUrl} target="_blank" rel="noreferrer" className="text-xs text-muted-foreground underline underline-offset-2">Historical source</a>}
                        </div>
                        <Badge variant={period.status === "current" ? "default" : "outline"}>{period.status === "upcoming" ? "Upcoming" : period.status === "current" ? "Current" : "Past"}</Badge>
                      </li>
                    ))}
                    {otherService.map((m) => {
                      const upcoming = Boolean(m.start_date && m.start_date > today);
                      const active = membershipIsActiveOn(m, today);
                      return (
                        <li key={m.id} className="flex flex-wrap items-start justify-between gap-3 border-l-2 border-border pl-4">
                          <div>
                            <p className="font-semibold">{upcoming ? upcomingRole(m.role) : m.role}</p>
                            <p className="text-sm text-muted-foreground">{m.organization?.name}</p>
                            <p className="text-sm text-muted-foreground">
                              {m.start_date ? formatDate(m.start_date) : "Start date unrecorded"}
                              {" – "}{m.end_date ? formatDate(m.end_date) : upcoming ? "End date unrecorded" : "Present"}
                            </p>
                          </div>
                          <Badge variant={active ? "default" : "outline"}>{upcoming ? "Upcoming" : active ? "Current" : "Past"}</Badge>
                        </li>
                      );
                    })}
                  </ol>
                </CardContent>
              </Card>
            )}


            <AskQuestion
              personId={person.id}
              personName={person.name}
              className="shadow-sm"
            />
          </aside>
        </div>
      </div>
    </div>
  );
}
