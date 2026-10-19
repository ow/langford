import type { JsonSchema } from "../schema";

/**
 * The tiny adapter surface a model provider implements. The client owns retries,
 * timeouts, house rules, schema validation and usage reporting; providers just
 * translate one request and normalise failures into `AiError`s.
 */
export interface ProviderRequest {
  model: string;
  /** Already includes house rules. */
  system: string;
  prompt: string;
  signal: AbortSignal;
  /** When set, the provider must enforce this JSON Schema on the output. */
  jsonSchema?: { name: string; schema: JsonSchema };
}

export interface ProviderResult {
  text: string;
  inputTokens: number;
  outputTokens: number;
}

export type ProviderStreamChunk =
  | { type: "text"; text: string }
  | { type: "usage"; inputTokens: number; outputTokens: number };

export interface EmbedRequest {
  model: string;
  dimensions: number;
  input: string[];
  signal: AbortSignal;
}

export interface Provider {
  readonly name: string;
  generate(req: ProviderRequest): Promise<ProviderResult>;
  stream(req: ProviderRequest): AsyncIterable<ProviderStreamChunk>;
  embed(req: EmbedRequest): Promise<{ vectors: number[][]; inputTokens: number }>;
}
