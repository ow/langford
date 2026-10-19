import { describe, expect, it, vi } from "vitest";
import { estimateCostUsd, priceFor } from "../../app/services/ai/pricing";
import {
  createPersistingUsageHook,
  getAiRequestContext,
  getPersistUsageHook,
  runWithAiRequestContext,
  toUsageRow,
} from "../../app/services/ai/usage-sink.server";
import type { AiUsageEvent } from "../../app/services/ai/usage";
import { summarizeUsage, type AiUsageSummaryRow } from "../../app/services/ai-usage";
import { getAiUsageDashboard } from "../../app/services/ai-usage-admin.server";

const event = (overrides: Partial<AiUsageEvent> = {}): AiUsageEvent => ({
  stage: "answer",
  provider: "openai",
  model: "gpt-6-luna",
  inputTokens: 1200,
  outputTokens: 300,
  latencyMs: 812.6,
  attempts: 1,
  ok: true,
  ...overrides,
});

describe("pricing", () => {
  it("prices the Decisions API by input tokens only", () => {
    expect(priceFor("gpt-6-luna", "decide")).toEqual({ inputPerM: 0.1, outputPerM: 0 });
    expect(estimateCostUsd("gpt-6-luna", "decide", 2_000_000, 999_999)).toBeCloseTo(0.2);
  });

  it("prices embeddings and returns null for unknown models", () => {
    expect(estimateCostUsd("text-embedding-3-small", "embed", 1_000_000, 0)).toBeCloseTo(0.02);
    expect(estimateCostUsd("mystery-model", "text", 10, 10)).toBeNull();
  });
});

describe("usage sink", () => {
  it("builds a web row with request context", () => {
    const row = toUsageRow(event({ ok: false, error: "boom" }), { requestId: "ray-1", job: "/api/search" });
    expect(row).toMatchObject({
      source: "web",
      stage: "answer",
      operation: "generate",
      model: "gpt-6-luna",
      input_tokens: 1200,
      output_tokens: 300,
      latency_ms: 813,
      ok: false,
      error: "boom",
      job: "/api/search",
      request_id: "ray-1",
    });
    expect(toUsageRow(event({ stage: "embedding" })).operation).toBe("embed");
  });

  it("hands the insert to waitUntil and returns synchronously", async () => {
    const insert = vi.fn().mockResolvedValue({ error: null });
    const waitUntil = vi.fn();
    const hook = createPersistingUsageHook(insert, () => ({ waitUntil, requestId: "r", job: "/x" }));
    const result = hook(event());
    expect(result).toBeUndefined();
    expect(waitUntil).toHaveBeenCalledTimes(1);
    await waitUntil.mock.calls[0][0];
    expect(insert).toHaveBeenCalledWith(expect.objectContaining({ request_id: "r", job: "/x" }));
  });

  it("never throws when the insert fails or rejects", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const waitUntil = vi.fn();
    const rejecting = createPersistingUsageHook(() => Promise.reject(new Error("db down")), () => ({ waitUntil }));
    const erroring = createPersistingUsageHook(async () => ({ error: { message: "no table" } }), () => ({ waitUntil }));
    const throwing = createPersistingUsageHook(() => {
      throw new Error("sync throw");
    }, () => undefined);
    expect(() => rejecting(event())).not.toThrow();
    expect(() => erroring(event())).not.toThrow();
    expect(() => throwing(event())).not.toThrow();
    await Promise.all(waitUntil.mock.calls.map((c) => c[0]));
    await new Promise((r) => setTimeout(r, 0));
    expect(warn).toHaveBeenCalled();
    warn.mockRestore();
  });

  it("carries request context through async work", async () => {
    const seen = await runWithAiRequestContext({ requestId: "abc", job: "/api/ask" }, async () => {
      await new Promise((r) => setTimeout(r, 1));
      return getAiRequestContext();
    });
    expect(seen).toMatchObject({ requestId: "abc", job: "/api/ask" });
    expect(getAiRequestContext()).toBeUndefined();
  });

  it("is disabled under tests so unit runs never write rows", () => {
    expect(getPersistUsageHook()).toBeNull();
  });
});

describe("admin rollup", () => {
  const rows: AiUsageSummaryRow[] = [
    {
      source: "pipeline",
      stage: "decisions",
      calls: 10,
      failures: 1,
      input_tokens: 1_000_000,
      output_tokens: 5_000,
      p50_latency_ms: 400,
      p95_latency_ms: 1200,
      by_model: [{ model: "gpt-6-luna", operation: "decide", calls: 10, input_tokens: 1_000_000, output_tokens: 5_000 }],
    },
    {
      source: "web",
      stage: "embedding",
      calls: 4,
      failures: 0,
      input_tokens: 2_000_000,
      output_tokens: 0,
      p50_latency_ms: 90,
      p95_latency_ms: 150,
      by_model: [
        { model: "text-embedding-3-small", operation: "embed", calls: 3, input_tokens: 1_000_000, output_tokens: 0 },
        { model: "unpriced", operation: "embed", calls: 1, input_tokens: 1_000_000, output_tokens: 0 },
      ],
    },
  ];

  it("estimates cost per stage at read time and totals the window", () => {
    const w = summarizeUsage(7, rows);
    const decisions = w.stages.find((s) => s.stage === "decisions")!;
    expect(decisions.costUsd).toBeCloseTo(0.1);
    expect(decisions.costPartial).toBe(false);
    const embedding = w.stages.find((s) => s.stage === "embedding")!;
    expect(embedding.costUsd).toBeCloseTo(0.02);
    expect(embedding.costPartial).toBe(true);
    expect(w.totals).toMatchObject({ calls: 14, failures: 1, inputTokens: 3_000_000 });
    expect(w.totals.costUsd).toBeCloseTo(0.12);
  });

  it("loads windows and failures, and degrades when the table is missing", async () => {
    const rpc = vi.fn().mockResolvedValue({ data: rows, error: null });
    const failures = [{ id: 1, created_at: "2026-10-19T00:00:00Z", source: "web", stage: "answer", model: "gpt-6-luna", job: "/api/search", meeting_id: null, error: "timeout" }];
    const query: any = {
      select: vi.fn(() => query),
      eq: vi.fn(() => query),
      order: vi.fn(() => query),
      limit: vi.fn().mockResolvedValue({ data: failures, error: null }),
    };
    const supabase: any = { rpc, from: vi.fn(() => query) };
    const now = new Date("2026-10-19T12:00:00Z");
    const dash = await getAiUsageDashboard(supabase, { now });
    expect(dash.available).toBe(true);
    expect(dash.windows.map((w) => w.days)).toEqual([7, 30]);
    expect(rpc).toHaveBeenCalledWith("ai_usage_summary", { since: "2026-10-12T12:00:00.000Z" });
    expect(query.eq).toHaveBeenCalledWith("ok", false);
    expect(query.limit).toHaveBeenCalledWith(20);
    expect(dash.failures).toEqual(failures);

    const broken: any = {
      rpc: vi.fn().mockResolvedValue({ data: null, error: { message: "relation ai_usage does not exist" } }),
      from: vi.fn(() => query),
    };
    const down = await getAiUsageDashboard(broken);
    expect(down).toMatchObject({ available: false, error: "relation ai_usage does not exist" });
  });
});
