import { useEffect } from "react";
import {
  Form,
  Link,
  redirect,
  useActionData,
  useNavigation,
  useRevalidator,
} from "react-router";
import {
  ArrowLeft,
  Calendar,
  Clock,
  CopyPlus,
  FileText,
  RadioTower,
  StopCircle,
  Terminal,
} from "lucide-react";
import type { Route } from "./+types/admin-pipeline-job";
import { requireAdmin } from "../lib/auth.server";
import { getSupabaseAdminClient } from "../lib/supabase.server";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "../components/ui/card";
import { formatDate, formatRelativeTime } from "../lib/utils";
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

function StatusBadge({ status }: { status: string }) {
  const classes: Record<string, string> = {
    queued: "border-amber-200 bg-amber-50 text-amber-800",
    running: "border-blue-200 bg-blue-50 text-blue-800",
    succeeded: "border-emerald-200 bg-emerald-50 text-emerald-800",
    failed: "border-red-200 bg-red-50 text-red-800",
    cancelled: "border-zinc-200 bg-zinc-50 text-zinc-700",
  };

  return (
    <Badge variant="outline" className={classes[status] || "border-zinc-200"}>
      {status.replaceAll("_", " ")}
    </Badge>
  );
}

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="max-h-96 overflow-auto rounded-lg border border-zinc-200 bg-zinc-950 p-4 text-xs leading-relaxed text-zinc-100">
      {JSON.stringify(value || {}, null, 2)}
    </pre>
  );
}

function isStreamEvent(event: any) {
  return event.data?.stream === "info" || event.data?.stream === "warning";
}

function TerminalLog({ events }: { events: any[] }) {
  if (events.length === 0) {
    return (
      <p className="text-sm text-zinc-500">
        No terminal output has been recorded for this job yet.
      </p>
    );
  }

  return (
    <pre className="max-h-[560px] overflow-auto rounded-lg border border-zinc-800 bg-zinc-950 p-4 font-mono text-xs leading-relaxed text-zinc-100">
      {events
        .map((event) => {
          const timestamp = new Date(event.created_at).toLocaleTimeString();
          const prefix = event.level === "warning" ? "stderr" : "stdout";
          return `[${timestamp}] ${prefix}> ${event.message}`;
        })
        .join("\n")}
    </pre>
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
  const streamEvents = events.filter(isStreamEvent);
  const lifecycleEvents = events.filter((event: any) => !isStreamEvent(event));

  useEffect(() => {
    if (!isActive) return;
    const id = window.setInterval(() => revalidator.revalidate(), 5000);
    return () => window.clearInterval(id);
  }, [isActive, revalidator]);

  return (
    <div className="container mx-auto max-w-6xl px-4 py-8">
      <div className="mb-6">
        <Button asChild variant="ghost" className="-ml-3">
          <Link to="/admin/pipeline">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Pipeline dashboard
          </Link>
        </Button>
      </div>

      <div className="mb-8 flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="mb-2 flex items-center gap-2">
            <StatusBadge status={job.status} />
            <span className="text-sm text-zinc-500">Job #{job.id}</span>
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-zinc-950">
            {job.job_type.replaceAll("_", " ")}
          </h1>
          <p className="mt-2 text-sm text-zinc-600">
            Requested {formatRelativeTime(job.requested_at)}
            {job.requested_by ? ` by ${job.requested_by}` : ""}.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          {canCancel && (
            <Form method="post">
              <Button
                type="submit"
                name="intent"
                value="cancel"
                variant="outline"
                disabled={isSubmitting}
              >
                <StopCircle className="mr-2 h-4 w-4" />
                Cancel
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
                <CopyPlus className="mr-2 h-4 w-4" />
                Requeue
              </Button>
            </Form>
          )}
        </div>
      </div>

      {actionData?.success && (
        <div className="mb-6 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          {actionData.success}
        </div>
      )}
      {actionData?.error && (
        <div className="mb-6 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          {actionData.error}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Terminal className="h-5 w-5" />
                Terminal log
              </CardTitle>
              <CardDescription>
                Worker stdout/stderr, ordered oldest first.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <TerminalLog events={streamEvents} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Job events</CardTitle>
              <CardDescription>
                Structured lifecycle events and result payloads.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {lifecycleEvents.map((event: any) => (
                  <div
                    key={event.id}
                    className="rounded-lg border border-zinc-200 p-4"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="font-medium text-zinc-950">
                        {event.message}
                      </div>
                      <Badge variant="outline">{event.level}</Badge>
                    </div>
                    <div className="mt-1 flex items-center gap-2 text-xs text-zinc-500">
                      <Clock className="h-3.5 w-3.5" />
                      {new Date(event.created_at).toLocaleString()}
                    </div>
                    {event.data && Object.keys(event.data).length > 0 && (
                      <div className="mt-3">
                        <JsonBlock value={event.data} />
                      </div>
                    )}
                  </div>
                ))}
                {lifecycleEvents.length === 0 && (
                  <p className="text-sm text-zinc-500">
                    No lifecycle events have been recorded for this job yet.
                  </p>
                )}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Result</CardTitle>
              <CardDescription>
                Final result payload written by the worker.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <JsonBlock value={job.result} />
              {job.last_error && (
                <div className="mt-4 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
                  {job.last_error}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Job metadata</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              <div>
                <div className="text-xs font-medium uppercase tracking-wide text-zinc-500">
                  Attempts
                </div>
                <div className="mt-1">
                  {job.attempt_count} / {job.max_attempts}
                </div>
              </div>
              <div>
                <div className="text-xs font-medium uppercase tracking-wide text-zinc-500">
                  Worker
                </div>
                <div className="mt-1">{job.locked_by || "None"}</div>
              </div>
              <div>
                <div className="text-xs font-medium uppercase tracking-wide text-zinc-500">
                  Heartbeat
                </div>
                <div className="mt-1 flex items-center gap-2">
                  <StatusBadge
                    status={
                      heartbeatState === "Alive"
                        ? "running"
                        : heartbeatState === "Stale"
                          ? "failed"
                          : "cancelled"
                    }
                  />
                  <span>
                    {job.locked_at
                      ? `${heartbeatState} · ${formatRelativeTime(job.locked_at)}`
                      : heartbeatState}
                  </span>
                </div>
              </div>
              <div>
                <div className="text-xs font-medium uppercase tracking-wide text-zinc-500">
                  Started
                </div>
                <div className="mt-1">
                  {job.started_at
                    ? new Date(job.started_at).toLocaleString()
                    : "Not started"}
                </div>
              </div>
              <div>
                <div className="text-xs font-medium uppercase tracking-wide text-zinc-500">
                  Finished
                </div>
                <div className="mt-1">
                  {job.finished_at
                    ? new Date(job.finished_at).toLocaleString()
                    : "Not finished"}
                </div>
              </div>
              <div>
                <div className="text-xs font-medium uppercase tracking-wide text-zinc-500">
                  Args
                </div>
                <div className="mt-2">
                  <JsonBlock value={job.args} />
                </div>
              </div>
            </CardContent>
          </Card>

          {sourceMeeting && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <RadioTower className="h-5 w-5" />
                  Source meeting
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <div className="font-medium text-zinc-950">
                  {sourceMeeting.title}
                </div>
                <div className="flex items-center gap-2 text-zinc-600">
                  <Calendar className="h-4 w-4" />
                  {formatDate(sourceMeeting.meeting_date)}
                </div>
                <div className="flex items-center gap-2 text-zinc-600">
                  <FileText className="h-4 w-4" />
                  {sourceMeeting.archive_path || "No archive path"}
                </div>
                <StatusBadge status={sourceMeeting.status} />
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
