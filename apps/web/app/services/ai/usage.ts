import type { AiStage } from "./config.server";

/** One record per client call (after retries), success or failure. */
export interface AiUsageEvent {
  stage: AiStage | "embedding";
  provider: string;
  model: string;
  inputTokens: number;
  outputTokens: number;
  latencyMs: number;
  attempts: number;
  ok: boolean;
  error?: string;
}

export type AiUsageHook = (event: AiUsageEvent) => void;

export const consoleUsageHook: AiUsageHook = (event) => {
  console.debug(
    `[ai] ${event.stage} ${event.model} ${event.ok ? "ok" : "FAILED"} ` +
      `in=${event.inputTokens} out=${event.outputTokens} ${event.latencyMs}ms` +
      (event.attempts > 1 ? ` attempts=${event.attempts}` : "") +
      (event.error ? ` error=${event.error}` : ""),
  );
};

/** Collects usage for one request (e.g. an /api/search answer) so it can be reported in aggregate. */
export function createUsageCollector() {
  const events: AiUsageEvent[] = [];
  const hook: AiUsageHook = (event) => {
    events.push(event);
  };
  return {
    events,
    hook,
    totals() {
      let inputTokens = 0;
      let outputTokens = 0;
      let failedCalls = 0;
      for (const e of events) {
        inputTokens += e.inputTokens;
        outputTokens += e.outputTokens;
        if (!e.ok) failedCalls++;
      }
      return { inputTokens, outputTokens, calls: events.length, failedCalls };
    },
  };
}
