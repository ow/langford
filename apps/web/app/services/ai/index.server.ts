/**
 * The web app's single model client. Import from here, not from providers.
 *
 *   const ai = getAiClient();
 *   await ai.text({ stage: "agent", system, prompt });
 *   await ai.json({ stage: "rerank", prompt, schema, schemaName: "rerank_scores" });
 *   for await (const chunk of ai.stream({ stage: "answer", system, prompt })) ...
 *   await embedQuery("tree bylaw");
 */
export {
  createAiClient,
  embedQuery,
  getAiClient,
  isVectorSearchAvailable,
  setAiClientForTesting,
  type AiCallOptions,
  type AiClient,
  type AiJsonOptions,
  type AiStreamChunk,
  type AiTextResult,
} from "./client.server";
export {
  getAiConfig,
  getStageConfig,
  isAiConfigured,
  resolveAiConfig,
  type AiConfig,
  type AiStage,
} from "./config.server";
export { AiError, isAiError, type AiErrorKind } from "./errors";
export { HOUSE_RULES, withHouseRules } from "./house-rules";
export { createUsageCollector, type AiUsageEvent, type AiUsageHook } from "./usage";
