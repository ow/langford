import { useState } from "react";
import type { Route } from "./+types/people";
import { getMunicipalityFromMatches } from "../lib/municipality-helpers";
import { ogImageUrl, ogUrl } from "../lib/og";

export const meta: Route.MetaFunction = ({ matches }) => {
  const municipality = getMunicipalityFromMatches(matches);
  const shortName = municipality?.short_name || "View Royal";
  const description = `${shortName} council members, attendance records, and voting history.`;
  return [
    { title: "Council Members | ViewRoyal.ai" },
    { name: "description", content: description },
    { property: "og:title", content: "Council Members | ViewRoyal.ai" },
    { property: "og:description", content: description },
    { property: "og:type", content: "website" },
    { property: "og:url", content: ogUrl("/people") },
    { property: "og:image", content: ogImageUrl("Council Members", { type: "person" }) },
    { property: "og:image:width", content: "1200" },
    { property: "og:image:height", content: "630" },
    { name: "twitter:card", content: "summary_large_image" },
  ];
};
import { getRawPeopleData, calculateAttendance } from "../services/people";
import { getCouncilTerms } from "../services/council-terms";
import { getMunicipality } from "../services/municipality";
import { getSupabaseAdminClient } from "../lib/supabase.server";
import { civicToday, councilTermStatus, councilTermLabel, councilRoster, membershipIsActiveOn } from "../lib/council-terms";
import type { Municipality } from "../lib/types";
import { Link, useRouteLoaderData, useSearchParams } from "react-router";
import { Users, Search } from "lucide-react";
import { Input } from "../components/ui/input";
import { Badge } from "../components/ui/badge";
import { PersonCard } from "../components/person-card";
import { formatDate } from "../lib/utils";

export async function loader() {
  const supabase = getSupabaseAdminClient();
  const municipality = await getMunicipality(supabase);
  const [rawData, terms] = await Promise.all([
    getRawPeopleData(supabase, municipality.id), getCouncilTerms(supabase, municipality.id),
  ]);
  return { rawData, terms, today: civicToday() };
}

export default function PeopleList({ loaderData }: Route.ComponentProps) {
  const { rawData, terms, today } = loaderData;
  const rootData = useRouteLoaderData("root") as { municipality?: Municipality } | undefined;
  const shortName = rootData?.municipality?.short_name || "Council";
  const [searchTerm, setSearchTerm] = useState("");
  const [params, setParams] = useSearchParams();
  const current = terms.find((term) => councilTermStatus(term, today) === "current");
  const selected = terms.find((term) => String(term.id) === params.get("term")) || current || terms[0];
  const status = selected ? councilTermStatus(selected, today) : null;
  // Without verified term dates, show only dated current memberships and no invented term.
  const range = selected || { start_date: "0001-01-01", end_date: null };
  const roster = councilRoster(rawData.people, range, today)
    .filter(({ person, status: memberStatus }) =>
      person.name.toLowerCase().includes(searchTerm.toLowerCase()) && (selected || memberStatus === "current"))
    .sort((a, b) => {
      const mayorA = a.memberships.some((membership) => membership.role === "Mayor");
      const mayorB = b.memberships.some((membership) => membership.role === "Mayor");
      return Number(mayorB) - Number(mayorA) || a.person.name.localeCompare(b.person.name);
    });
  const members = roster.filter((member) => status !== "current" || member.status !== "past");
  const formerMembers = status === "current" ? roster.filter((member) => member.status === "past") : [];

  const renderMembers = (entries: typeof roster) => entries.map(({ person, memberships, status: memberStatus }) => {
    const membership = memberships.find((m) => membershipIsActiveOn(m, today)) || memberships[0];
    const role = membership?.role || "Council member";
    const displayRole = memberStatus === "upcoming" ? `${role}-elect` : memberStatus === "past" ? `Former ${role.toLowerCase()}` : role;
    const stats = calculateAttendance(person, rawData.meetings, rawData.attendance, rawData.councilId, {
      start: range.start_date, end: range.end_date && range.end_date < today ? range.end_date : today,
    });
    return <PersonCard key={person.id} person={{ ...person, stats }} role={displayRole} showStats={memberStatus !== "upcoming"} />;
  });

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto flex max-w-4xl flex-col gap-8 px-4 py-8">
        <header className="flex flex-col gap-3">
          <h1 className="flex items-center gap-3 text-3xl font-bold"><Users className="size-8" />{shortName} Council</h1>
          <p className="text-muted-foreground">Explore who serves, who has been elected, and the record of each council term.</p>
          <nav className="flex gap-5 text-sm"><Link className="underline underline-offset-4" to="/elections">Election results</Link><Link className="underline underline-offset-4" to={`/alignment${selected ? `?term=${selected.id}` : ""}`}>Voting alignment</Link></nav>
        </header>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
          <label className="flex flex-1 flex-col gap-2 text-sm font-medium" htmlFor="council-term">
            Council term
            <select id="council-term" className="h-10 rounded-md border border-input bg-background px-3" value={selected?.id || ""} disabled={!terms.length} onChange={(event) => { const next = new URLSearchParams(params); next.set("term", event.target.value); setParams(next); }}>
              {!terms.length && <option value="">Current council · term dates unavailable</option>}
              {terms.map((term) => <option key={term.id} value={term.id}>{councilTermLabel(term, today)}</option>)}
            </select>
          </label>
          <div className="relative flex-1"><Search aria-hidden="true" className="absolute left-3 top-3 size-4 text-muted-foreground" /><Input aria-label="Search council members" placeholder="Search members…" className="pl-9" value={searchTerm} onChange={(event) => setSearchTerm(event.target.value)} /></div>
        </div>
        <section className="flex flex-col gap-4" aria-labelledby="selected-term-heading">
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-3"><h2 id="selected-term-heading" className="text-xl font-semibold">{selected ? councilTermLabel(selected, today) : "Current council"}</h2>{status === "upcoming" && <Badge variant="secondary">Incoming</Badge>}</div>
            {selected && <p className="text-sm text-muted-foreground">{status === "upcoming" ? "Scheduled to take office " : "Term began "}{formatDate(selected.start_date)}{selected.end_date ? ` · Ends ${formatDate(selected.end_date)}` : ""}</p>}
            {status === "upcoming" && <p className="text-sm text-muted-foreground">Election results identify the incoming council. Members currently serving remain in office until the new term begins. There are no attendance or voting statistics for this term yet.</p>}
            {!selected && <p className="text-sm text-muted-foreground">Verified term dates have not been recorded. Only members serving today are shown.</p>}
          </div>
          <div className="grid gap-4">{renderMembers(members)}</div>
          {!members.length && <p className="py-6 text-muted-foreground">No members match this selection.</p>}
        </section>
        {!!formerMembers.length && <section className="flex flex-col gap-4"><h2 className="text-lg font-semibold">Also served during this term</h2><p className="text-sm text-muted-foreground">These members left office before the end of the term.</p><div className="grid gap-4">{renderMembers(formerMembers)}</div></section>}
      </div>
    </div>
  );
}
