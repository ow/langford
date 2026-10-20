import { getSupabaseAdminClient } from "../lib/supabase.server";
import { getAiRequestContext } from "./ai/usage-sink.server";
import { latestIngestAt } from "./hybrid-search.server";

/**
 * Serve an expensive, read-mostly computation from `computed_cache`.
 * Fresh = computed after the latest ingested meeting and within the last 6 hours. A stale row is returned
 * immediately and recomputed in the background (ctx.waitUntil); with no row the
 * first caller computes it. Same code path as before, so results are identical.
 */
const inFlight = new Map<string, Promise<unknown>>();
const MAX_AGE_MS = 6 * 60 * 60 * 1000;

export async function cachedCompute<T>(key: string, compute: () => Promise<T>): Promise<T> {
  const supabase = getSupabaseAdminClient();
  const [{ data: row }, ingestAt] = await Promise.all([
    supabase.from("computed_cache").select("payload, computed_at").eq("key", key).maybeSingle(),
    latestIngestAt().catch(() => new Date(0).toISOString()),
  ]);

  const refresh = () => {
    if (!inFlight.has(key)) {
      const job = compute()
        .then((payload) =>
          supabase.from("computed_cache").upsert({ key, payload, computed_at: new Date().toISOString() }).then(() => payload),
        )
        .finally(() => inFlight.delete(key));
      inFlight.set(key, job);
    }
    return inFlight.get(key) as Promise<T>;
  };

  // Identity corrections and other edits don't touch meetings, so also cap the age.
  const fresh = row && row.computed_at > ingestAt && Date.now() - new Date(row.computed_at).getTime() < MAX_AGE_MS;
  if (fresh) return row!.payload as T;
  if (row) {
    const job = refresh().catch((error) => console.error(`[computed-cache] refresh ${key} failed:`, error));
    getAiRequestContext()?.waitUntil?.(job);
    return row.payload as T;
  }
  return refresh();
}
