import OpenAI, {
  APIConnectionError,
  APIError,
  APIUserAbortError,
} from "openai";
import { AiError } from "../errors";
import type {
  EmbedRequest,
  Provider,
  ProviderRequest,
  ProviderResult,
  ProviderStreamChunk,
} from "./types";

export interface OpenAIProviderOptions {
  apiKey?: string;
  /** Injected in tests. */
  fetch?: typeof fetch;
  baseURL?: string;
}

/** OpenAI Responses API adapter. Retries/timeouts are owned by the client, so the SDK's are disabled. */
export function createOpenAIProvider(options: OpenAIProviderOptions): Provider {
  let client: OpenAI | null = null;
  const getClient = (): OpenAI => {
    if (!options.apiKey) {
      throw new AiError("config", "OPENAI_API_KEY is not configured");
    }
    if (!client) {
      client = new OpenAI({
        apiKey: options.apiKey,
        maxRetries: 0,
        // Our AbortSignal enforces the real deadline; this is only a backstop.
        timeout: 10 * 60_000,
        ...(options.fetch ? { fetch: options.fetch } : {}),
        ...(options.baseURL ? { baseURL: options.baseURL } : {}),
      });
    }
    return client;
  };

  function body(req: ProviderRequest) {
    return {
      model: req.model,
      instructions: req.system,
      input: req.prompt,
      store: false,
      ...(req.jsonSchema
        ? {
            text: {
              format: {
                type: "json_schema" as const,
                name: req.jsonSchema.name,
                schema: req.jsonSchema.schema,
                strict: true,
              },
            },
          }
        : {}),
    };
  }

  return {
    name: "openai",

    async generate(req): Promise<ProviderResult> {
      try {
        const response = await getClient().responses.create(body(req), { signal: req.signal });
        const refusal = findRefusal(response.output);
        if (refusal) throw new AiError("refusal", `Model refused: ${refusal}`);
        if (response.status === "incomplete") {
          throw new AiError(
            "incomplete",
            `Response incomplete: ${response.incomplete_details?.reason ?? "unknown reason"}`,
          );
        }
        if (response.status === "failed" || response.error) {
          throw new AiError("http", `Response failed: ${response.error?.message ?? "unknown error"}`, {
            status: 500,
          });
        }
        return {
          text: response.output_text ?? "",
          inputTokens: response.usage?.input_tokens ?? 0,
          outputTokens: response.usage?.output_tokens ?? 0,
        };
      } catch (err) {
        throw toAiError(err, req.signal);
      }
    },

    async *stream(req): AsyncIterable<ProviderStreamChunk> {
      let events;
      try {
        events = await getClient().responses.create({ ...body(req), stream: true }, { signal: req.signal });
      } catch (err) {
        throw toAiError(err, req.signal);
      }
      try {
        for await (const event of events) {
          switch (event.type) {
            case "response.output_text.delta":
              if (event.delta) yield { type: "text", text: event.delta };
              break;
            case "response.refusal.done":
              throw new AiError("refusal", `Model refused: ${event.refusal}`);
            case "response.completed":
            case "response.incomplete": {
              const usage = event.response.usage;
              yield {
                type: "usage",
                inputTokens: usage?.input_tokens ?? 0,
                outputTokens: usage?.output_tokens ?? 0,
              };
              if (event.type === "response.incomplete") {
                console.warn(
                  `[ai] stream incomplete: ${event.response.incomplete_details?.reason ?? "unknown"}`,
                );
              }
              break;
            }
            case "response.failed":
              throw new AiError(
                "http",
                `Response failed: ${event.response.error?.message ?? "unknown error"}`,
                { status: 500 },
              );
            case "error":
              throw new AiError("http", `Stream error: ${event.message}`, { status: 500 });
          }
        }
      } catch (err) {
        throw toAiError(err, req.signal);
      }
    },

    async embed(req: EmbedRequest) {
      try {
        const response = await getClient().embeddings.create(
          { model: req.model, input: req.input, dimensions: req.dimensions, encoding_format: "float" },
          { signal: req.signal },
        );
        const vectors = [...response.data]
          .sort((a, b) => a.index - b.index)
          .map((d) => d.embedding);
        return { vectors, inputTokens: response.usage?.prompt_tokens ?? 0 };
      } catch (err) {
        throw toAiError(err, req.signal);
      }
    },
  };
}

function findRefusal(output: unknown): string | null {
  if (!Array.isArray(output)) return null;
  for (const item of output as any[]) {
    for (const part of item?.content ?? []) {
      if (part?.type === "refusal") return String(part.refusal ?? "refused");
    }
  }
  return null;
}

/** Normalise SDK / fetch failures into AiError so the client's retry policy can classify them. */
export function toAiError(err: unknown, signal?: AbortSignal): AiError {
  if (err instanceof AiError) return err;
  if (err instanceof APIUserAbortError || signal?.aborted) {
    return new AiError("aborted", "Request aborted", { cause: err });
  }
  if (err instanceof APIConnectionError) {
    return new AiError("network", `Network error: ${err.message}`, { cause: err });
  }
  if (err instanceof APIError) {
    const retryAfter = Number(err.headers?.get?.("retry-after"));
    return new AiError("http", `OpenAI ${err.status ?? "?"}: ${err.message}`, {
      status: err.status,
      retryAfterSeconds: Number.isFinite(retryAfter) ? retryAfter : undefined,
      cause: err,
    });
  }
  if (err instanceof TypeError) {
    // fetch() rejects with TypeError on network failures.
    return new AiError("network", `Network error: ${err.message}`, { cause: err });
  }
  const message = err instanceof Error ? err.message : String(err);
  return new AiError("http", message, { cause: err });
}
