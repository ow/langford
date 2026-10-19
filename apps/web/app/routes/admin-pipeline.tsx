import { useEffect } from "react";
import {
  Form,
  Link,
  useActionData,
  useNavigation,
  useRevalidator,
} from "react-router";
import {
  Activity,
  Archive,
  CheckCircle2,
  ChevronDown,
  Ellipsis,
  Play,
  RadioTower,
  Search,
  StopCircle,
} from "lucide-react";
import type { Route } from "./+types/admin-pipeline";
import { requireAdmin } from "../lib/auth.server";
import { getSupabaseAdminClient } from "../lib/supabase.server";
import { Button } from "../components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "../components/ui/card";
import { ButtonGroup } from "../components/ui/button-group";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../components/ui/dropdown-menu";
import { Input } from "../components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../components/ui/table";
import { cn, formatDate, formatRelativeTime } from "../lib/utils";
import {
  enqueuePipelineJob,
  cancelPipelineJob,
  getPipelineDashboard,
  type PipelineJobType,
} from "../services/pipeline-admin.server";

export async function loader({ request }: Route.LoaderArgs) {
  await requireAdmin(request);
  const supabase = getSupabaseAdminClient();
  const url = new URL(request.url);
  const page = Number(url.searchParams.get("page") || "1");
  const q = url.searchParams.get("q") || "";
  return getPipelineDashboard(supabase, {
    page: Number.isFinite(page) ? page : 1,
    search: q,
    pageSize: 25,
  });
}

export async function action({ request }: Route.ActionArgs) {
  const user = await requireAdmin(request);
  const supabase = getSupabaseAdminClient();
  const formData = await request.formData();
  const jobType = formData.get("job_type") as PipelineJobType | null;
  const intent = formData.get("intent");
  const jobId = formData.get("job_id") as string | null;
  const limitValue = (formData.get("limit") as string | null)?.trim();
  const discoverAll = formData.get("discover_all") === "true" && !limitValue;
  const limit = discoverAll ? undefined : limitValue ? Number(limitValue) : undefined;
  const sourceMeetingId = formData.get("source_meeting_id") as string | null;
  const meetingId = formData.get("meeting_id") as string | null;
  const table = formData.get("table") as string | null;

  if (intent === "cancel_job") {
    if (!jobId) return { error: "Missing job id." };
    try {
      await cancelPipelineJob(supabase, jobId);
      return { success: `Cancelled job #${jobId}.` };
    } catch (error: any) {
      return { error: error.message || "Failed to cancel job." };
    }
  }

  const supportedJobTypes: PipelineJobType[] = [
    "preflight",
    "discover_meetings",
    "sync_documents",
    "sync_media",
    "ingest_meeting",
    "extract_documents",
    "embed_content",
    "diarize_meeting",
    "regenerate_summary",
  ];

  if (!jobType || !supportedJobTypes.includes(jobType)) {
    return { error: "Unsupported pipeline job type." };
  }

  if (limitValue && (!Number.isInteger(limit) || Number(limit) <= 0)) {
    return { error: "Limit must be a positive whole number." };
  }

  try {
    const args: Record<string, unknown> = {};
    if (limit) args.limit = limit;
    if (sourceMeetingId) args.source_meeting_id = Number(sourceMeetingId);
    if (meetingId) args.meeting_id = Number(meetingId);
    if (table) args.tables = [table];

    const job = await enqueuePipelineJob(
      supabase,
      jobType,
      user.email || user.id,
      args,
    );
    return { success: `Queued ${jobType.replace("_", " ")} job #${job.id}.` };
  } catch (error: any) {
    return { error: error.message || "Failed to queue pipeline job." };
  }
}

const statusDotClasses: Record<string, string> = {
  queued: "bg-amber-500",
  running: "bg-brand-500",
  succeeded: "bg-emerald-500",
  failed: "bg-red-500",
  cancelled: "bg-zinc-400",
  discovered: "bg-sky-500",
  documents_downloaded: "bg-emerald-500",
  media_downloaded: "bg-teal-500",
  ingested: "bg-indigo-500",
  extracted: "bg-fuchsia-500",
  diarized: "bg-cyan-500",
};

function formatStatus(status: string) {
  return status.replaceAll("_", " ");
}

function StatusLabel({
  status,
  className,
}: {
  status: string;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 whitespace-nowrap text-sm text-zinc-700",
        className,
      )}
    >
      <span
        className={cn(
          "h-2 w-2 rounded-full",
          statusDotClasses[status] || "bg-zinc-300",
        )}
      />
      {formatStatus(status)}
    </span>
  );
}

function StatMetric({
  label,
  value,
  detail,
}: {
  label: string;
  value: number;
  detail: string;
}) {
  return (
    <div className="min-w-0">
      <div className="text-xs font-medium uppercase tracking-wide text-zinc-500">
        {label}
      </div>
      <div className="mt-2 text-2xl font-semibold tracking-tight text-zinc-950">
        {value.toLocaleString()}
      </div>
      <p className="mt-1 truncate text-sm text-zinc-500">{detail}</p>
    </div>
  );
}

function QueueJobMenu({ isSubmitting }: { isSubmitting: boolean }) {
  return (
    <details className="group relative w-full md:w-auto">
      <summary className="inline-flex h-9 w-full cursor-pointer list-none items-center justify-center gap-2 whitespace-nowrap rounded-md border bg-background px-3 text-sm font-medium shadow-xs transition-all hover:bg-accent hover:text-accent-foreground md:w-auto [&::-webkit-details-marker]:hidden">
        <Play className="h-4 w-4" />
        Queue job
        <ChevronDown className="h-4 w-4 transition-transform group-open:rotate-180" />
      </summary>
      <div className="mt-2 w-full rounded-lg border border-zinc-200 bg-white p-4 shadow-lg md:absolute md:right-0 md:z-20 md:w-[420px]">
        <div className="mb-3">
          <div className="font-medium text-zinc-950">Manual queue</div>
          <p className="mt-1 text-sm text-zinc-500">
            Use source-row ingest for normal meeting processing.
          </p>
        </div>
        <Form method="post" className="grid gap-3">
          <Button
            type="submit"
            name="job_type"
            value="preflight"
            variant="outline"
            disabled={isSubmitting}
          >
            Run preflight
          </Button>
          <div className="grid grid-cols-[1fr_auto] gap-2">
            <Input
              name="limit"
              type="number"
              min="1"
              placeholder="Discovery limit, blank = all"
            />
            <input type="hidden" name="discover_all" value="true" />
            <Button
              type="submit"
              name="job_type"
              value="discover_meetings"
              disabled={isSubmitting}
            >
              <Search className="h-4 w-4" />
              Discover
            </Button>
          </div>
          <Button
            type="submit"
            name="job_type"
            value="sync_documents"
            variant="secondary"
            disabled={isSubmitting}
          >
            <Archive className="h-4 w-4" />
            Sync documents
          </Button>
          <div className="grid grid-cols-[1fr_auto] gap-2 border-t border-zinc-100 pt-3">
            <input type="hidden" name="table" value="document_sections" />
            <div className="rounded-md border border-zinc-200 px-3 py-2 text-sm text-zinc-600">
              Embed document sections
            </div>
            <Button
              type="submit"
              name="job_type"
              value="embed_content"
              variant="outline"
              disabled={isSubmitting}
            >
              Queue
            </Button>
          </div>
        </Form>
      </div>
    </details>
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
  return "Unknown time";
}

export default function AdminPipeline({ loaderData }: Route.ComponentProps) {
  const {
    municipality,
    counts,
    jobs,
    sourceMeetings,
    sourceMeetingsPage,
    events,
  } = loaderData;
  const actionData = useActionData<typeof action>();
  const navigation = useNavigation();
  const revalidator = useRevalidator();
  const isSubmitting = navigation.state === "submitting";
  const hasActiveVisibleJob = sourceMeetings.some((meeting: any) =>
    ["queued", "running"].includes(meeting.latest_job?.status),
  );
  const hasActiveWork =
    counts.jobRunning > 0 || counts.jobQueued > 0 || hasActiveVisibleJob;
  const page = sourceMeetingsPage.page;
  const totalPages = sourceMeetingsPage.totalPages;
  const searchParams = new URLSearchParams();
  if (sourceMeetingsPage.search) {
    searchParams.set("q", sourceMeetingsPage.search);
  }
  const pageHref = (nextPage: number) => {
    const params = new URLSearchParams(searchParams);
    params.set("page", String(nextPage));
    return `/admin/pipeline?${params.toString()}`;
  };

  useEffect(() => {
    if (!hasActiveWork) return;
    const id = window.setInterval(() => revalidator.revalidate(), 5000);
    return () => window.clearInterval(id);
  }, [hasActiveWork, revalidator]);

  return (
    <div className="container mx-auto max-w-7xl px-4 py-8">
      <div className="mb-6 flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="mb-3 inline-flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-zinc-500">
            <RadioTower className="h-3.5 w-3.5" />
            Internal pipeline ops
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-zinc-950">
            {municipality.short_name} pipeline
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-zinc-600">
            Monitor queue health, active workers, and meeting ingestion.
          </p>
        </div>

        <QueueJobMenu isSubmitting={isSubmitting} />
      </div>

      {actionData?.success && (
        <p className="mb-4 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
          {actionData.success}
        </p>
      )}
      {actionData?.error && (
        <p className="mb-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
          {actionData.error}
        </p>
      )}

      <div className="rounded-lg border border-zinc-200 bg-white p-4">
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          <StatMetric
            label="Queue"
            value={counts.jobRunning}
            detail={`${counts.jobQueued.toLocaleString()} queued · ${counts.jobFailed.toLocaleString()} failed`}
          />
          <StatMetric
            label="Source meetings"
            value={counts.sourceTotal}
            detail={`${counts.sourcePendingIngest.toLocaleString()} not ingested`}
          />
          <StatMetric
            label="App meetings"
            value={counts.appMeetings}
            detail={`${counts.appDocuments.toLocaleString()} source PDFs`}
          />
          <StatMetric
            label="Searchable docs"
            value={counts.appExtractedDocuments}
            detail={`${counts.appSections.toLocaleString()} sections`}
          />
        </div>
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1fr)_380px]">
        <Card>
          <CardHeader>
            <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
              <div>
                <CardTitle>Meeting inventory</CardTitle>
                <CardDescription>
                  {sourceMeetingsPage.total.toLocaleString()} upstream meetings.
                </CardDescription>
              </div>
              <Form method="get" className="flex gap-2">
                <Input
                  name="q"
                  defaultValue={sourceMeetingsPage.search}
                  placeholder="Search title, type, source id"
                  className="w-64"
                />
                <Button type="submit" variant="outline">
                  <Search className="mr-2 h-4 w-4" />
                  Search
                </Button>
              </Form>
            </div>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Meeting</TableHead>
                  <TableHead>Pipeline</TableHead>
                  <TableHead>Output</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sourceMeetings.map((meeting: any) => (
                  <TableRow key={meeting.id}>
                    <TableCell className="whitespace-nowrap text-sm text-zinc-600">
                      {formatDate(meeting.meeting_date, {
                        month: "short",
                        day: "numeric",
                        year: "numeric",
                      })}
                    </TableCell>
                    <TableCell>
                      <div className="font-medium text-zinc-900">
                        {meeting.title}
                      </div>
                      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-zinc-500">
                        <span>{meeting.meeting_type || meeting.source_id}</span>
                        <StatusLabel
                          status={meeting.status}
                          className="text-xs text-zinc-500"
                        />
                      </div>
                    </TableCell>
                    <TableCell>
                      {meeting.latest_job ? (
                        <div className="space-y-1 text-sm text-zinc-600">
                          <Link
                            to={`/admin/pipeline/jobs/${meeting.latest_job.id}`}
                            className="inline-flex items-center gap-2 font-medium text-zinc-900 hover:text-brand-700 hover:underline"
                          >
                            <StatusLabel status={meeting.latest_job.status} />
                            <span>#{meeting.latest_job.id}</span>
                          </Link>
                          <div className="text-xs text-zinc-500">
                            {meeting.latest_job.job_type.replaceAll("_", " ")}
                            {meeting.latest_job.locked_at
                              ? ` · heartbeat ${formatRelativeTime(meeting.latest_job.locked_at)}`
                              : meeting.latest_job.requested_at
                                ? ` · queued ${formatRelativeTime(meeting.latest_job.requested_at)}`
                                : ""}
                          </div>
                          {meeting.latest_job.last_error && (
                            <div
                              className="max-w-[220px] truncate text-xs text-red-700"
                              title={meeting.latest_job.last_error}
                            >
                              {meeting.latest_job.last_error}
                            </div>
                          )}
                        </div>
                      ) : (
                        <span className="text-sm text-zinc-400">No job</span>
                      )}
                    </TableCell>
                    <TableCell>
                      {meeting.ingested_meeting_id ? (
                        <div className="space-y-1 text-sm">
                          <span className="inline-flex items-center gap-1 text-emerald-700">
                            <CheckCircle2 className="h-4 w-4" />
                            Meeting #{meeting.ingested_meeting_id}
                          </span>
                          <div className="text-xs text-zinc-500">
                            {meeting.document_count} docs · {meeting.section_count} sections
                          </div>
                        </div>
                      ) : (
                        <span className="text-sm text-zinc-400">Not yet</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="flex justify-end">
                        <ButtonGroup>
                        {!meeting.ingested_meeting_id && (
                          <Form method="post">
                            <input
                              type="hidden"
                              name="source_meeting_id"
                              value={meeting.id}
                            />
                            <Button
                              type="submit"
                              name="job_type"
                              value="ingest_meeting"
                              variant="outline"
                              size="sm"
                              disabled={isSubmitting}
                            >
                              Ingest full
                            </Button>
                          </Form>
                        )}
                        {meeting.ingested_meeting_id && (
                          <Button asChild variant="outline" size="sm">
                            <Link to={`/meetings/${meeting.ingested_meeting_id}`}>
                              View
                            </Link>
                          </Button>
                        )}
                          {(meeting.ingested_meeting_id ||
                            (!meeting.ingested_meeting_id && meeting.video_url)) && (
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button
                                type="button"
                                variant="outline"
                                size="icon-sm"
                                disabled={isSubmitting}
                                aria-label="More pipeline actions"
                              >
                                <Ellipsis />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              <DropdownMenuGroup>
                                {!meeting.ingested_meeting_id && meeting.video_url && (
                                  <Form method="post">
                                    <input
                                      type="hidden"
                                      name="source_meeting_id"
                                      value={meeting.id}
                                    />
                                    <DropdownMenuItem asChild>
                                      <button
                                        type="submit"
                                        name="job_type"
                                        value="sync_media"
                                        disabled={isSubmitting}
                                      >
                                        Cache media
                                      </button>
                                    </DropdownMenuItem>
                                  </Form>
                                )}
                                {meeting.ingested_meeting_id && (
                                  <Form method="post">
                                    <input
                                      type="hidden"
                                      name="source_meeting_id"
                                      value={meeting.id}
                                    />
                                    <DropdownMenuItem asChild>
                                      <button
                                        type="submit"
                                        name="job_type"
                                        value="regenerate_summary"
                                        disabled={isSubmitting}
                                      >
                                        Regenerate summary
                                      </button>
                                    </DropdownMenuItem>
                                  </Form>
                                )}
                                {meeting.ingested_meeting_id && (
                                  <Form method="post">
                                    <input
                                      type="hidden"
                                      name="source_meeting_id"
                                      value={meeting.id}
                                    />
                                    <DropdownMenuItem asChild>
                                      <button
                                        type="submit"
                                        name="job_type"
                                        value="extract_documents"
                                        disabled={isSubmitting}
                                      >
                                        Rerun docs
                                      </button>
                                    </DropdownMenuItem>
                                  </Form>
                                )}
                                {meeting.ingested_meeting_id && meeting.video_url && (
                                  <Form method="post">
                                    <input
                                      type="hidden"
                                      name="source_meeting_id"
                                      value={meeting.id}
                                    />
                                    <DropdownMenuItem asChild>
                                      <button
                                        type="submit"
                                        name="job_type"
                                        value="diarize_meeting"
                                        disabled={isSubmitting}
                                      >
                                        Rerun audio
                                      </button>
                                    </DropdownMenuItem>
                                  </Form>
                                )}
                              </DropdownMenuGroup>
                            </DropdownMenuContent>
                          </DropdownMenu>
                          )}
                        </ButtonGroup>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
                {sourceMeetings.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={5} className="py-8 text-center text-zinc-500">
                      No source meetings recorded yet. Queue discovery to populate this table.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
            <div className="mt-4 flex flex-col gap-3 border-t pt-4 text-sm text-zinc-600 sm:flex-row sm:items-center sm:justify-between">
              <div>
                Page {page} of {totalPages}
                {sourceMeetingsPage.search
                  ? ` for "${sourceMeetingsPage.search}"`
                  : ""}
              </div>
              <div className="flex gap-2">
                <Button asChild variant="outline" size="sm" disabled={page <= 1}>
                  <Link to={pageHref(Math.max(page - 1, 1))}>Previous</Link>
                </Button>
                <Button
                  asChild
                  variant="outline"
                  size="sm"
                  disabled={page >= totalPages}
                >
                  <Link to={pageHref(Math.min(page + 1, totalPages))}>Next</Link>
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Jobs</CardTitle>
              <CardDescription>
                {counts.jobRunning.toLocaleString()} running ·{" "}
                {counts.jobQueued.toLocaleString()} queued ·{" "}
                {counts.jobSucceeded.toLocaleString()} done
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="divide-y divide-zinc-100">
                {jobs.map((job: any) => (
                  <div key={job.id} className="py-3 first:pt-0 last:pb-0">
                    <div className="flex items-center justify-between gap-3">
                      <Link
                        to={`/admin/pipeline/jobs/${job.id}`}
                        className="font-medium hover:text-brand-700 hover:underline"
                      >
                        #{job.id} {job.job_type.replaceAll("_", " ")}
                      </Link>
                      <StatusLabel status={job.status} className="text-xs" />
                    </div>
                    <div className="mt-1 flex items-center gap-2 text-xs text-zinc-500">
                      <Play className="h-3.5 w-3.5" />
                      {jobLifecycleSummary(job)}
                      {job.requested_by ? ` by ${job.requested_by}` : ""}
                    </div>
                    {job.status === "running" && job.locked_at && (
                      <div className="mt-1 text-xs text-zinc-500">
                        Last heartbeat {formatRelativeTime(job.locked_at)}
                      </div>
                    )}
                    {job.last_error && (
                      <p className="mt-2 line-clamp-2 text-xs text-red-700">
                        {job.last_error}
                      </p>
                    )}
                    <div className="mt-3 flex gap-2">
                      <Button asChild variant="outline" size="sm">
                        <Link to={`/admin/pipeline/jobs/${job.id}`}>Details</Link>
                      </Button>
                      {job.status === "queued" && (
                        <Form method="post">
                          <input type="hidden" name="intent" value="cancel_job" />
                          <input type="hidden" name="job_id" value={job.id} />
                          <Button
                            type="submit"
                            variant="outline"
                            size="sm"
                            disabled={isSubmitting}
                          >
                            <StopCircle className="mr-1 h-3.5 w-3.5" />
                            Cancel
                          </Button>
                        </Form>
                      )}
                    </div>
                  </div>
                ))}
              </div>
              {jobs.length === 0 && (
                <p className="text-sm text-zinc-500">No jobs queued yet.</p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Worker events</CardTitle>
              <CardDescription>Latest events for the visible jobs.</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="divide-y divide-zinc-100">
                {events.slice(0, 10).map((event: any) => (
                  <div
                    key={event.id}
                    className="py-3 text-sm first:pt-0 last:pb-0"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="line-clamp-2 font-medium text-zinc-800">
                        {event.message}
                      </div>
                      <span className="shrink-0 text-xs uppercase tracking-wide text-zinc-400">
                        {event.level}
                      </span>
                    </div>
                    <div className="mt-1 flex items-center gap-2 text-xs text-zinc-500">
                      <Activity className="h-3.5 w-3.5" />
                      Job #{event.job_id} · {formatRelativeTime(event.created_at)}
                    </div>
                  </div>
                ))}
              </div>
              {events.length === 0 && (
                <p className="text-sm text-zinc-500">No worker events yet.</p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
