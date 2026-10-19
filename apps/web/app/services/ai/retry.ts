import type { AiError } from "./errors";

export interface RetryPolicy {
  /** Total attempts including the first. */
  maxAttempts: number;
  baseDelayMs: number;
  maxDelayMs: number;
}

/** The one retry policy for every model call: 429/5xx/network/timeout, exponential backoff, 3 attempts. */
export const DEFAULT_RETRY_POLICY: RetryPolicy = {
  maxAttempts: 3,
  baseDelayMs: 400,
  maxDelayMs: 8_000,
};

export type Sleep = (ms: number, signal?: AbortSignal) => Promise<void>;

export const defaultSleep: Sleep = (ms, signal) =>
  new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(signal.reason);
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        reject(signal.reason);
      },
      { once: true },
    );
  });

/** Exponential backoff with jitter; honours Retry-After when the provider sends it. */
export function backoffDelay(attempt: number, policy: RetryPolicy, err?: AiError): number {
  if (err?.retryAfterSeconds && err.retryAfterSeconds > 0) {
    return Math.min(err.retryAfterSeconds * 1000, policy.maxDelayMs);
  }
  const exp = policy.baseDelayMs * 2 ** (attempt - 1);
  const jitter = Math.random() * policy.baseDelayMs;
  return Math.min(exp + jitter, policy.maxDelayMs);
}

/** A signal that fires on the caller's abort or after `timeoutMs`, whichever is first. */
export function deadlineSignal(
  timeoutMs: number,
  outer?: AbortSignal,
): { signal: AbortSignal; timedOut: () => boolean; dispose: () => void } {
  const controller = new AbortController();
  let didTimeout = false;
  const timer = setTimeout(() => {
    didTimeout = true;
    controller.abort(new Error(`Timed out after ${timeoutMs}ms`));
  }, timeoutMs);
  const onAbort = () => controller.abort(outer?.reason);
  if (outer) {
    if (outer.aborted) onAbort();
    else outer.addEventListener("abort", onAbort, { once: true });
  }
  return {
    signal: controller.signal,
    timedOut: () => didTimeout,
    dispose: () => {
      clearTimeout(timer);
      outer?.removeEventListener("abort", onAbort);
    },
  };
}
