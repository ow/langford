import { afterEach, describe, expect, it, vi } from "vitest";
import { createOpenAIProvider } from "~/services/ai/providers/openai.server";
import { gatewayFetch } from "~/services/ai/gateway.server";
import { runWithAiRequestContext } from "~/services/ai/usage-sink.server";
import { resolveAiConfig, isAiConfigured } from "~/services/ai/config.server";

const provider = () => createOpenAIProvider({ apiKey: "sdk-placeholder", fetch: gatewayFetch });
const signal = () => new AbortController().signal;
const responseBody = { id: "r1", object: "response", status: "completed", output: [{ type: "message", role: "assistant", content: [{ type: "output_text", text: "Verified", annotations: [] }] }], usage: { input_tokens: 2, output_tokens: 1 } };

afterEach(() => vi.unstubAllGlobals());

describe("AI Gateway transport", () => {
  it("uses stored provider credentials and the current request's binding for SDK calls", async () => {
    const first = vi.fn().mockResolvedValue(Response.json(responseBody));
    const second = vi.fn().mockResolvedValue(Response.json({ object: "list", data: [{ object: "embedding", index: 0, embedding: [0.1, 0.2] }], usage: { prompt_tokens: 1 } }));
    const sdk = provider();
    const result = await runWithAiRequestContext({ gateway: { run: first }, job: "/api/search" }, () => sdk.generate({ model: "m", system: "s", prompt: "p", signal: signal() }));
    expect(result.text).toBe("Verified");
    const embedding = await runWithAiRequestContext({ gateway: { run: second } }, () => sdk.embed({ model: "e", dimensions: 2, input: ["housing"], signal: signal() }));
    expect(embedding.vectors).toEqual([[0.1, 0.2]]);
    expect(first.mock.calls[0][0]).toMatchObject({ provider: "openai", endpoint: "responses", headers: { "cf-aig-no-wholesale": "true", "cf-aig-max-attempts": "1" } });
    expect(JSON.stringify(first.mock.calls)).not.toContain("sdk-placeholder");
    expect(Object.keys(first.mock.calls[0][0].headers).map((key) => key.toLowerCase())).not.toContain("authorization");
    expect(second.mock.calls[0][0].endpoint).toBe("embeddings");
  });

  it("preserves streaming answer events", async () => {
    const events = [
      { type: "response.output_text.delta", delta: "Hello" },
      { type: "response.completed", response: { usage: { input_tokens: 2, output_tokens: 1 } } },
    ].map((data) => `event: ${data.type}\ndata: ${JSON.stringify(data)}\n\n`).join("");
    const run = vi.fn().mockResolvedValue(new Response(events, { headers: { "Content-Type": "text/event-stream" } }));
    const chunks = await runWithAiRequestContext({ gateway: { run } }, async () => {
      const output = [];
      for await (const chunk of provider().stream({ model: "m", system: "s", prompt: "p", signal: signal() })) output.push(chunk);
      return output;
    });
    expect(chunks).toEqual([{ type: "text", text: "Hello" }, { type: "usage", inputTokens: 2, outputTokens: 1 }]);
  });

  it("does not bypass a rejected gateway or a missing binding", async () => {
    const direct = vi.fn();
    vi.stubGlobal("fetch", direct);
    const run = vi.fn().mockResolvedValue(Response.json({ error: { message: "Spend limit reached" } }, { status: 429 }));
    await expect(runWithAiRequestContext({ gateway: { run } }, () => provider().generate({ model: "m", system: "s", prompt: "p", signal: signal() }))).rejects.toMatchObject({ status: 429 });
    await expect(provider().generate({ model: "m", system: "s", prompt: "p", signal: signal() })).rejects.toMatchObject({ kind: "config" });
    expect(direct).not.toHaveBeenCalled();
  });

  it("honours cancellation while the binding is waiting for headers", async () => {
    const controller = new AbortController();
    const run = vi.fn(() => new Promise<Response>(() => {}));
    const pending = runWithAiRequestContext({ gateway: { run } }, () => gatewayFetch("https://api.openai.com/v1/responses", { method: "POST", body: "{}", signal: controller.signal }));
    await vi.waitFor(() => expect(run).toHaveBeenCalledOnce());
    controller.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  });

  it("supports gateway-only configuration without an OpenAI key in the Worker", () => {
    expect(isAiConfigured(resolveAiConfig({ AI_GATEWAY_ID: "configured" }))).toBe(true);
  });
});
