import { AiError } from "./errors";
import { getAiRequestContext } from "./usage-sink.server";

/** Adapt the OpenAI SDK's JSON requests to an authenticated Worker binding.
 * Provider credentials never leave the gateway, and failures never fall back
 * to direct OpenAI calls (which would bypass its spend limit).
 */
export const gatewayFetch: typeof fetch = async (input, init) => {
  const request = new Request(input, init);
  const url = new URL(request.url);
  if (request.method !== "POST" || url.origin !== "https://api.openai.com" ||
      !["/v1/responses", "/v1/embeddings"].includes(url.pathname)) {
    throw new AiError("config", "Unsupported AI Gateway request");
  }
  const context = getAiRequestContext();
  if (!context?.gateway) {
    throw new AiError("config", "AI Gateway binding is unavailable; direct calls are disabled");
  }
  request.signal.throwIfAborted();
  const query: unknown = await request.json();
  const response = context.gateway.run({
    provider: "openai",
    endpoint: url.pathname.slice("/v1/".length),
    // Do not forward the SDK's Authorization header: BYOK only injects the
    // stored key when no provider Authorization header is supplied.
    headers: {
      "Content-Type": "application/json",
      "cf-aig-byok-alias": "default",
      "cf-aig-no-wholesale": "true",
      "cf-aig-max-attempts": "1",
      "cf-aig-metadata": JSON.stringify({ application: "langford", route: context.job, request_id: context.requestId }),
    },
    query,
  }, { extraHeaders: { "cf-aig-max-attempts": "1", "cf-aig-no-wholesale": "true" } });
  return withAbort(response, request.signal);
};

// The binding's run() has no signal parameter. Preserve the SDK's deadline and
// cancel its response reader on abort, including if headers arrive afterwards.
function withAbort(pending: Promise<Response>, signal: AbortSignal): Promise<Response> {
  return new Promise((resolve, reject) => {
    let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
    const onAbort = () => {
      reject(signal.reason);
      void reader?.cancel(signal.reason).catch(() => {});
    };
    const cleanup = () => signal.removeEventListener("abort", onAbort);
    signal.addEventListener("abort", onAbort, { once: true });
    if (signal.aborted) onAbort();
    pending.then((response) => {
      if (signal.aborted) {
        cleanup();
        void response.body?.cancel().catch(() => {});
        return;
      }
      if (!response.body) {
        cleanup();
        resolve(response);
        return;
      }
      reader = response.body.getReader();
      const body = new ReadableStream<Uint8Array>({
        async pull(controller) {
          try {
            signal.throwIfAborted();
            const chunk = await reader!.read();
            signal.throwIfAborted();
            if (chunk.done) {
              cleanup();
              controller.close();
            } else controller.enqueue(chunk.value);
          } catch (error) {
            cleanup();
            controller.error(error);
            void reader!.cancel(error).catch(() => {});
          }
        },
        cancel(reason) {
          cleanup();
          return reader!.cancel(reason);
        },
      });
      resolve(new Response(body, { status: response.status, statusText: response.statusText, headers: response.headers }));
    }, (error) => {
      cleanup();
      reject(error);
    });
  });
}
