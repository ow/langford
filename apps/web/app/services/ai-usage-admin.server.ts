import type { SupabaseClient } from "@supabase/supabase-js";
import {
  summarizeUsage,
  type AiUsageDashboard,
  type AiUsageFailure,
  type AiUsageSummaryRow,
} from "./ai-usage";

export type { AiUsageDashboard } from "./ai-usage";

/** AI usage for the admin pipeline page. Never throws: a missing table reads as unavailable. */
export async function getAiUsageDashboard(
  supabase: SupabaseClient,
  { windows = [7, 30], now = new Date() }: { windows?: number[]; now?: Date } = {},
): Promise<AiUsageDashboard> {
  try {
    const sinceFor = (days: number) => new Date(now.getTime() - days * 86_400_000).toISOString();
    const [summaries, failures] = await Promise.all([
      Promise.all(
        windows.map((days) => supabase.rpc("ai_usage_summary", { since: sinceFor(days) })),
      ),
      supabase
        .from("ai_usage")
        .select("id, created_at, source, stage, model, job, meeting_id, error")
        .eq("ok", false)
        .order("created_at", { ascending: false })
        .limit(20),
    ]);
    const firstError = summaries.find((r) => r.error)?.error ?? failures.error;
    if (firstError) {
      return { available: false, error: firstError.message, windows: [], failures: [] };
    }
    return {
      available: true,
      windows: windows.map((days, i) => summarizeUsage(days, (summaries[i].data ?? []) as AiUsageSummaryRow[])),
      failures: (failures.data ?? []) as AiUsageFailure[],
    };
  } catch (err) {
    return { available: false, error: (err as Error).message, windows: [], failures: [] };
  }
}
