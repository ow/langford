import type { Route } from "./+types/meetings";
import { getMeetings } from "../services/meetings";
import { getMunicipality } from "../services/municipality";
import { getSupabaseAdminClient } from "../lib/supabase.server";
import { getMunicipalityFromMatches } from "../lib/municipality-helpers";
import type { Meeting } from "../lib/types";
import { cn } from "../lib/utils";
import { ogImageUrl, ogUrl } from "../lib/og";

export const meta: Route.MetaFunction = ({ data, matches }) => {
  const municipality = getMunicipalityFromMatches(matches);
  const shortName = municipality?.short_name || "View Royal";
  const year = (data as any)?.selectedYear;
  const title = year
    ? `${year} Council Meetings | ViewRoyal.ai`
    : "Council Meetings | ViewRoyal.ai";
  const ogTitle = year ? `${year} Council Meetings` : "Council Meetings";
  const description = `Browse all ${shortName} council meetings, agendas, transcripts, and voting records.`;
  return [
    { title },
    { name: "description", content: description },
    { property: "og:title", content: title },
    { property: "og:description", content: description },
    { property: "og:type", content: "website" },
    { property: "og:url", content: ogUrl("/meetings") },
    { property: "og:image", content: ogImageUrl(ogTitle, { type: "meeting" }) },
    { property: "og:image:width", content: "1200" },
    { property: "og:image:height", content: "630" },
    { name: "twitter:card", content: "summary_large_image" },
  ];
};
import {
  useSearchParams,
  type ShouldRevalidateFunctionArgs,
} from "react-router";
import { useState, useEffect, useMemo } from "react";
import {
  Search,
  Calendar as CalendarIcon,
  LayoutList,
  X,
  ChevronLeft,
  ChevronRight,
  ArrowUpDown,
} from "lucide-react";
import {
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
} from "../components/ui/tabs";
import { MeetingCard } from "../components/meeting-card";
import { PageHeader } from "../components/ui/page-header";
import { CalendarView } from "../components/calendar-view";

export async function loader({ request }: Route.LoaderArgs) {
  const url = new URL(request.url);
  const currentYear = new Date().getFullYear();
  const selectedYear = parseInt(
    url.searchParams.get("year") || currentYear.toString(),
  );

  try {
    const supabase = getSupabaseAdminClient();
    const municipality = await getMunicipality(supabase);
    const { meetings, statsMap } = await getMeetings(
      supabase,
      municipality,
      {
        startDate: `${selectedYear}-01-01`,
        endDate: `${selectedYear}-12-31`,
      },
    );
    return { meetings, statsMap, selectedYear, currentYear };
  } catch (error) {
    console.error("Error loading meetings data:", error);
    return { meetings: [], statsMap: {}, selectedYear, currentYear };
  }
}

export function shouldRevalidate({
  currentUrl,
  nextUrl,
}: ShouldRevalidateFunctionArgs) {
  return (
    currentUrl.searchParams.get("year") !== nextUrl.searchParams.get("year")
  );
}

export default function Meetings({ loaderData }: Route.ComponentProps) {
  const { meetings, statsMap, selectedYear, currentYear } = loaderData;
  const [searchParams, setSearchParams] = useSearchParams();

  // View state (List vs Calendar)
  const view = searchParams.get("view") || "list";

  // Filter states
  const statusTab = searchParams.get("status") || "past";
  const qParam = searchParams.get("q") || "";
  const [searchQuery, setSearchQuery] = useState(qParam);
  const orgFilter = searchParams.get("org") || "";
  const typeFilter = searchParams.get("type") || "";
  const sortOrder = searchParams.get("sort") || "desc";

  const years = useMemo(() => {
    const startYear = 2008;
    const yearsArr = [];
    for (let y = currentYear; y >= startYear; y--) {
      yearsArr.push(y);
    }
    return yearsArr;
  }, [currentYear]);

  // Extract unique organizations and types from loaded meetings
  const meetingTypes = useMemo(() => {
    const types = new Set<string>();
    meetings.forEach((m) => {
      if (m.type) types.add(m.type);
    });
    return Array.from(types).sort();
  }, [meetings]);

  // Types already distinguish most bodies (e.g. "Regular Council"), so an
  // organization only gets its own chip when it has untyped meetings and
  // isn't already named by a type — avoids duplicate "Advisory Committee"
  // / "Council" + "Regular Council" chips.
  const organizations = useMemo(() => {
    const orgs = new Set<string>();
    meetings.forEach((m) => {
      const name = m.organization?.name;
      if (name && !m.type && !meetingTypes.includes(name)) orgs.add(name);
    });
    return Array.from(orgs).sort();
  }, [meetings, meetingTypes]);

  // Filtered and sorted meetings for the LIST VIEW
  const filteredMeetingsForList = useMemo(() => {
    const filtered = meetings.filter((m) => {
      // Status Filter
      const today = new Date().toLocaleDateString("en-CA");
      const isPast = m.meeting_date < today;
      const effectiveStatus = m.status || (isPast ? "Completed" : "Planned");

      if (statusTab === "past") {
        const isActuallyPast =
          effectiveStatus === "Completed" ||
          effectiveStatus === "Occurred" ||
          effectiveStatus === "Cancelled";
        if (!isActuallyPast) return false;
      }

      if (
        statusTab === "upcoming" &&
        effectiveStatus !== "Planned" &&
        effectiveStatus !== "Scheduled" &&
        effectiveStatus.toLowerCase() !== "scheduled"
      ) {
        return false;
      }

      // Organization Filter
      if (orgFilter && m.organization?.name !== orgFilter) return false;

      // Type Filter
      if (typeFilter && m.type !== typeFilter) return false;

      // Search Filter
      if (searchQuery) {
        const lowerQuery = searchQuery.toLowerCase();
        const matchesTitle = m.title.toLowerCase().includes(lowerQuery);
        const matchesSummary = m.summary?.toLowerCase().includes(lowerQuery);
        if (!matchesTitle && !matchesSummary) return false;
      }

      return true;
    });

    // Sort
    filtered.sort((a, b) => {
      const dateA = new Date(a.meeting_date).getTime();
      const dateB = new Date(b.meeting_date).getTime();
      return sortOrder === "asc" ? dateA - dateB : dateB - dateA;
    });

    return filtered;
  }, [meetings, statusTab, searchQuery, orgFilter, typeFilter, sortOrder]);

  const meetingsByMonth = useMemo(() => {
    const groups: { key: string; label: string; items: Meeting[] }[] = [];
    for (const m of filteredMeetingsForList) {
      const key = m.meeting_date.slice(0, 7);
      let group = groups[groups.length - 1];
      if (!group || group.key !== key) {
        const [y, mo] = key.split("-").map(Number);
        group = {
          key,
          label: new Date(y, mo - 1, 1).toLocaleDateString("en-CA", {
            month: "long",
            year: "numeric",
          }),
          items: [],
        };
        groups.push(group);
      }
      group.items.push(m);
    }
    return groups;
  }, [filteredMeetingsForList]);

  const hasActiveFilters = orgFilter || typeFilter || searchQuery;

  const updateFilters = (updates: Record<string, string | null>) => {
    const newParams = new URLSearchParams(searchParams);
    Object.entries(updates).forEach(([key, value]) => {
      if (value === null || value === "") {
        newParams.delete(key);
      } else {
        newParams.set(key, value);
      }
    });
    setSearchParams(newParams);
  };

  const updateYear = (year: string) => {
    if (year !== selectedYear.toString()) {
      updateFilters({ year });
    }
  };

  // Sync local search state with URL param
  useEffect(() => {
    setSearchQuery(qParam);
  }, [qParam]);

  // Debounce search URL updates
  useEffect(() => {
    const timer = setTimeout(() => {
      if (searchQuery !== qParam) {
        updateFilters({ q: searchQuery || null });
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery, qParam]);

  const clearFilters = () => {
    const newParams = new URLSearchParams();
    if (selectedYear !== currentYear)
      newParams.set("year", selectedYear.toString());
    if (view !== "list") newParams.set("view", view);
    newParams.set("status", "past");
    setSearchParams(newParams);
  };

  return (
    <div className="min-h-screen bg-zinc-50">
      <div className="container mx-auto max-w-6xl px-4 py-12">
        <PageHeader
          title="Meetings"
          icon={CalendarIcon}
          description="Agendas, minutes, video and decisions from every council and committee meeting."
          actions={
            <div className="flex items-center gap-1 rounded-lg bg-zinc-200/60 p-1">
              <button
                onClick={() => updateFilters({ view: "list" })}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-semibold transition-colors",
                  view === "list"
                    ? "bg-white text-zinc-900 shadow-sm"
                    : "text-zinc-500 hover:text-zinc-800",
                )}
              >
                <LayoutList className="h-4 w-4" />
                List
              </button>
              <button
                onClick={() => updateFilters({ view: "calendar" })}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-semibold transition-colors",
                  view === "calendar"
                    ? "bg-white text-zinc-900 shadow-sm"
                    : "text-zinc-500 hover:text-zinc-800",
                )}
              >
                <CalendarIcon className="h-4 w-4" />
                Calendar
              </button>
            </div>
          }
        />

        <Tabs
          value={view}
          onValueChange={(v) => updateFilters({ view: v })}
          className="w-full"
        >
          {/* Calendar View */}
          <TabsContent value="calendar" className="mt-0">
            <div className="bg-white rounded-2xl border border-zinc-200 shadow-sm overflow-hidden mb-8">
              <CalendarView meetings={meetings} />
            </div>
          </TabsContent>

          {/* List View */}
          <TabsContent value="list" className="mt-0 space-y-6">
            {/* Row 1: Year, Search, Status */}
            <div className="flex flex-col md:flex-row gap-4">
              {/* Year Selector */}
              <div className="flex items-center gap-2 bg-white border border-zinc-200 p-1 rounded-xl shadow-sm">
                <button
                  onClick={() =>
                    updateFilters({ year: (selectedYear - 1).toString() })
                  }
                  className="p-2 hover:bg-zinc-100 rounded-lg text-zinc-500"
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <select
                  value={selectedYear}
                  onInput={(e) => updateYear(e.currentTarget.value)}
                  onChange={(e) => updateYear(e.currentTarget.value)}
                  className="bg-transparent text-sm font-bold text-zinc-900 px-2 focus:outline-none cursor-pointer"
                >
                  {years.map((y) => (
                    <option key={y} value={y}>
                      {y}
                    </option>
                  ))}
                </select>
                <button
                  onClick={() =>
                    updateFilters({ year: (selectedYear + 1).toString() })
                  }
                  disabled={selectedYear >= currentYear}
                  className="p-2 hover:bg-zinc-100 rounded-lg text-zinc-500 disabled:opacity-30"
                >
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>

              {/* Search */}
              <div className="flex-1 relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-zinc-400" />
                <input
                  placeholder="Search meeting titles or topics..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full pl-10 pr-10 h-11 bg-white border border-zinc-200 shadow-sm rounded-xl focus:ring-2 focus:ring-brand-500/30 focus:outline-none"
                />
                {searchQuery && (
                  <button
                    onClick={() => setSearchQuery("")}
                    className="absolute right-3 top-1/2 -translate-y-1/2 p-1 hover:bg-zinc-100 rounded-full text-zinc-400"
                  >
                    <X className="h-3 w-3" />
                  </button>
                )}
              </div>

              {/* Status Tabs */}
              <div className="flex items-center bg-white border border-zinc-200 p-1 rounded-xl shadow-sm min-w-[260px]">
                <button
                  onClick={() => updateFilters({ status: null })}
                  className={cn(
                    "flex-1 px-3 py-2 text-sm font-semibold rounded-lg transition-colors",
                    statusTab === "all"
                      ? "bg-zinc-900 text-white"
                      : "text-zinc-500 hover:text-zinc-800",
                  )}
                >
                  All
                </button>
                <button
                  onClick={() => updateFilters({ status: "upcoming" })}
                  className={cn(
                    "flex-1 px-3 py-2 text-sm font-semibold rounded-lg transition-colors",
                    statusTab === "upcoming"
                      ? "bg-zinc-900 text-white"
                      : "text-zinc-500 hover:text-zinc-800",
                  )}
                >
                  Upcoming
                </button>
                <button
                  onClick={() => updateFilters({ status: "past" })}
                  className={cn(
                    "flex-1 px-3 py-2 text-sm font-semibold rounded-lg transition-colors",
                    statusTab === "past"
                      ? "bg-zinc-900 text-white"
                      : "text-zinc-500 hover:text-zinc-800",
                  )}
                >
                  Past
                </button>
              </div>
            </div>

            {/* Row 2: Organization & Type pills, Sort */}
            <div className="flex flex-col sm:flex-row sm:items-center gap-4">
              <div className="flex flex-wrap items-center gap-2 flex-1">
                {/* Organization pills */}
                {organizations.length > 0 && (
                  <>
                    {organizations.map((org) => (
                      <button
                        key={org}
                        onClick={() =>
                          updateFilters({
                            org: orgFilter === org ? null : org,
                          })
                        }
                        className={cn(
                          "px-3 py-1.5 text-xs font-semibold rounded-full border transition-colors",
                          orgFilter === org
                            ? "bg-brand-600 text-white border-brand-600"
                            : "bg-white text-zinc-600 border-zinc-200 hover:border-brand-300 hover:text-brand-700",
                        )}
                      >
                        {org}
                      </button>
                    ))}
                    {organizations.length > 0 && meetingTypes.length > 1 && (
                      <div className="w-px h-5 bg-zinc-200 mx-1 hidden sm:block" />
                    )}
                  </>
                )}

                {/* Type pills */}
                {meetingTypes.length > 1 &&
                  meetingTypes.map((type) => (
                    <button
                      key={type}
                      onClick={() =>
                        updateFilters({
                          type: typeFilter === type ? null : type,
                        })
                      }
                      className={cn(
                        "px-3 py-1.5 text-xs font-semibold rounded-full border transition-colors",
                        typeFilter === type
                          ? "bg-brand-600 text-white border-brand-600"
                          : "bg-white text-zinc-600 border-zinc-200 hover:border-brand-300 hover:text-brand-700",
                      )}
                    >
                      {type}
                    </button>
                  ))}
              </div>

              {/* Sort */}
              <div className="flex items-center gap-2 shrink-0">
                <ArrowUpDown className="h-3.5 w-3.5 text-zinc-400" />
                <select
                  value={sortOrder}
                  onChange={(e) => updateFilters({ sort: e.target.value })}
                  className="text-xs font-semibold text-zinc-600 bg-white border border-zinc-200 rounded-full px-3 py-1.5 focus:outline-none cursor-pointer"
                >
                  <option value="desc">Newest first</option>
                  <option value="asc">Oldest first</option>
                </select>
              </div>
            </div>

            {/* Results count & clear */}
            <div className="flex items-center gap-2">
              <span className="text-sm text-zinc-500">
                <span className="font-semibold text-zinc-900">
                  {filteredMeetingsForList.length}
                </span>{" "}
                {filteredMeetingsForList.length === 1 ? "meeting" : "meetings"}
              </span>
              {hasActiveFilters && (
                <button
                  onClick={clearFilters}
                  className="ml-2 text-xs font-bold text-brand-600 hover:text-brand-700 flex items-center gap-1"
                >
                  <X className="h-3 w-3" />
                  Clear filters
                </button>
              )}
            </div>

            {/* List Results */}
            <div className="flex flex-col gap-8 w-full min-h-[300px]">
              {filteredMeetingsForList.length === 0 ? (
                <div className="text-center py-24 bg-white rounded-2xl border border-zinc-200 border-dashed">
                  <div className="bg-zinc-50 w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-4">
                    <Search className="h-8 w-8 text-zinc-300" />
                  </div>
                  <h3 className="text-lg font-bold text-zinc-900 mb-1">
                    No meetings found
                  </h3>
                  <p className="text-zinc-500 max-w-xs mx-auto mb-6">
                    No meetings matching your criteria were found for{" "}
                    {selectedYear}.
                  </p>
                  <button
                    onClick={clearFilters}
                    className="text-sm font-bold text-brand-600 hover:underline"
                  >
                    Clear filters
                  </button>
                </div>
              ) : (
                meetingsByMonth.map((group) => (
                  <section key={group.key} aria-labelledby={`month-${group.key}`}>
                    <h2
                      id={`month-${group.key}`}
                      className="mb-2 px-1 text-sm font-semibold text-zinc-500"
                    >
                      {group.label}
                    </h2>
                    <div className="overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm divide-y divide-zinc-100">
                      {group.items.map((meeting) => (
                        <MeetingCard key={meeting.id} meeting={meeting} stats={statsMap[meeting.id]} />
                      ))}
                    </div>
                  </section>
                ))
              )}
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
