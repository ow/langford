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
  ArrowDownWideNarrow,
  ArrowUpNarrowWide,
} from "lucide-react";
import { MeetingCard } from "../components/meeting-card";
import { PageHeader } from "../components/ui/page-header";
import { NativeSelect } from "../components/ui/native-select";
import { FilterBar } from "../components/ui/filter-bar";
import { SearchField } from "../components/ui/search-field";
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

  const view = searchParams.get("view") || "list";
  const qParam = searchParams.get("q") || "";
  const [searchQuery, setSearchQuery] = useState(qParam);
  const typeFilter = searchParams.get("type") || "";
  const sortOrder = searchParams.get("sort") === "asc" ? "asc" : "desc";

  const years = useMemo(() => {
    const yearsArr: number[] = [];
    for (let y = currentYear; y >= 2008; y--) yearsArr.push(y);
    return yearsArr;
  }, [currentYear]);

  const meetingTypes = useMemo(() => {
    const types = new Set<string>();
    meetings.forEach((m) => {
      if (m.type) types.add(m.type);
    });
    return Array.from(types).sort();
  }, [meetings]);

  const filtered = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    const list = meetings.filter((m) => {
      if (typeFilter && m.type !== typeFilter) return false;
      if (q) {
        const hit =
          m.title.toLowerCase().includes(q) ||
          m.summary?.toLowerCase().includes(q) ||
          m.organization?.name?.toLowerCase().includes(q);
        if (!hit) return false;
      }
      return true;
    });
    list.sort((a, b) =>
      sortOrder === "asc"
        ? a.meeting_date.localeCompare(b.meeting_date)
        : b.meeting_date.localeCompare(a.meeting_date),
    );
    return list;
  }, [meetings, searchQuery, typeFilter, sortOrder]);

  // Upcoming meetings get their own section (soonest first); past meetings
  // are grouped by month.
  const { upcoming, pastByMonth } = useMemo(() => {
    const today = new Date().toLocaleDateString("en-CA");
    const upcoming = filtered
      .filter((m) => m.meeting_date >= today && m.status !== "Cancelled")
      .sort((a, b) => a.meeting_date.localeCompare(b.meeting_date));
    const upcomingIds = new Set(upcoming.map((m) => m.id));
    const groups: { key: string; label: string; items: Meeting[] }[] = [];
    for (const m of filtered) {
      if (upcomingIds.has(m.id)) continue;
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
    return { upcoming, pastByMonth: groups };
  }, [filtered]);

  const hasActiveFilters = !!(typeFilter || searchQuery);

  const updateFilters = (updates: Record<string, string | null>) => {
    const next = new URLSearchParams(searchParams);
    Object.entries(updates).forEach(([key, value]) => {
      if (value === null || value === "") next.delete(key);
      else next.set(key, value);
    });
    setSearchParams(next, { preventScrollReset: true });
  };

  useEffect(() => {
    setSearchQuery(qParam);
  }, [qParam]);

  useEffect(() => {
    const timer = setTimeout(() => {
      if (searchQuery !== qParam) updateFilters({ q: searchQuery || null });
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery, qParam]);

  const clearFilters = () => {
    setSearchQuery("");
    updateFilters({ q: null, type: null });
  };

  const viewButton = (
    value: "list" | "calendar",
    Icon: typeof LayoutList,
    label: string,
  ) => (
    <button
      onClick={() => updateFilters({ view: value === "list" ? null : value })}
      aria-pressed={view === value}
      className={cn(
        "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-semibold transition-colors",
        view === value
          ? "bg-white text-zinc-900 shadow-sm"
          : "text-zinc-500 hover:text-zinc-800",
      )}
    >
      <Icon className="h-4 w-4" />
      {label}
    </button>
  );

  const group = (
    key: string,
    label: string,
    items: Meeting[],
    tone: "default" | "brand" = "default",
  ) => (
    <section key={key} aria-labelledby={`group-${key}`}>
      <h2
        id={`group-${key}`}
        className={cn(
          "mb-2 flex items-baseline gap-2 px-1 text-sm font-semibold",
          tone === "brand" ? "text-brand-700" : "text-zinc-900",
        )}
      >
        {label}
        <span className="text-xs font-normal text-zinc-400">{items.length}</span>
      </h2>
      <div
        className={cn(
          "overflow-hidden rounded-2xl border bg-white shadow-sm divide-y divide-zinc-100",
          tone === "brand" ? "border-brand-200" : "border-zinc-200",
        )}
      >
        {items.map((meeting) => (
          <MeetingCard key={meeting.id} meeting={meeting} stats={statsMap[meeting.id]} />
        ))}
      </div>
    </section>
  );

  return (
    <div className="min-h-screen bg-zinc-50">
      <div className="container mx-auto max-w-5xl px-4 py-12">
        <PageHeader
          title="Meetings"
          icon={CalendarIcon}
          description="Agendas, minutes, video and decisions from every council and committee meeting."
          actions={
            <div className="flex items-center gap-1 rounded-lg bg-zinc-200/60 p-1">
              {viewButton("list", LayoutList, "List")}
              {viewButton("calendar", CalendarIcon, "Calendar")}
            </div>
          }
        />

        {view === "calendar" ? (
          <div className="overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm">
            <CalendarView meetings={meetings} />
          </div>
        ) : (
          <>
            <FilterBar
              search={
                <SearchField
                  aria-label="Search meetings"
                  placeholder="Search titles and summaries"
                  value={searchQuery}
                  onValueChange={setSearchQuery}
                />
              }
              controls={
                <>
                  <NativeSelect
                    aria-label="Year"
                    className="w-28"
                    value={selectedYear}
                    onChange={(e) =>
                      updateFilters({
                        year:
                          e.currentTarget.value === String(currentYear)
                            ? null
                            : e.currentTarget.value,
                      })
                    }
                  >
                    {years.map((y) => (
                      <option key={y} value={y}>
                        {y}
                      </option>
                    ))}
                  </NativeSelect>
                  {meetingTypes.length > 1 && (
                    <NativeSelect
                      aria-label="Meeting type"
                      className="min-w-0 flex-1 sm:w-52 sm:flex-none"
                      value={typeFilter}
                      onChange={(e) => updateFilters({ type: e.currentTarget.value || null })}
                    >
                      <option value="">All meeting types</option>
                      {meetingTypes.map((t) => (
                        <option key={t} value={t}>
                          {t}
                        </option>
                      ))}
                    </NativeSelect>
                  )}
                  <button
                    onClick={() => updateFilters({ sort: sortOrder === "desc" ? "asc" : null })}
                    aria-label={sortOrder === "desc" ? "Newest first — switch to oldest first" : "Oldest first — switch to newest first"}
                    title={sortOrder === "desc" ? "Newest first" : "Oldest first"}
                    className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-zinc-200 bg-white text-zinc-500 shadow-xs transition-colors hover:border-zinc-300 hover:text-zinc-800"
                  >
                    {sortOrder === "desc" ? (
                      <ArrowDownWideNarrow className="h-4 w-4" />
                    ) : (
                      <ArrowUpNarrowWide className="h-4 w-4" />
                    )}
                  </button>
                </>
              }
              status={
                hasActiveFilters && (
                  <>
                    <span className="font-semibold text-zinc-900">{filtered.length}</span>{" "}
                    {filtered.length === 1 ? "result" : "results"}
                    <button onClick={clearFilters} className="ml-2 font-semibold text-brand-700 hover:text-brand-800">
                      Clear
                    </button>
                  </>
                )
              }
            />

            {filtered.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-zinc-300 bg-white px-6 py-16 text-center">
                <h3 className="text-base font-semibold text-zinc-900">No meetings found</h3>
                <p className="mx-auto mt-1 max-w-sm text-sm text-zinc-500">
                  {hasActiveFilters
                    ? `Nothing in ${selectedYear} matches those filters.`
                    : `No meetings recorded for ${selectedYear}.`}
                </p>
                {hasActiveFilters && (
                  <button
                    onClick={clearFilters}
                    className="mt-4 text-sm font-semibold text-brand-700 hover:text-brand-800"
                  >
                    Clear filters
                  </button>
                )}
              </div>
            ) : (
              <div className="flex flex-col gap-8">
                {upcoming.length > 0 && group("upcoming", "Upcoming", upcoming, "brand")}
                {pastByMonth.map((g) => group(g.key, g.label, g.items))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
