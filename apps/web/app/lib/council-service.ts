import { civicToday, councilTermStatus } from "./council-terms";
import type { Person } from "./types";

/** Historical summaries retain year precision; they never create statistical memberships. */
export interface CouncilServiceHistory {
  organization_id: number;
  role: string;
  start_year: number;
  end_year: number;
  source_url: string;
}

export interface CouncilServicePeriod {
  organizationId: number;
  organizationName: string;
  role: string;
  startYear?: number;
  endYear?: number;
  startDate?: string;
  endDate?: string | null;
  status: "past" | "current" | "upcoming";
  sourceUrl?: string;
}

/** Combine adjacent appointments in the same office, never across a gap or into a future term. */
export function councilServicePeriods(person: Pick<Person, "memberships" | "council_service_history">, today = civicToday()): CouncilServicePeriod[] {
  const memberships = (person.memberships || [])
    .filter((m) => m.organization?.classification === "Council")
    .slice().sort((a, b) => (a.start_date || "").localeCompare(b.start_date || ""));
  const periods: CouncilServicePeriod[] = [];
  for (const m of memberships) {
    const status = councilTermStatus(m, today);
    const prior = [...periods].reverse().find((p) => p.role === m.role && p.organizationId === m.organization_id
      && (p.status === "upcoming") === (status === "upcoming"));
    const nextDay = prior?.endDate ? new Date(`${prior.endDate}T00:00:00Z`) : null;
    if (nextDay) nextDay.setUTCDate(nextDay.getUTCDate() + 1);
    if (prior?.startDate && m.start_date && (!prior.endDate || nextDay!.toISOString().slice(0, 10) >= m.start_date)) {
      prior.endDate = !prior.endDate || !m.end_date ? null : prior.endDate > m.end_date ? prior.endDate : m.end_date;
      prior.endYear = prior.endDate ? Number(prior.endDate.slice(0, 4)) : undefined;
      prior.status = councilTermStatus({ start_date: prior.startDate, end_date: prior.endDate }, today);
    } else {
      periods.push({ organizationId: m.organization_id, organizationName: m.organization?.name || "Council", role: m.role,
        startDate: m.start_date, endDate: m.end_date,
        startYear: m.start_date ? Number(m.start_date.slice(0, 4)) : undefined,
        endYear: m.end_date ? Number(m.end_date.slice(0, 4)) : undefined, status });
    }
  }
  const history: unknown = person.council_service_history;
  if (Array.isArray(history)) {
    for (const h of history as CouncilServiceHistory[]) {
      if (!h || !Number.isInteger(h.start_year) || !Number.isInteger(h.end_year) || h.start_year > h.end_year
        || h.end_year > Number(today.slice(0, 4)) || typeof h.role !== "string"
        || typeof h.source_url !== "string" || !h.source_url.startsWith("https://")) continue;
      const organization = memberships.find((m) => m.organization_id === h.organization_id)?.organization;
      if (!organization) continue;
      // A sourced completed tenure may include the dated appointments already in the DB.
      // Hide only appointments wholly contained by that explicit tenure, retaining all raw records.
      for (let i = periods.length - 1; i >= 0; i--) {
        const p = periods[i];
        if (p.status === "past" && p.organizationId === h.organization_id && p.role === h.role
          && p.startYear !== undefined && p.endYear !== undefined && p.startYear >= h.start_year && p.endYear <= h.end_year) periods.splice(i, 1);
      }
      periods.push({ organizationId: h.organization_id, organizationName: organization.name || "Council", role: h.role,
        startYear: h.start_year, endYear: h.end_year, status: "past", sourceUrl: h.source_url });
    }
  }
  return periods.sort((a, b) => (b.startYear || 0) - (a.startYear || 0));
}

export function councilServiceRange(period: CouncilServicePeriod): string {
  if (!period.startYear) return "Start date unrecorded";
  if (period.status === "upcoming") return `From ${period.startYear}`;
  if (period.status === "current") return `${period.startYear}–present`;
  return period.endYear ? `${period.startYear}–${period.endYear}` : `${period.startYear}–end date unrecorded`;
}
