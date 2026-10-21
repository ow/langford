export const RECENT_PUBLIC_TTL = 300;
export const HISTORICAL_PUBLIC_TTL = 86400;
/** Allow a month for post-meeting publication/corrections before the longer policy. */
export function historicalPublicDate(date: unknown): boolean {
  if (typeof date !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(date)) return false;
  const timestamp = Date.parse(`${date}T00:00:00Z`);
  return Number.isFinite(timestamp) && new Date(timestamp).toISOString().slice(0, 10) === date && timestamp <= Date.now() - 30 * 86400_000;
}
