import { useEffect, useState } from "react";
import {
  Form,
  Link,
  useActionData,
  useNavigation,
  useRevalidator,
} from "react-router";
import { ChevronDown, Ellipsis } from "lucide-react";
import type { Route } from "./+types/admin-pipeline";
import { requireAdmin } from "../lib/auth.server";
import { getSupabaseAdminClient } from "../lib/supabase.server";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { ButtonGroup } from "../components/ui/button-group";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "../components/ui/dropdown-menu";
import { FilterBar } from "../components/ui/filter-bar";
import { Input } from "../components/ui/input";
import { PageHeader } from "../components/ui/page-header";
import { SearchField } from "../components/ui/search-field";
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

type BadgeTone = "success" | "danger" | "warning" | "muted" | "brand";

/** Job statuses use semantic tones; source-meeting stages are neutral/brand. */
const statusTones: Record<string, BadgeTone> = {
  succeeded: "success",
  completed: "success",
  failed: "danger",
  running: "warning",
  queued: "warning",
  cancelled: "muted",
  discovered: "muted",
  documents_downloaded: "muted",
  media_downloaded: "muted",
  ingested: "brand",
  extracted: "brand",
  diarized: "brand",
};

function formatStatus(status: string) {
  const text = status.replaceAll("_", " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function StatusBadge({
  status,
  className,
}: {
  status: string;
  className?: string;
}) {
  return (
    <Badge variant={statusTones[status] ?? "muted"} className={className}>
      {formatStatus(status)}
    </Badge>
  );
}

function formatJobType(jobType: string) {
  return formatStatus(jobType).toLowerCase();
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
    <div className="min-w-0 bg-white px-4 py-3">
      <div className="text-sm text-zinc-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums tracking-tight text-zinc-950">
        {value.toLocaleString()}
      </div>
      <p className="mt-0.5 truncate text-xs tabular-nums text-zinc-500">
        {detail}
      </p>
    </div>
  );
}

function QueueJobMenu({ isSubmitting }: { isSubmitting: boolean }) {
  return (
    <details className="group relative w-full md:w-auto">
      <summary className="inline-flex h-9 w-full cursor-pointer list-none items-center justify-center gap-2 whitespace-nowrap rounded-md border border-zinc-200 bg-white px-3 text-sm font-medium text-zinc-800 shadow-xs transition-colors hover:bg-zinc-50 focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-brand-500/20 md:w-auto [&::-webkit-details-marker]:hidden">
        Queue job
        <ChevronDown
          className="h-4 w-4 text-zinc-400 transition-transform group-open:rotate-180"
          aria-hidden="true"
        />
      </summary>
      <div className="mt-2 w-full rounded-2xl border border-zinc-200 bg-white p-4 shadow-lg md:absolute md:right-0 md:z-30 md:w-[400px]">
        <div className="mb-3">
          <div className="text-sm font-semibold text-zinc-900">
            Manual queue
          </div>
          <p className="mt-0.5 text-sm text-zinc-500">
            Use per-meeting ingest for normal processing.
          </p>
        </div>
        <Form method="post" className="divide-y divide-zinc-100">
          <div className="flex items-center justify-between gap-3 py-2.5">
            <div className="text-sm text-zinc-700">Preflight checks</div>
            <Button
              type="submit"
              name="job_type"
              value="preflight"
              variant="outline"
              size="sm"
              disabled={isSubmitting}
            >
              Run
            </Button>
          </div>
          <div className="py-2.5">
            <label
              htmlFor="discover-limit"
              className="mb-1.5 block text-sm text-zinc-700"
            >
              Discover meetings
            </label>
            <div className="flex gap-2">
              <Input
                id="discover-limit"
                name="limit"
                type="number"
                min="1"
                placeholder="Limit (blank for all)"
                className="h-8"
              />
              <input type="hidden" name="discover_all" value="true" />
              <Button
                type="submit"
                name="job_type"
                value="discover_meetings"
                size="sm"
                disabled={isSubmitting}
              >
                Discover
              </Button>
            </div>
          </div>
          <div className="flex items-center justify-between gap-3 py-2.5">
            <div className="text-sm text-zinc-700">Sync documents</div>
            <Button
              type="submit"
              name="job_type"
              value="sync_documents"
              variant="outline"
              size="sm"
              disabled={isSubmitting}
            >
              Sync
            </Button>
          </div>
          <div className="flex items-center justify-between gap-3 pt-2.5">
            <input type="hidden" name="table" value="document_sections" />
            <div className="text-sm text-zinc-700">Embed document sections</div>
            <Button
              type="submit"
              name="job_type"
              value="embed_content"
              variant="outline"
              size="sm"
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

const levelTones: Record<string, BadgeTone> = {
  error: "danger",
  warning: "warning",
  info: "muted",
};

const card = "rounded-2xl border border-zinc-200 bg-white shadow-sm";

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
  const [search, setSearch] = useState(sourceMeetingsPage.search ?? "");
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
    setSearch(sourceMeetingsPage.search ?? "");
  }, [sourceMeetingsPage.search]);

  useEffect(() => {
    if (!hasActiveWork) return;
    const id = window.setInterval(() => revalidator.revalidate(), 5000);
    return () => window.clearInterval(id);
  }, [hasActiveWork, revalidator]);

  return (
    <div className="min-h-screen bg-zinc-50">
      <div className="container mx-auto max-w-6xl px-4 py-12">
        <PageHeader
          title={`${municipality.short_name} pipeline`}
          description="Queue health, active workers and meeting ingestion."
          actions={<QueueJobMenu isSubmitting={isSubmitting} />}
        />

        {actionData?.success && (
          <p
            role="status"
            className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-sm text-emerald-800"
          >
            {actionData.success}
          </p>
        )}
        {actionData?.error && (
          <p
            role="alert"
            className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-800"
          >
            {actionData.error}
          </p>
        )}

        <div
          className={cn(
            card,
            "grid grid-cols-2 gap-px overflow-hidden bg-zinc-100 lg:grid-cols-4",
          )}
        >
          <StatMetric
            label="Running jobs"
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

        <div className="mt-8 grid gap-8 xl:grid-cols-[minmax(0,1fr)_340px]">
          <section aria-labelledby="inventory-heading" className="min-w-0">
            <div className="mb-3 flex items-baseline justify-between gap-3">
              <h2
                id="inventory-heading"
                className="text-lg font-semibold text-zinc-900"
              >
                Meeting inventory
              </h2>
              <span className="text-sm tabular-nums text-zinc-500">
                {sourceMeetingsPage.total.toLocaleString()} upstream meetings
              </span>
            </div>

            <Form method="get">
              <FilterBar
                sticky={false}
                className="mb-3"
                search={
                  <SearchField
                    name="q"
                    value={search}
                    onValueChange={setSearch}
                    placeholder="Search title, type or source ID"
                    aria-label="Search source meetings"
                  />
                }
                controls={
                  <Button type="submit" variant="outline" className="h-10">
                    Search
                  </Button>
                }
              />
            </Form>

            {sourceMeetings.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-zinc-300 bg-white/60 p-5 text-sm text-zinc-500">
                {sourceMeetingsPage.search
                  ? `No source meetings match "${sourceMeetingsPage.search}".`
                  : "No source meetings recorded yet. Queue discovery to populate this list."}
              </div>
            ) : (
              <div className={cn(card, "overflow-hidden")}>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead className="border-b border-zinc-100 bg-zinc-50/60 text-left text-xs text-zinc-500">
                      <tr>
                        <th scope="col" className="px-4 py-2 font-medium">
                          Date
                        </th>
                        <th scope="col" className="px-4 py-2 font-medium">
                          Meeting
                        </th>
                        <th scope="col" className="px-4 py-2 font-medium">
                          Latest job
                        </th>
                        <th scope="col" className="px-4 py-2 font-medium">
                          Output
                        </th>
                        <th scope="col" className="px-4 py-2 text-right font-medium">
                          <span className="sr-only">Actions</span>
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-zinc-100">
                      {sourceMeetings.map((meeting: any) => (
                        <tr key={meeting.id} className="align-top">
                          <td className="whitespace-nowrap px-4 py-3 tabular-nums text-zinc-600">
                            {formatDate(meeting.meeting_date, {
                              month: "short",
                              day: "numeric",
                              year: "numeric",
                            })}
                          </td>
                          <td className="min-w-[200px] px-4 py-3">
                            <div className="font-medium text-zinc-900">
                              {meeting.title}
                            </div>
                            <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-zinc-500">
                              <span>
                                {meeting.meeting_type || meeting.source_id}
                              </span>
                              <StatusBadge status={meeting.status} />
                            </div>
                          </td>
                          <td className="min-w-[160px] px-4 py-3">
                            {meeting.latest_job ? (
                              <div className="space-y-1">
                                <Link
                                  to={`/admin/pipeline/jobs/${meeting.latest_job.id}`}
                                  className="inline-flex items-center gap-2 text-zinc-900 hover:text-brand-700"
                                >
                                  <StatusBadge
                                    status={meeting.latest_job.status}
                                  />
                                  <span className="tabular-nums hover:underline">
                                    #{meeting.latest_job.id}
                                  </span>
                                </Link>
                                <div className="text-xs text-zinc-500">
                                  {formatJobType(meeting.latest_job.job_type)}
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
                              <span className="text-zinc-400">No job</span>
                            )}
                          </td>
                          <td className="whitespace-nowrap px-4 py-3">
                            {meeting.ingested_meeting_id ? (
                              <div className="space-y-1">
                                <span className="tabular-nums text-emerald-700">
                                  Meeting #{meeting.ingested_meeting_id}
                                </span>
                                <div className="text-xs tabular-nums text-zinc-500">
                                  {meeting.document_count} docs ·{" "}
                                  {meeting.section_count} sections
                                </div>
                              </div>
                            ) : (
                              <span className="text-zinc-400">Not yet</span>
                            )}
                          </td>
                          <td className="px-4 py-3">
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
                                      Ingest
                                    </Button>
                                  </Form>
                                )}
                                {meeting.ingested_meeting_id && (
                                  <Button asChild variant="outline" size="sm">
                                    <Link
                                      to={`/meetings/${meeting.ingested_meeting_id}`}
                                    >
                                      View
                                    </Link>
                                  </Button>
                                )}
                                {(meeting.ingested_meeting_id ||
                                  (!meeting.ingested_meeting_id &&
                                    meeting.video_url)) && (
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
                                        {!meeting.ingested_meeting_id &&
                                          meeting.video_url && (
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
                                                  className="w-full"
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
                                                className="w-full"
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
                                                className="w-full"
                                              >
                                                Rerun documents
                                              </button>
                                            </DropdownMenuItem>
                                          </Form>
                                        )}
                                        {meeting.ingested_meeting_id &&
                                          meeting.video_url && (
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
                                                  className="w-full"
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
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="flex items-center justify-between gap-3 border-t border-zinc-100 px-4 py-3 text-sm text-zinc-500">
                  <div className="tabular-nums">
                    Page {page} of {totalPages}
                    {sourceMeetingsPage.search
                      ? ` for "${sourceMeetingsPage.search}"`
                      : ""}
                  </div>
                  <div className="flex gap-2">
                    {page <= 1 ? (
                      <Button variant="outline" size="sm" disabled>
                        Previous
                      </Button>
                    ) : (
                      <Button asChild variant="outline" size="sm">
                        <Link to={pageHref(Math.max(page - 1, 1))}>
                          Previous
                        </Link>
                      </Button>
                    )}
                    {page >= totalPages ? (
                      <Button variant="outline" size="sm" disabled>
                        Next
                      </Button>
                    ) : (
                      <Button asChild variant="outline" size="sm">
                        <Link to={pageHref(Math.min(page + 1, totalPages))}>
                          Next
                        </Link>
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            )}
          </section>

          <aside className="min-w-0 space-y-8">
            <section aria-labelledby="jobs-heading">
              <div className="mb-3">
                <h2
                  id="jobs-heading"
                  className="text-lg font-semibold text-zinc-900"
                >
                  Jobs
                </h2>
                <p className="text-sm tabular-nums text-zinc-500">
                  {counts.jobRunning.toLocaleString()} running ·{" "}
                  {counts.jobQueued.toLocaleString()} queued ·{" "}
                  {counts.jobSucceeded.toLocaleString()} done
                </p>
              </div>
              {jobs.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-zinc-300 bg-white/60 p-5 text-sm text-zinc-500">
                  No jobs queued yet.
                </div>
              ) : (
                <ul className={cn(card, "divide-y divide-zinc-100")}>
                  {jobs.map((job: any) => (
                    <li key={job.id} className="px-4 py-3">
                      <div className="flex items-start justify-between gap-3">
                        <Link
                          to={`/admin/pipeline/jobs/${job.id}`}
                          className="min-w-0 text-sm font-medium text-zinc-900 hover:text-brand-700 hover:underline"
                        >
                          <span className="tabular-nums text-zinc-500">
                            #{job.id}
                          </span>{" "}
                          {formatJobType(job.job_type)}
                        </Link>
                        <StatusBadge status={job.status} />
                      </div>
                      <div className="mt-0.5 text-xs text-zinc-500">
                        {jobLifecycleSummary(job)}
                        {job.requested_by ? ` by ${job.requested_by}` : ""}
                        {job.status === "running" && job.locked_at
                          ? ` · heartbeat ${formatRelativeTime(job.locked_at)}`
                          : ""}
                      </div>
                      {job.last_error && (
                        <p className="mt-1 line-clamp-2 text-xs text-red-700">
                          {job.last_error}
                        </p>
                      )}
                      {job.status === "queued" && (
                        <Form method="post" className="mt-2">
                          <input type="hidden" name="intent" value="cancel_job" />
                          <input type="hidden" name="job_id" value={job.id} />
                          <Button
                            type="submit"
                            variant="outline"
                            size="sm"
                            className="h-7"
                            disabled={isSubmitting}
                          >
                            Cancel
                          </Button>
                        </Form>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section aria-labelledby="events-heading">
              <div className="mb-3">
                <h2
                  id="events-heading"
                  className="text-lg font-semibold text-zinc-900"
                >
                  Worker events
                </h2>
                <p className="text-sm text-zinc-500">
                  Latest events for the visible jobs.
                </p>
              </div>
              {events.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-zinc-300 bg-white/60 p-5 text-sm text-zinc-500">
                  No worker events yet.
                </div>
              ) : (
                <ul className={cn(card, "divide-y divide-zinc-100")}>
                  {events.slice(0, 10).map((event: any) => (
                    <li key={event.id} className="px-4 py-2.5 text-sm">
                      <div className="flex items-start justify-between gap-3">
                        <div className="line-clamp-2 text-zinc-800">
                          {event.message}
                        </div>
                        {event.level && event.level !== "info" && (
                          <Badge variant={levelTones[event.level] ?? "muted"}>
                            {formatStatus(event.level)}
                          </Badge>
                        )}
                      </div>
                      <div className="mt-0.5 text-xs text-zinc-500">
                        <Link
                          to={`/admin/pipeline/jobs/${event.job_id}`}
                          className="tabular-nums hover:text-brand-700 hover:underline"
                        >
                          Job #{event.job_id}
                        </Link>{" "}
                        · {formatRelativeTime(event.created_at)}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </aside>
        </div>
      </div>
    </div>
  );
}
