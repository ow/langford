import { useEffect } from "react";
import {
  Form,
  redirect,
  useActionData,
  useNavigation,
  useRevalidator,
} from "react-router";
import type { ReactNode } from "react";
import type { Route } from "./+types/admin-pipeline-job";
import { requireAdmin } from "../lib/auth.server";
import { getSupabaseAdminClient } from "../lib/supabase.server";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { DetailHeader } from "../components/ui/detail-header";
import { cn, formatDate, formatRelativeTime } from "../lib/utils";
import {
  cancelPipelineJob,
  getPipelineJobDetail,
  retryPipelineJob,
} from "../services/pipeline-admin.server";

export async function loader({ request, params }: Route.LoaderArgs) {
  await requireAdmin(request);
  const supabase = getSupabaseAdminClient();
  return getPipelineJobDetail(supabase, params.id);
}

export async function action({ request, params }: Route.ActionArgs) {
  const user = await requireAdmin(request);
  const supabase = getSupabaseAdminClient();
  const formData = await request.formData();
  const intent = formData.get("intent");

  try {
    if (intent === "cancel") {
      await cancelPipelineJob(supabase, params.id);
      return { success: "Job cancelled." };
    }
    if (intent === "retry") {
      const newJob = await retryPipelineJob(
        supabase,
        params.id,
        user.email || user.id,
      );
      throw redirect(`/admin/pipeline/jobs/${newJob.id}`);
    }
    return { error: "Unsupported action." };
  } catch (error: any) {
    if (error instanceof Response) throw error;
    return { error: error.message || "Job action failed." };
  }
}

type BadgeTone = "success" | "danger" | "warning" | "muted" | "brand";

const statusTones: Record<string, BadgeTone> = {
  succeeded: "success",
  completed: "success",
  failed: "danger",
  running: "warning",
  queued: "warning",
  cancelled: "muted",
  ingested: "brand",
  extracted: "brand",
  diarized: "brand",
};

const levelTones: Record<string, BadgeTone> = {
  error: "danger",
  warning: "warning",
};

function sentence(value: string) {
  const text = value.replaceAll("_", " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function StatusBadge({ status }: { status: string }) {
  return (
    <Badge variant={statusTones[status] ?? "muted"}>{sentence(status)}</Badge>
  );
}

const card = "rounded-2xl border border-zinc-200 bg-white shadow-sm";
const logPanel =
  "overflow-auto rounded-xl border border-zinc-200 bg-zinc-50 p-3 font-mono text-xs leading-relaxed text-zinc-800";

function JsonBlock({ value, className }: { value: unknown; className?: string }) {
  return (
    <pre className={cn(logPanel, "max-h-80", className)}>
      {JSON.stringify(value || {}, null, 2)}
    </pre>
  );
}

function SectionTitle({
  title,
  description,
}: {
  title: string;
  description?: string;
}) {
  return (
    <div className="mb-3">
      <h2 className="text-lg font-semibold text-zinc-900">{title}</h2>
      {description && <p className="text-sm text-zinc-500">{description}</p>}
    </div>
  );
}

function EmptyNote({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-2xl border border-dashed border-zinc-300 bg-white/60 p-5 text-sm text-zinc-500">
      {children}
    </div>
  );
}

function jobLifecycleSummary(job: any) {
  if (job.status === "running" && job.started_at) {
    return `Started ${formatRelativeTime(job.started_at)}`;
  }
  if (job.status === "queued" && job.requested_at) {
    return `Queued ${formatRelativeTime(job.requested_at)}`;
  }
  if (
    ["succeeded", "failed", "cancelled"].includes(job.status) &&
    job.finished_at
  ) {
    return `Finished ${formatRelativeTime(job.finished_at)}`;
  }
  if (job.requested_at) {
    return `Requested ${formatRelativeTime(job.requested_at)}`;
  }
  return "Time unavailable";
}

function isStreamEvent(event: any) {
  return event.data?.stream === "info" || event.data?.stream === "warning";
}

function TerminalLog({ events }: { events: any[] }) {
  if (events.length === 0) {
    return (
      <EmptyNote>No terminal output has been recorded for this job yet.</EmptyNote>
    );
  }

  return (
    <div
      role="log"
      aria-label="Terminal output"
      tabIndex={0}
      className={cn(logPanel, "max-h-[560px] whitespace-pre")}
    >
      {events.map((event) => {
        const timestamp = new Date(event.created_at).toLocaleTimeString();
        const isStderr = event.level === "warning";
        return (
          <div key={event.id} className={cn(isStderr && "text-amber-800")}>
            <span className="text-zinc-400">[{timestamp}]</span>{" "}
            <span className={isStderr ? "text-amber-600" : "text-zinc-400"}>
              {isStderr ? "stderr" : "stdout"}&gt;
            </span>{" "}
            {event.message}
          </div>
        );
      })}
    </div>
  );
}

function MetaRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[96px_minmax(0,1fr)] gap-3 px-4 py-2.5 text-sm">
      <dt className="text-zinc-500">{label}</dt>
      <dd className="min-w-0 text-zinc-900">{children}</dd>
    </div>
  );
}

export default function AdminPipelineJob({ loaderData }: Route.ComponentProps) {
  const { job, events, sourceMeeting } = loaderData;
  const actionData = useActionData<typeof action>();
  const navigation = useNavigation();
  const revalidator = useRevalidator();
  const isSubmitting = navigation.state === "submitting";
  const canCancel = job.status === "queued";
  const canRetry = ["failed", "cancelled", "succeeded"].includes(job.status);
  const isActive = ["queued", "running"].includes(job.status);
  const heartbeatAgeMs = job.locked_at
    ? Date.now() - new Date(job.locked_at).getTime()
    : null;
  const heartbeatState =
    job.status !== "running"
      ? "Not running"
      : heartbeatAgeMs != null && heartbeatAgeMs < 90_000
        ? "Alive"
        : "Stale";
  const heartbeatTone: BadgeTone =
    heartbeatState === "Alive"
      ? "success"
      : heartbeatState === "Stale"
        ? "danger"
        : "muted";
  const streamEvents = events.filter(isStreamEvent);
  const lifecycleEvents = events.filter((event: any) => !isStreamEvent(event));

  useEffect(() => {
    if (!isActive) return;
    const id = window.setInterval(() => revalidator.revalidate(), 5000);
    return () => window.clearInterval(id);
  }, [isActive, revalidator]);

  return (
    <div className="min-h-screen bg-zinc-50">
      <div className="container mx-auto max-w-6xl px-4 py-12">
        <DetailHeader
          back={{ to: "/admin/pipeline", label: "Pipeline" }}
          meta={[
            <span key="id" className="tabular-nums">
              Job #{job.id}
            </span>,
            <span key="when">
              {jobLifecycleSummary(job)}
              {job.requested_by ? ` by ${job.requested_by}` : ""}
            </span>,
          ]}
          title={sentence(job.job_type)}
          badges={<StatusBadge status={job.status} />}
          actions={
            (canCancel || canRetry) && (
              <>
                {canCancel && (
                  <Form method="post">
                    <Button
                      type="submit"
                      name="intent"
                      value="cancel"
                      variant="outline"
                      disabled={isSubmitting}
                    >
                      Cancel job
                    </Button>
                  </Form>
                )}
                {canRetry && (
                  <Form method="post">
                    <Button
                      type="submit"
                      name="intent"
                      value="retry"
                      disabled={isSubmitting}
                    >
                      Requeue
                    </Button>
                  </Form>
                )}
              </>
            )
          }
        />

        {actionData?.success && (
          <p
            role="status"
            className="mb-6 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-sm text-emerald-800"
          >
            {actionData.success}
          </p>
        )}
        {actionData?.error && (
          <p
            role="alert"
            className="mb-6 rounded-xl border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-800"
          >
            {actionData.error}
          </p>
        )}

        {job.last_error && (
          <div className="mb-8 rounded-2xl border border-red-200 bg-red-50 p-4">
            <div className="text-sm font-medium text-red-800">Last error</div>
            <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-red-800">
              {job.last_error}
            </pre>
          </div>
        )}

        <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_340px]">
          <div className="min-w-0 space-y-8">
            <section>
              <SectionTitle
                title="Terminal log"
                description="Worker stdout and stderr, oldest first."
              />
              <TerminalLog events={streamEvents} />
            </section>

            <section>
              <SectionTitle
                title="Job events"
                description="Structured lifecycle events and payloads."
              />
              {lifecycleEvents.length === 0 ? (
                <EmptyNote>
                  No lifecycle events have been recorded for this job yet.
                </EmptyNote>
              ) : (
                <ul className={cn(card, "divide-y divide-zinc-100")}>
                  {lifecycleEvents.map((event: any) => {
                    const hasData =
                      event.data && Object.keys(event.data).length > 0;
                    return (
                      <li key={event.id} className="px-4 py-3">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0 text-sm font-medium text-zinc-900">
                            {event.message}
                          </div>
                          <Badge variant={levelTones[event.level] ?? "muted"}>
                            {sentence(event.level || "info")}
                          </Badge>
                        </div>
                        <div className="mt-0.5 text-xs tabular-nums text-zinc-500">
                          {new Date(event.created_at).toLocaleString()}
                        </div>
                        {hasData && (
                          <details className="group mt-2">
                            <summary className="cursor-pointer text-xs font-medium text-zinc-500 hover:text-brand-700">
                              <span className="group-open:hidden">Show data</span>
                              <span className="hidden group-open:inline">
                                Hide data
                              </span>
                            </summary>
                            <JsonBlock value={event.data} className="mt-2" />
                          </details>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
            </section>

            <section>
              <SectionTitle
                title="Result"
                description="Final payload written by the worker."
              />
              {job.result && Object.keys(job.result).length > 0 ? (
                <JsonBlock value={job.result} className="max-h-96" />
              ) : (
                <EmptyNote>
                  {isActive
                    ? "No result yet. The worker writes one when the job finishes."
                    : "This job did not record a result payload."}
                </EmptyNote>
              )}
            </section>
          </div>

          <aside className="min-w-0 space-y-8">
            <section>
              <SectionTitle title="Details" />
              <dl className={cn(card, "divide-y divide-zinc-100")}>
                <MetaRow label="Attempts">
                  <span className="tabular-nums">
                    {job.attempt_count} / {job.max_attempts}
                  </span>
                </MetaRow>
                <MetaRow label="Worker">
                  <span className="break-all">{job.locked_by || "None"}</span>
                </MetaRow>
                <MetaRow label="Heartbeat">
                  <span className="flex flex-wrap items-center gap-2">
                    <Badge variant={heartbeatTone}>{heartbeatState}</Badge>
                    {job.locked_at && (
                      <span className="text-xs text-zinc-500">
                        {formatRelativeTime(job.locked_at)}
                      </span>
                    )}
                  </span>
                </MetaRow>
                <MetaRow label="Started">
                  <span className="tabular-nums">
                    {job.started_at
                      ? new Date(job.started_at).toLocaleString()
                      : "Not started"}
                  </span>
                </MetaRow>
                <MetaRow label="Finished">
                  <span className="tabular-nums">
                    {job.finished_at
                      ? new Date(job.finished_at).toLocaleString()
                      : "Not finished"}
                  </span>
                </MetaRow>
                <div className="px-4 py-3">
                  <dt className="mb-1.5 text-sm text-zinc-500">Arguments</dt>
                  <dd>
                    <JsonBlock value={job.args} className="max-h-60" />
                  </dd>
                </div>
              </dl>
            </section>

            {sourceMeeting && (
              <section>
                <SectionTitle title="Source meeting" />
                <div className={cn(card, "space-y-2 p-4 text-sm")}>
                  <div className="font-medium text-zinc-900">
                    {sourceMeeting.title}
                  </div>
                  <div className="flex flex-wrap items-center gap-2 text-zinc-500">
                    <span className="tabular-nums">
                      {formatDate(sourceMeeting.meeting_date)}
                    </span>
                    <StatusBadge status={sourceMeeting.status} />
                  </div>
                  <div className="break-all font-mono text-xs text-zinc-500">
                    {sourceMeeting.archive_path || "No archive path"}
                  </div>
                </div>
              </section>
            )}
          </aside>
        </div>
      </div>
    </div>
  );
}
