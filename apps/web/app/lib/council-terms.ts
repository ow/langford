/** Civil dates are inclusive and use the municipality's local calendar. */
type ServiceDates = { start_date?: string | null; end_date?: string | null };

export function civicToday(now = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Vancouver", year: "numeric", month: "2-digit", day: "2-digit",
  }).format(now);
}

export function membershipIsActiveOn(membership: ServiceDates, date: string): boolean {
  return (!membership.start_date || membership.start_date <= date)
    && (!membership.end_date || membership.end_date >= date);
}

export function membershipOverlapsRange(membership: ServiceDates, start: string, end?: string | null): boolean {
  return (!end || !membership.start_date || membership.start_date <= end)
    && (!membership.end_date || membership.end_date >= start);
}

export function councilTermStatus(term: ServiceDates, today = civicToday()): "upcoming" | "current" | "past" {
  if (term.start_date && term.start_date > today) return "upcoming";
  if (term.end_date && term.end_date < today) return "past";
  return "current";
}

export function councilTermLabel(term: ServiceDates & { name: string }, today = civicToday()): string {
  const status = councilTermStatus(term, today);
  return `${status === "upcoming" ? "Council-elect" : status === "current" ? "Current council" : "Past council"} · ${term.name}`;
}

type CouncilMembership = ServiceDates & {
  role?: string;
  organization?: { classification?: string };
};

/** Preserve every service interval; election day does not confer current office. */
export function councilRoster<T extends { memberships: CouncilMembership[] }>(
  people: T[], term: ServiceDates & { start_date: string }, today = civicToday(),
) {
  const termStatus = councilTermStatus(term, today);
  return people.flatMap((person) => {
    const memberships = person.memberships.filter((m) =>
      m.organization?.classification === "Council"
      && membershipOverlapsRange(m, term.start_date, term.end_date));
    if (!memberships.length) return [];
    const status = termStatus === "upcoming" ? "upcoming"
      : memberships.some((m) => membershipIsActiveOn(m, today)) && termStatus === "current"
        ? "current" : "past";
    return [{ person, memberships, status }];
  });
}
