import type { AiStage } from "./config.server";

export type AiErrorKind =
  | "config" // missing key / unsupported provider
  | "timeout" // our per-attempt deadline elapsed
  | "aborted" // caller cancelled
  | "network" // connection failure
  | "http" // non-2xx from the provider
  | "refusal" // model refused
  | "incomplete" // output truncated (max tokens, content filter)
  | "schema"; // output didn't match the requested JSON schema

export class AiError extends Error {
  readonly kind: AiErrorKind;
  readonly stage?: AiStage | "embedding";
  readonly model?: string;
  readonly status?: number;
  readonly attempts?: number;
  /** Seconds the provider asked us to wait (Retry-After), if any. */
  readonly retryAfterSeconds?: number;
  /** Tokens spent before the failure (e.g. output that failed schema validation). */
  readonly usage?: { inputTokens: number; outputTokens: number };

  constructor(
    kind: AiErrorKind,
    message: string,
    opts: {
      stage?: AiStage | "embedding";
      model?: string;
      status?: number;
      attempts?: number;
      retryAfterSeconds?: number;
      usage?: { inputTokens: number; outputTokens: number };
      cause?: unknown;
    } = {},
  ) {
    super(message, opts.cause !== undefined ? { cause: opts.cause } : undefined);
    this.name = "AiError";
    this.kind = kind;
    this.stage = opts.stage;
    this.model = opts.model;
    this.status = opts.status;
    this.attempts = opts.attempts;
    this.retryAfterSeconds = opts.retryAfterSeconds;
    this.usage = opts.usage;
  }

  /** 408/429/5xx, network failures and our own timeouts are worth retrying. */
  get retryable(): boolean {
    if (this.kind === "timeout" || this.kind === "network") return true;
    if (this.kind === "http" && this.status !== undefined) {
      return this.status === 408 || this.status === 429 || this.status >= 500;
    }
    return false;
  }

  /** Copy with call context filled in (stage/model/attempts). */
  withContext(ctx: { stage?: AiStage | "embedding"; model?: string; attempts?: number }): AiError {
    return new AiError(this.kind, this.message, {
      stage: ctx.stage ?? this.stage,
      model: ctx.model ?? this.model,
      status: this.status,
      attempts: ctx.attempts ?? this.attempts,
      retryAfterSeconds: this.retryAfterSeconds,
      usage: this.usage,
      cause: this.cause,
    });
  }
}

export function isAiError(err: unknown): err is AiError {
  return err instanceof AiError;
}
