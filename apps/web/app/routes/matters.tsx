import type { Route } from "./+types/matters";
import { getMatters } from "../services/matters";
import { getSupabaseAdminClient } from "../lib/supabase.server";
import { Link, useRouteLoaderData, useSearchParams } from "react-router";
import type { Municipality } from "../lib/types";
import {
  FileText,
  ChevronRight,
  Search,
  Filter,
  Tag,
  Calendar,
  Book,
  MapPin,
  List,
  Map as MapIcon,
} from "lucide-react";
import { Badge } from "../components/ui/badge";
import { useState, useMemo, useRef, useEffect } from "react";
import { formatDate, cn } from "../lib/utils";
import { PageHeader } from "../components/ui/page-header";
import { displayTitle } from "../lib/display-text";
import { NativeSelect } from "../components/ui/native-select";
import { FilterBar } from "../components/ui/filter-bar";
import { SearchField } from "../components/ui/search-field";
import { MattersMap } from "../components/matters-map";
import type { Matter } from "../lib/types";
import { ogImageUrl, ogUrl } from "../lib/og";

export const meta: Route.MetaFunction = () => {
  return [
    { title: "Council Matters | ViewRoyal.ai" },
    { name: "description", content: "Active and historical council matters for View Royal" },
    { property: "og:title", content: "Council Matters | ViewRoyal.ai" },
    { property: "og:description", content: "Active and historical council matters for View Royal" },
    { property: "og:type", content: "website" },
    { property: "og:url", content: ogUrl("/matters") },
    { property: "og:image", content: ogImageUrl("Council Matters", { type: "matter" }) },
    { property: "og:image:width", content: "1200" },
    { property: "og:image:height", content: "630" },
    { name: "twitter:card", content: "summary_large_image" },
  ];
};

export async function loader() {
  try {
    const supabase = getSupabaseAdminClient();
    const matters = await getMatters(supabase);
    return { matters };
  } catch (error) {
    console.error("Error fetching matters:", error);
    return { matters: [] };
  }
}

export default function Matters({ loaderData }: Route.ComponentProps) {
  const { matters } = loaderData;
  const rootData = useRouteLoaderData("root") as { municipality?: Municipality } | undefined;
  const municipality = rootData?.municipality;
  const [searchParams, setSearchParams] = useSearchParams();
  const [filterText, setFilterText] = useState(searchParams.get("q") || "");
  const [statusFilter, setStatusFilter] = useState("All");
  const [categoryFilter, setCategoryFilter] = useState("All");
  const [viewMode, setViewMode] = useState<"list" | "map">("list");
  const [activeAddress, setActiveAddress] = useState<string | null>(null);
  const [focusedLocation, setFocusedLocation] = useState<
    { lat: number; lng: number } | undefined
  >();
  const [showMap, setShowMap] = useState(true);
  const PAGE_SIZE = 50;
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const sidebarRef = useRef<HTMLDivElement>(null);
  const addressRefs = useRef<Record<string, HTMLDivElement | null>>({});

  const filteredMatters = useMemo(() => {
    let result = matters;

    // Filter out procedural matters
    const proceduralTitles = [
      "call to order",
      "approval of agenda",
      "adjournment",
      "question period",
      "termination",
    ];
    result = result.filter(
      (m) => !proceduralTitles.includes(m.title.toLowerCase()),
    );

    if (categoryFilter !== "All") {
      result = result.filter((m) => m.category === categoryFilter);
    }

    if (statusFilter !== "All") {
      if (statusFilter === "Active") {
        result = result.filter((m) => m.status === "Active");
      } else if (statusFilter === "Completed") {
        result = result.filter((m) =>
          ["Adopted", "Completed"].includes(m.status),
        );
      } else if (statusFilter === "Inactive") {
        result = result.filter((m) =>
          ["Inactive", "Denied", "Repealed"].includes(m.status),
        );
      }
    }

    if (filterText) {
      const lower = filterText.toLowerCase();
      result = result.filter(
        (m) => {
          const meta = (m as any).meta && typeof (m as any).meta === "object"
            ? (m as any).meta
            : {};
          const aliases = Array.isArray(meta.aliases) ? meta.aliases : [];
          const searchable = [
            m.title,
            m.identifier,
            m.category,
            (m as any).description,
            (m as any).plain_english_summary,
            meta.entity_cluster,
            ...aliases,
            ...(m.addresses || []),
          ]
            .filter(Boolean)
            .join(" ")
            .toLowerCase();
          return searchable.includes(lower);
        },
      );
    }

    return result;
  }, [matters, filterText, statusFilter, categoryFilter]);

  // Group by address for Address View
  const mattersByAddress = useMemo(() => {
    const grouped: Record<string, typeof matters> = {};
    const noAddress: typeof matters = [];

    filteredMatters.forEach((matter) => {
      if (!matter.addresses || matter.addresses.length === 0) {
        noAddress.push(matter);
      } else {
        matter.addresses.forEach((addr: string) => {
          if (!grouped[addr]) grouped[addr] = [];
          grouped[addr].push(matter);
        });
      }
    });

    return {
      grouped: Object.entries(grouped).sort((a, b) => a[0].localeCompare(b[0])),
      noAddress,
    };
  }, [filteredMatters]);

  const handleAddressClick = (address: string, items: typeof matters) => {
    setActiveAddress(address);
    // Find a location for this address in the linked items
    const location = items
      .flatMap((m) => m.locations || [])
      .find((l) => l.address === address);
    if (location) {
      setFocusedLocation({ lat: location.lat, lng: location.lng });
    }
  };

  const handleMarkerClick = (matter: Matter, address?: string) => {
    const addr = address || matter.addresses?.[0];
    if (addr) {
      setActiveAddress(addr);
      setFocusedLocation(undefined); // Clear focus so user can still pan if they want, or keep it synced?
      // Let's not clear it, so it stays centered if they click.
      if (addressRefs.current[addr]) {
        addressRefs.current[addr]?.scrollIntoView({
          behavior: "smooth",
          block: "start",
        });
      }
    }
  };

  useEffect(() => {
    setVisibleCount(PAGE_SIZE);
  }, [filterText, statusFilter, categoryFilter]);

  const counts = useMemo(() => {
    return {
      All: matters.length,
      Active: matters.filter((m) => m.status === "Active").length,
      Completed: matters.filter((m) =>
        ["Adopted", "Completed"].includes(m.status),
      ).length,
      Inactive: matters.filter((m) =>
        ["Inactive", "Denied", "Repealed"].includes(m.status),
      ).length,
    };
  }, [matters]);

  // Status tabs only help when matters actually spread across statuses
  const statusTabs = [
    { value: "All", label: "All", count: counts.All },
    { value: "Active", label: "Active", count: counts.Active },
    { value: "Completed", label: "Adopted / completed", count: counts.Completed },
    { value: "Inactive", label: "Inactive / denied", count: counts.Inactive },
  ];
  const showStatusTabs =
    statusTabs.filter((t) => t.value !== "All" && t.count > 0).length > 1;

  const statusBadge = (status: string) => {
    if (status === "Active") return null;
    if (["Adopted", "Completed"].includes(status))
      return <Badge variant="success">{status}</Badge>;
    if (["Denied", "Repealed"].includes(status))
      return <Badge variant="danger">{status}</Badge>;
    return <Badge variant="muted">{status}</Badge>;
  };

  const categories = useMemo(() => {
    const cats = new Set(matters.map((m) => m.category || "General"));
    return ["All", ...Array.from(cats).sort()];
  }, [matters]);

  return (
    <div className="min-h-screen bg-zinc-50">
      <div className="container mx-auto max-w-5xl px-4 py-12">
        <PageHeader
          title="Matters"
          icon={Tag}
          description="Bylaws, development applications and recurring items, tracked as they move through council."
          actions={
            <div className="flex items-center gap-1 rounded-lg bg-zinc-200/60 p-1">
              <button
                onClick={() => setViewMode("list")}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-semibold transition-colors",
                  viewMode === "list"
                    ? "bg-white text-zinc-900 shadow-sm"
                    : "text-zinc-500 hover:text-zinc-800",
                )}
              >
                List
              </button>
              <button
                onClick={() => setViewMode("map")}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-semibold transition-colors",
                  viewMode === "map"
                    ? "bg-white text-zinc-900 shadow-sm"
                    : "text-zinc-500 hover:text-zinc-800",
                )}
              >
                Map
              </button>
            </div>
          }
        />

        <FilterBar
          search={
            <SearchField
              aria-label="Search matters"
              placeholder="Search by title, bylaw number or address"
              value={filterText}
              onValueChange={(value) => {
                setFilterText(value);
                const next = new URLSearchParams(searchParams);
                if (value.trim()) next.set("q", value);
                else next.delete("q");
                setSearchParams(next, { replace: true, preventScrollReset: true });
              }}
            />
          }
          controls={
            <>
              <NativeSelect
                aria-label="Category"
                className="min-w-0 flex-1 sm:w-44 sm:flex-none"
                value={categoryFilter}
                onChange={(e) => setCategoryFilter(e.currentTarget.value)}
              >
                {categories.map((cat) => (
                  <option key={cat} value={cat}>
                    {cat === "All" ? "All categories" : cat}
                  </option>
                ))}
              </NativeSelect>
              {showStatusTabs && (
                <NativeSelect
                  aria-label="Status"
                  className="min-w-0 flex-1 sm:w-48 sm:flex-none"
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.currentTarget.value)}
                >
                  {statusTabs
                    .filter((t) => t.value === "All" || t.count > 0)
                    .map((t) => (
                      <option key={t.value} value={t.value}>
                        {t.value === "All" ? "Any status" : t.label} ({t.count.toLocaleString()})
                      </option>
                    ))}
                </NativeSelect>
              )}
            </>
          }
          status={
            <>
              <span className="font-semibold text-zinc-900">
                {filteredMatters.length.toLocaleString()}
              </span>{" "}
              {filteredMatters.length === 1 ? "matter" : "matters"}
            </>
          }
        />

        <div
          className={cn(
            "grid gap-6",
            viewMode === "map" && showMap && "grid-cols-1 lg:grid-cols-12",
          )}
        >
          {filteredMatters.length === 0 ? (
            <div className="text-center py-24 bg-white rounded-2xl border border-dashed border-zinc-200 lg:col-span-12">
              <Filter className="h-12 w-12 text-zinc-200 mx-auto mb-4" />
              <p className="text-zinc-500 text-lg">
                No matters match your search.
              </p>
            </div>
          ) : viewMode === "list" ? (
            <div>
              <ul className="overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm divide-y divide-zinc-100">
                {filteredMatters.slice(0, visibleCount).map((matter) => {
                  const bylawLabel =
                    matter.bylaw &&
                    !matter.identifier?.toLowerCase().includes("bylaw")
                      ? matter.bylaw.bylaw_number
                        ? `Bylaw ${matter.bylaw.bylaw_number}`
                        : "Bylaw"
                      : null;
                  return (
                    <li key={matter.id}>
                      <Link
                        to={`/matters/${matter.id}`}
                        className="group flex items-start gap-4 px-5 py-4 transition-colors hover:bg-zinc-50"
                      >
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                            <h3 className="text-base font-semibold leading-snug text-zinc-900 group-hover:text-brand-700">
                              {displayTitle(matter.title)}
                            </h3>
                            {statusBadge(matter.status)}
                          </div>
                          <p className="mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-xs text-zinc-500">
                            <span className="font-medium text-zinc-600">
                              {matter.category || "General"}
                            </span>
                            {matter.identifier && (
                              <>
                                <span aria-hidden="true">·</span>
                                <span className="tabular-nums text-zinc-600">
                                  {matter.identifier}
                                </span>
                              </>
                            )}
                            {bylawLabel && (
                              <>
                                <span aria-hidden="true">·</span>
                                <span className="inline-flex items-center gap-1">
                                  <Book className="h-3 w-3" />
                                  {bylawLabel}
                                </span>
                              </>
                            )}
                            {matter.addresses?.slice(0, 3).map((addr: string) => (
                              <span key={addr} className="inline-flex items-center gap-1">
                                <span aria-hidden="true">·</span>
                                <MapPin className="h-3 w-3" />
                                {addr}
                              </span>
                            ))}
                          </p>
                          {matter.description && (
                            <p className="mt-1.5 max-w-[75ch] text-sm leading-relaxed text-zinc-600 line-clamp-2">
                              {matter.description}
                            </p>
                          )}
                        </div>
                        <div className="flex shrink-0 items-center gap-3 self-center">
                          {matter.last_seen && (
                            <span className="hidden text-xs tabular-nums text-zinc-500 sm:inline">
                              {formatDate(matter.last_seen, {
                                month: "short",
                                day: "numeric",
                                year: "numeric",
                              })}
                            </span>
                          )}
                          <ChevronRight className="h-5 w-5 text-zinc-300 group-hover:text-brand-600" />
                        </div>
                      </Link>
                    </li>
                  );
                })}
              </ul>
              {visibleCount < filteredMatters.length && (
                <div className="mt-6 flex justify-center">
                  <button
                    onClick={() => setVisibleCount((n) => n + PAGE_SIZE)}
                    className="rounded-full border border-zinc-200 bg-white px-5 py-2 text-sm font-semibold text-zinc-700 shadow-sm transition-colors hover:border-brand-300 hover:text-brand-700"
                  >
                    Show more
                    <span className="ml-1.5 font-normal text-zinc-500">
                      ({(filteredMatters.length - visibleCount).toLocaleString()} remaining)
                    </span>
                  </button>
                </div>
              )}
            </div>
          ) : (
            <>
              {/* Sidebar / List for Properties View */}
              <div
                ref={sidebarRef}
                className={cn(
                  "overflow-y-auto space-y-4 pr-2 scroll-smooth transition-all duration-500",
                  showMap ? "lg:col-span-4 h-[600px]" : "col-span-full h-auto",
                )}
              >
                <div className="flex items-center justify-between px-2 mb-2">
                  <h2 className="text-sm font-semibold text-zinc-500">
                    {mattersByAddress.grouped.length} properties located
                  </h2>
                  <button
                    onClick={() => setShowMap(!showMap)}
                    className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-zinc-100 hover:bg-zinc-200 text-[10px] font-bold text-zinc-600 transition-colors"
                  >
                    {showMap ? (
                      <>
                        <List className="h-3 w-3" />
                        Expand List
                      </>
                    ) : (
                      <>
                        <MapIcon className="h-3 w-3" />
                        Show Map
                      </>
                    )}
                  </button>
                </div>

                <div
                  className={cn(
                    "grid gap-4",
                    !showMap && "grid-cols-1 md:grid-cols-2 lg:grid-cols-3",
                  )}
                >
                  {mattersByAddress.grouped.map(([address, items]) => (
                    <div
                      key={address}
                      ref={(el) => {
                        addressRefs.current[address] = el;
                      }}
                      onClick={() => handleAddressClick(address, items)}
                      className={cn(
                        "bg-white p-4 rounded-2xl border transition-all duration-500 cursor-pointer",
                        activeAddress === address
                          ? "border-brand-500 shadow-md ring-2 ring-brand-500/10 scale-[1.02]"
                          : "border-zinc-200 shadow-sm hover:border-brand-200",
                      )}
                    >
                      <h3 className="text-sm font-bold text-zinc-900 flex items-center gap-2 mb-3">
                        <MapPin
                          className={cn(
                            "h-3 w-3",
                            activeAddress === address
                              ? "text-brand-600 animate-bounce"
                              : "text-zinc-400",
                          )}
                        />
                        {address}
                      </h3>
                      <div className="space-y-2">
                        {items.map((matter) => (
                          <Link
                            key={matter.id}
                            to={`/matters/${matter.id}`}
                            onClick={(e) => e.stopPropagation()}
                            className="block p-2 rounded-lg hover:bg-zinc-50 border border-transparent hover:border-zinc-100 transition-all group"
                          >
                            <div className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest mb-0.5">
                              {matter.category}
                            </div>
                            <div className="text-xs font-bold text-zinc-700 group-hover:text-brand-600 line-clamp-1">
                              {matter.title}
                            </div>
                          </Link>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>

                {mattersByAddress.grouped.length === 0 && (
                  <div className="p-8 text-center bg-white rounded-2xl border border-dashed border-zinc-200">
                    <p className="text-xs text-zinc-500 italic">
                      No address data available.
                    </p>
                  </div>
                )}
              </div>

              {/* Map Column */}
              {showMap && (
                <div className="lg:col-span-8">
                  <MattersMap
                    matters={filteredMatters}
                    onMarkerClick={handleMarkerClick}
                    activeLocation={focusedLocation}
                    selectedAddress={activeAddress}
                    mapCenter={municipality?.map_center_lat && municipality?.map_center_lng ? { lat: municipality.map_center_lat, lng: municipality.map_center_lng } : undefined}
                  />
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
