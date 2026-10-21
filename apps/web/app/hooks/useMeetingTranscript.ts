import { useEffect, useState } from "react";

/** Timings stay available immediately; download words only for an explicit text/playback need. */
export function useMeetingTranscript(meetingId: number, hasTranscript: boolean, enabled: boolean) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<{
    meetingId: number;
    status: "loading" | "ready" | "error";
    texts: Record<number, string> | null;
  } | null>(null);
  const current = state?.meetingId === meetingId ? state : null;
  useEffect(() => {
    if (!enabled || !hasTranscript) return;
    const controller = new AbortController();
    setState({ meetingId, status: "loading", texts: null });
    fetch(`/api/meeting-text?meeting=${meetingId}&kind=transcript`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error("Transcript unavailable");
        const data = await response.json() as { texts?: unknown };
        if (!data.texts || typeof data.texts !== "object" || Array.isArray(data.texts) || Object.values(data.texts).some((text) => typeof text !== "string")) throw new Error("Invalid transcript");
        if (!controller.signal.aborted) setState({ meetingId, status: "ready", texts: data.texts as Record<number, string> });
      })
      .catch(() => {
        if (!controller.signal.aborted) setState({ meetingId, status: "error", texts: null });
      });
    return () => controller.abort();
  }, [meetingId, hasTranscript, enabled, attempt]);
  return {
    texts: current?.texts ?? null,
    status: current?.status ?? "idle" as const,
    retry: () => setAttempt((value) => value + 1),
  };
}
