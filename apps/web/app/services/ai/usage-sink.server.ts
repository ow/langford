/**
 * Persist AI usage events to `ai_usage` (admin client, fire-and-forget).
 *
 * The Worker entry wraps each request in `runWithAiRequestContext`, which
 * carries `ctx.waitUntil`, a request id and the route. The usage hook hands
 * its insert to `waitUntil` so the response is never delayed; without a
 * request context (dev server, scripts) the insert just floats. Nothing here
 * throws into the caller.
 */
import { AsyncLocalStorage } from "node:async_hooks";
import { getSupabaseAdminClient } from "../../lib/supabase.server";
import type { AiUsageEvent, AiUsageHook } from "./usage";

export interface AiRequestContext {
  waitUntil?: (promise: Promise<unknown>) => void;
  requestId?: string;
  job?: string;
}

const storage = new AsyncLocalStorage<AiRequestContext>();

export function runWithAiRequestContext<T>(context: AiRequestContext, fn: () => T): T {
  return storage.run(context, fn);
}

export function getAiRequestContext(): AiRequestContext | undefined {
  return storage.getStore();
}

export interface AiUsageRow {
  source: "web";
  stage: string;
  operation: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  latency_ms: number;
  attempts: number;
  ok: boolean;
  error: string | null;
  meeting_id: null;
  job: string | null;
  request_id: string | null;
}

export function toUsageRow(event: AiUsageEvent, context?: AiRequestContext): AiUsageRow {
  return {
    source: "web",
    stage: event.stage,
    operation: event.stage === "embedding" ? "embed" : "generate",
    model: event.model,
    input_tokens: event.inputTokens,
    output_tokens: event.outputTokens,
    latency_ms: Math.round(event.latencyMs),
    attempts: event.attempts,
    ok: event.ok,
    error: event.error ? event.error.slice(0, 2000) : null,
    meeting_id: null,
    job: context?.job?.slice(0, 200) ?? null,
    request_id: context?.requestId ?? null,
  };
}

type InsertRow = (row: AiUsageRow) => PromiseLike<{ error: { message: string } | null } | void>;

/** Build a hook that persists events. Exposed for tests; the app uses `persistUsageHook`. */
export function createPersistingUsageHook(
  insert: InsertRow,
  getContext: () => AiRequestContext | undefined = getAiRequestContext,
): AiUsageHook {
  return (event) => {
    let context: AiRequestContext | undefined;
    try {
      context = getContext();
      const pending = Promise.resolve()
        .then(() => insert(toUsageRow(event, context)))
        .then((result) => {
          if (result && result.error) console.warn("[ai] usage insert failed:", result.error.message);
        })
        .catch((err) => console.warn("[ai] usage insert failed:", (err as Error)?.message ?? err));
      context?.waitUntil?.(pending);
    } catch (err) {
      console.warn("[ai] usage logging skipped:", (err as Error)?.message ?? err);
    }
  };
}

function usageLoggingEnabled(): boolean {
  // Never write rows from unit tests (vitest sets VITEST; MODE is "test").
  if (import.meta.env?.MODE === "test" || (typeof process !== "undefined" && process.env?.VITEST)) return false;
  if ((process.env.AI_USAGE_LOGGING ?? "").toLowerCase() === "false") return false;
  return Boolean(
    (process.env.SUPABASE_URL || process.env.VITE_SUPABASE_URL) && process.env.SUPABASE_SECRET_KEY,
  );
}

const insertWithAdmin: InsertRow = (row) => getSupabaseAdminClient().from("ai_usage").insert(row);

/** The app's persisting hook, or null when logging is off / unconfigured. */
export function getPersistUsageHook(): AiUsageHook | null {
  return usageLoggingEnabled() ? createPersistingUsageHook(insertWithAdmin) : null;
}
