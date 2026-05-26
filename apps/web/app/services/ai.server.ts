import { GoogleGenAI } from "@google/genai";
import OpenAI from "openai";

export type AiProviderName = "gemini" | "openai";
export type AiScope = "rag" | "rerank" | "extraction" | "profile";

type GenerateOptions = {
  scope?: AiScope;
  model?: string;
  system?: string;
  prompt: string;
  json?: boolean;
};

type GenerateResult = {
  text: string;
  provider: AiProviderName;
  model: string;
  inputTokens: number;
  outputTokens: number;
};

type StreamOptions = Omit<GenerateOptions, "json">;

type StreamChunk =
  | { type: "text"; text: string }
  | { type: "usage"; inputTokens: number; outputTokens: number };

const DEFAULT_PROVIDER: AiProviderName = "gemini";
const DEFAULT_GEMINI_MODEL = "gemini-3-flash-preview";
const DEFAULT_OPENAI_MODEL = "gpt-5-mini";

const ENV: Record<string, string | undefined> = {
  GEMINI_API_KEY: process.env.GEMINI_API_KEY,
  GEMINI_MODEL: process.env.GEMINI_MODEL,
  OPENAI_API_KEY: process.env.OPENAI_API_KEY,
  OPENAI_MODEL: process.env.OPENAI_MODEL,
  AI_PROVIDER: process.env.AI_PROVIDER,
  AI_MODEL: process.env.AI_MODEL,
  RAG_AI_PROVIDER: process.env.RAG_AI_PROVIDER,
  RAG_AI_MODEL: process.env.RAG_AI_MODEL,
  RERANK_AI_PROVIDER: process.env.RERANK_AI_PROVIDER,
  RERANK_AI_MODEL: process.env.RERANK_AI_MODEL,
  EXTRACTION_AI_PROVIDER: process.env.EXTRACTION_AI_PROVIDER,
  EXTRACTION_AI_MODEL: process.env.EXTRACTION_AI_MODEL,
  PROFILE_AI_PROVIDER: process.env.PROFILE_AI_PROVIDER,
  PROFILE_AI_MODEL: process.env.PROFILE_AI_MODEL,
};

const SCOPE_PREFIX: Record<AiScope, string> = {
  rag: "RAG",
  rerank: "RERANK",
  extraction: "EXTRACTION",
  profile: "PROFILE",
};

let geminiClient: GoogleGenAI | null = null;
let openaiClient: OpenAI | null = null;

function readEnv(name: string): string | undefined {
  const value = ENV[name];
  return value && value.trim().length > 0 ? value.trim() : undefined;
}

function normalizeProvider(value?: string): AiProviderName {
  if (value?.toLowerCase() === "openai") return "openai";
  if (value?.toLowerCase() === "gemini") return "gemini";
  return DEFAULT_PROVIDER;
}

export function getAiConfig(scope: AiScope = "rag"): {
  provider: AiProviderName;
  model: string;
} {
  const prefix = SCOPE_PREFIX[scope];
  const provider = normalizeProvider(
    readEnv(`${prefix}_AI_PROVIDER`) || readEnv("AI_PROVIDER"),
  );
  const model =
    readEnv(`${prefix}_AI_MODEL`) ||
    readEnv("AI_MODEL") ||
    (provider === "gemini" ? readEnv("GEMINI_MODEL") : undefined) ||
    (provider === "openai" ? readEnv("OPENAI_MODEL") : undefined) ||
    (provider === "openai" ? DEFAULT_OPENAI_MODEL : DEFAULT_GEMINI_MODEL);

  return { provider, model };
}

export function isAiConfigured(scope: AiScope = "rag"): boolean {
  const { provider } = getAiConfig(scope);
  return provider === "openai" ? !!readEnv("OPENAI_API_KEY") : !!readEnv("GEMINI_API_KEY");
}

export function getAiProviderLabel(scope: AiScope = "rag"): string {
  const { provider } = getAiConfig(scope);
  return provider;
}

export function getAiModelLabel(scope: AiScope = "rag"): string {
  const { model } = getAiConfig(scope);
  return model;
}

function getGeminiClient(): GoogleGenAI {
  const apiKey = readEnv("GEMINI_API_KEY");
  if (!apiKey) throw new Error("GEMINI_API_KEY is not configured");
  if (!geminiClient) {
    geminiClient = new GoogleGenAI({ apiKey });
  }
  return geminiClient;
}

function getOpenAIClient(): OpenAI {
  const apiKey = readEnv("OPENAI_API_KEY");
  if (!apiKey) throw new Error("OPENAI_API_KEY is not configured");
  if (!openaiClient) {
    openaiClient = new OpenAI({ apiKey });
  }
  return openaiClient;
}

function buildInput(system: string | undefined, prompt: string) {
  return [
    ...(system
      ? [{ role: "system" as const, content: [{ type: "input_text" as const, text: system }] }]
      : []),
    { role: "user" as const, content: [{ type: "input_text" as const, text: prompt }] },
  ];
}

function cleanJsonText(text: string): string {
  return text
    .replace(/^```(?:json)?\s*\n?/i, "")
    .replace(/\n?```\s*$/, "")
    .trim();
}

export async function generateAiText(options: GenerateOptions): Promise<GenerateResult> {
  const config = getAiConfig(options.scope);
  const provider = config.provider;
  const model = options.model || config.model;

  if (provider === "openai") {
    const response = await getOpenAIClient().responses.create({
      model,
      input: buildInput(options.system, options.prompt),
      store: false,
    } as any);

    const usage = (response as any).usage || {};
    return {
      text: cleanJsonText((response as any).output_text || ""),
      provider,
      model,
      inputTokens: usage.input_tokens || 0,
      outputTokens: usage.output_tokens || 0,
    };
  }

  const response = await getGeminiClient().models.generateContent({
    model,
    contents: options.prompt,
    config: {
      ...(options.json ? { responseMimeType: "application/json" } : {}),
      ...(options.system ? { systemInstruction: options.system } : {}),
    },
  });

  return {
    text: cleanJsonText(response.text ?? ""),
    provider,
    model,
    inputTokens: response.usageMetadata?.promptTokenCount ?? 0,
    outputTokens: response.usageMetadata?.candidatesTokenCount ?? 0,
  };
}

export async function generateAiJson<T = unknown>(options: GenerateOptions): Promise<GenerateResult & { json: T }> {
  const result = await generateAiText({ ...options, json: true });
  return { ...result, json: JSON.parse(result.text) as T };
}

export async function* streamAiText(options: StreamOptions): AsyncGenerator<StreamChunk> {
  const config = getAiConfig(options.scope);
  const provider = config.provider;
  const model = options.model || config.model;

  if (provider === "openai") {
    const stream = getOpenAIClient().responses.stream({
      model,
      input: buildInput(options.system, options.prompt),
      store: false,
    } as any);

    for await (const event of stream as any) {
      if (event.type === "response.output_text.delta" && event.delta) {
        yield { type: "text", text: event.delta };
      }
    }

    const final = await stream.finalResponse();
    const usage = (final as any).usage || {};
    yield {
      type: "usage",
      inputTokens: usage.input_tokens || 0,
      outputTokens: usage.output_tokens || 0,
    };
    return;
  }

  const stream = await getGeminiClient().models.generateContentStream({
    model,
    contents: options.prompt,
    config: options.system ? { systemInstruction: options.system } : undefined,
  });

  for await (const chunk of stream) {
    if (chunk.text) {
      yield { type: "text", text: chunk.text };
    }
    if (chunk.usageMetadata) {
      yield {
        type: "usage",
        inputTokens: chunk.usageMetadata.promptTokenCount ?? 0,
        outputTokens: chunk.usageMetadata.candidatesTokenCount ?? 0,
      };
    }
  }
}
